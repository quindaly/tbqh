"""Who Knows Who game orchestration service."""

from __future__ import annotations

import random
import uuid
from collections import defaultdict
from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import exists
from sqlalchemy.orm import Session, aliased

from app.db.models.experience import ExperienceInstance
from app.db.models.game_guess import GameGuess
from app.db.models.game_round import GameRound
from app.db.models.group import Group
from app.db.models.participant import Participant
from app.db.models.prompt import PromptInstance, PromptResponse
from app.db.models.session import Session as SessionModel, SessionParticipant
from app.services.games.hwdyk_common import lock_experience as _lock_experience
from app.services.games.names import clean_display_name, ensure_name_free
from app.services.games.question_bank import select_questions
from app.services.games.roster import host_of, roster as _roster, session_participants
from app.services.games.sharing import generate_join_code, generate_share_url
from app.services.games.state import transition_state
from app.services.telemetry.events import log_event

# A guessing game needs someone to guess between: with two players the only
# possible answer is "the other person".
MIN_PLAYERS = 3
MAX_PLAYERS = 20
MAX_ANSWER_LEN = 280

DEFAULT_GAME_CONFIG = {
    "num_questions": 10,
    "max_rounds": 10,
    "min_answer_length": 2,
}

# Settings that carry over to a replay.
_CARRY_OVER_CONFIG = ("num_questions", "max_rounds", "min_answer_length")


def _conflict(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detail)


def _forbidden(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=detail)


def _require_member(
    db: Session, experience: ExperienceInstance, participant_id: uuid.UUID
) -> Participant:
    """The participant must be playing in this game."""
    for p in _roster(db, experience):
        if p.id == participant_id:
            return p
    raise _forbidden("You are not part of this game")


def _is_host(db: Session, experience: ExperienceInstance, participant_id: uuid.UUID) -> bool:
    players = _roster(db, experience)
    host = host_of(players, experience.present_participant_ids is not None)
    return host is not None and host.id == participant_id


# ---------- create / join ----------


def create_game(
    db: Session,
    user_id: uuid.UUID | None,
    display_name: str,
) -> dict:
    display_name = clean_display_name(display_name)

    # A signed-in host keeps their account; a guest host is stored as an
    # anonymous participant (see the note on anonymous users below).
    authenticated = user_id is not None
    if user_id is None:
        from app.db.models.user import User

        anon_user = User(email=f"anon-{uuid.uuid4().hex[:8]}@game.local")
        db.add(anon_user)
        db.flush()
        user_id = anon_user.id

    group = Group(created_by_user_id=user_id, name=f"{display_name}'s game")
    db.add(group)
    db.flush()

    host = Participant(
        group_id=group.id,
        user_id=user_id,
        display_name=display_name,
        role="host",
        join_type="authenticated" if authenticated else "anonymous",
    )
    db.add(host)
    db.flush()

    join_code = generate_join_code()
    # Need a policy profile for session — use first available or create a dummy
    from app.db.models.policy import PolicyProfile

    policy = db.query(PolicyProfile).first()
    if not policy:
        policy = PolicyProfile(name="default", excluded_categories=[])
        db.add(policy)
        db.flush()

    session = SessionModel(
        group_id=group.id,
        policy_profile_id=policy.id,
        join_code=join_code,
    )
    db.add(session)
    db.flush()

    sp = SessionParticipant(session_id=session.id, participant_id=host.id)
    db.add(sp)
    db.flush()

    config = dict(DEFAULT_GAME_CONFIG)
    experience = ExperienceInstance(
        session_id=session.id,
        experience_type="who_knows_who",
        game_state="lobby",
        game_config=config,
        max_rounds=config["max_rounds"],
        current_round=0,
    )
    db.add(experience)
    db.flush()

    share_url = generate_share_url(experience.id, join_code)

    log_event(
        db,
        "game_created",
        session_id=session.id,
        experience_instance_id=experience.id,
        participant_id=host.id,
        payload={"game_slug": "who-knows-who"},
    )
    db.commit()

    return {
        "group_id": str(group.id),
        "session_id": str(session.id),
        "experience_instance_id": str(experience.id),
        "participant_id": str(host.id),
        "join_code": join_code,
        "share_url": share_url,
    }


def _newest_game(db: Session, session_id: uuid.UUID) -> ExperienceInstance | None:
    """The join code outlives a single game, so people joining land in the
    newest game of the session: the one no later game follows."""
    later = aliased(ExperienceInstance)
    return (
        db.query(ExperienceInstance)
        .filter(
            ExperienceInstance.session_id == session_id,
            ExperienceInstance.experience_type == "who_knows_who",
            ~exists().where(later.parent_experience_instance_id == ExperienceInstance.id),
        )
        .order_by(ExperienceInstance.created_at.desc(), ExperienceInstance.id)
        .first()
    )


def join_game(
    db: Session,
    join_code: str,
    display_name: str,
    user_id: uuid.UUID | None = None,
    join_mode: str = "anonymous",
) -> dict:
    display_name = clean_display_name(display_name)

    session = db.query(SessionModel).filter(SessionModel.join_code == join_code).first()
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Invalid join code"
        )

    experience = _newest_game(db, session.id)
    if not experience:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Game not found"
        )

    # Settle (under lock) that it is still a lobby before anyone is added.
    experience = _lock_experience(db, experience.id)
    if experience.game_state != "lobby":
        raise _conflict("This game has already started, so new players can't join.")

    players = _roster(db, experience)
    if len(players) >= MAX_PLAYERS:
        raise _conflict("This game is full.")
    ensure_name_free(display_name, [p.display_name for p in players])

    participant = Participant(
        group_id=session.group_id,
        user_id=user_id,
        display_name=display_name,
        role="guest",
        join_type=join_mode,
    )
    db.add(participant)
    db.flush()

    sp = SessionParticipant(session_id=session.id, participant_id=participant.id)
    db.add(sp)
    db.flush()

    if experience.present_participant_ids is not None:
        # Joining a replay lobby: the newcomer is in it from the start.
        _add_present(experience, participant.id)

    log_event(
        db,
        "game_joined",
        session_id=session.id,
        experience_instance_id=experience.id,
        participant_id=participant.id,
    )
    db.commit()

    return {
        "participant_id": str(participant.id),
        "session_id": str(session.id),
        "experience_instance_id": str(experience.id),
    }


# ---------- lobby helpers ----------


def get_lobby_payload(db: Session, experience: ExperienceInstance) -> dict:
    session = db.get(SessionModel, experience.session_id)
    participants = _roster(db, experience)
    is_replay = experience.present_participant_ids is not None
    host = host_of(participants, is_replay)

    # In a replay lobby, the session's other players who have not come back yet.
    absent = []
    if is_replay:
        here = {p.id for p in participants}
        absent = [
            {"id": str(p.id), "display_name": p.display_name}
            for p in session_participants(db, experience.session_id)
            if p.id not in here
        ]

    return {
        "experience_id": str(experience.id),
        "game_state": experience.game_state,
        "game_slug": "who-knows-who",
        "join_code": session.join_code,
        "share_url": generate_share_url(experience.id, session.join_code),
        "host_id": str(host.id) if host else None,
        "is_replay": is_replay,
        "absent_participants": absent,
        "min_players": MIN_PLAYERS,
        "participants": [
            {
                "id": str(p.id),
                "display_name": p.display_name,
                "role": "host" if host and p.id == host.id else p.role,
            }
            for p in participants
        ],
    }


# ---------- answer collection ----------


def start_answer_collection(
    db: Session,
    experience: ExperienceInstance,
    participant_id: uuid.UUID,
) -> dict:
    experience = _lock_experience(db, experience.id)
    _require_member(db, experience, participant_id)
    if not _is_host(db, experience, participant_id):
        raise _forbidden("Only the host can start the game")

    if len(_roster(db, experience)) < MIN_PLAYERS:
        raise _conflict(f"Need at least {MIN_PLAYERS} players to start")

    transition_state(db, experience, "question_collection")

    # Create prompts from question bank
    config = experience.game_config or DEFAULT_GAME_CONFIG
    num_q = config.get("num_questions", 10)
    questions = select_questions(num_q)

    session = db.get(SessionModel, experience.session_id)

    created_prompts = []
    for q_text in questions:
        pi = PromptInstance(
            session_id=session.id,
            experience_instance_id=experience.id,
            prompt_type="who_knows_who_self_answer",
            prompt_text=q_text,
            options=None,
            allow_other=True,
        )
        db.add(pi)
        created_prompts.append(pi)
    db.flush()

    log_event(
        db,
        "game_started",
        session_id=session.id,
        experience_instance_id=experience.id,
        participant_id=participant_id,
        payload={"num_questions": len(questions)},
    )
    db.commit()

    return {"prompts_created": len(created_prompts)}


def get_prompts_for_experience(
    db: Session,
    experience_instance_id: uuid.UUID,
    participant_id: uuid.UUID | None = None,
) -> list[dict]:
    """The questions, oldest first. With a participant, each says whether that
    person has already answered it, so a reload picks up where they left off."""
    prompts = (
        db.query(PromptInstance)
        .filter(
            PromptInstance.experience_instance_id == experience_instance_id,
            PromptInstance.prompt_type == "who_knows_who_self_answer",
        )
        .order_by(PromptInstance.created_at, PromptInstance.id)
        .all()
    )
    answered: set[uuid.UUID] = set()
    if participant_id is not None and prompts:
        answered = {
            row[0]
            for row in db.query(PromptResponse.prompt_instance_id)
            .filter(
                PromptResponse.participant_id == participant_id,
                PromptResponse.prompt_instance_id.in_([p.id for p in prompts]),
            )
            .all()
        }
    return [
        {
            "id": str(p.id),
            "prompt_text": p.prompt_text,
            "prompt_type": p.prompt_type,
            "answered": p.id in answered,
        }
        for p in prompts
    ]


def submit_self_answer(
    db: Session,
    experience: ExperienceInstance,
    prompt_instance_id: uuid.UUID,
    participant_id: uuid.UUID,
    answer_text: str,
) -> dict:
    experience = _lock_experience(db, experience.id)
    _require_member(db, experience, participant_id)
    if experience.game_state != "question_collection":
        raise _conflict("Answers are no longer being collected for this game.")

    min_len = (experience.game_config or {}).get("min_answer_length", 2)
    answer_text = (answer_text or "").strip()
    if len(answer_text) < min_len:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Answer must be at least {min_len} characters",
        )
    if len(answer_text) > MAX_ANSWER_LEN:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Answers can be up to {MAX_ANSWER_LEN} characters",
        )

    # Check prompt belongs to experience
    pi = db.get(PromptInstance, prompt_instance_id)
    if not pi or pi.experience_instance_id != experience.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Prompt not found"
        )

    # Check no duplicate response
    existing = (
        db.query(PromptResponse)
        .filter(
            PromptResponse.prompt_instance_id == prompt_instance_id,
            PromptResponse.participant_id == participant_id,
        )
        .first()
    )
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Already answered this prompt",
        )

    pr = PromptResponse(
        prompt_instance_id=prompt_instance_id,
        participant_id=participant_id,
        other_text=answer_text,
    )
    db.add(pr)
    db.flush()

    log_event(
        db,
        "self_answer_submitted",
        session_id=experience.session_id,
        experience_instance_id=experience.id,
        participant_id=participant_id,
    )

    # Check if all answers are now submitted
    all_done = check_all_answers_submitted(db, experience)
    if all_done:
        log_event(
            db,
            "all_self_answers_completed",
            session_id=experience.session_id,
            experience_instance_id=experience.id,
        )
        transition_state(db, experience, "ready_to_start")
        _generate_rounds(db, experience)

    db.commit()
    return {"ok": True, "all_submitted": all_done}


def check_all_answers_submitted(db: Session, experience: ExperienceInstance) -> bool:
    prompts = (
        db.query(PromptInstance)
        .filter(
            PromptInstance.experience_instance_id == experience.id,
            PromptInstance.prompt_type == "who_knows_who_self_answer",
        )
        .all()
    )
    prompt_ids = [p.id for p in prompts]
    if not prompt_ids:
        return False

    player_ids = [p.id for p in _roster(db, experience)]
    expected = len(player_ids) * len(prompt_ids)

    actual = (
        db.query(PromptResponse)
        .filter(
            PromptResponse.prompt_instance_id.in_(prompt_ids),
            PromptResponse.participant_id.in_(player_ids),
        )
        .count()
    )
    return actual >= expected


# ---------- round generation ----------


def _pick_rounds(responses: list[PromptResponse], max_rounds: int) -> list[PromptResponse]:
    """Choose which answers become rounds.

    Each player gets (as near as possible) the same number of rounds, so nobody
    is the subject of most of the game, then the order is shuffled so that
    nobody comes up twice in a row and there is no pattern to read."""
    by_owner: dict[uuid.UUID, list[PromptResponse]] = defaultdict(list)
    shuffled = list(responses)
    random.shuffle(shuffled)
    for r in shuffled:
        by_owner[r.participant_id].append(r)

    owners = list(by_owner)
    random.shuffle(owners)
    picked: list[PromptResponse] = []
    while len(picked) < max_rounds and any(by_owner[o] for o in owners):
        for o in owners:
            if by_owner[o] and len(picked) < max_rounds:
                picked.append(by_owner[o].pop())
        random.shuffle(owners)

    def no_repeats(seq: list[PromptResponse]) -> bool:
        return all(a.participant_id != b.participant_id for a, b in zip(seq, seq[1:]))

    best = picked
    for _ in range(200):
        random.shuffle(picked)
        if no_repeats(picked):
            return picked
    return best


def _generate_rounds(db: Session, experience: ExperienceInstance) -> None:
    prompts = (
        db.query(PromptInstance)
        .filter(
            PromptInstance.experience_instance_id == experience.id,
            PromptInstance.prompt_type == "who_knows_who_self_answer",
        )
        .all()
    )
    prompt_ids = [p.id for p in prompts]
    player_ids = [p.id for p in _roster(db, experience)]

    min_len = (experience.game_config or {}).get("min_answer_length", 2)
    responses = (
        db.query(PromptResponse)
        .filter(
            PromptResponse.prompt_instance_id.in_(prompt_ids),
            PromptResponse.participant_id.in_(player_ids),
        )
        .all()
    )
    # Filter blanks
    valid = [
        r for r in responses if r.other_text and len(r.other_text.strip()) >= min_len
    ]

    max_rounds = experience.max_rounds or 10
    selected = _pick_rounds(valid, max_rounds)

    for i, resp in enumerate(selected, 1):
        gr = GameRound(
            experience_instance_id=experience.id,
            round_number=i,
            source_prompt_instance_id=resp.prompt_instance_id,
            source_response_id=resp.id,
            answering_participant_id=resp.participant_id,
            status="pending",
        )
        db.add(gr)

    # Activate round 1
    db.flush()
    first_round = (
        db.query(GameRound)
        .filter(
            GameRound.experience_instance_id == experience.id,
            GameRound.round_number == 1,
        )
        .first()
    )
    if first_round:
        first_round.status = "active"
        first_round.started_at = datetime.now(timezone.utc)
        experience.current_round = 1
        experience.max_rounds = len(selected)
        transition_state(db, experience, "round_active")

    log_event(
        db,
        "game_round_created",
        session_id=experience.session_id,
        experience_instance_id=experience.id,
        payload={"total_rounds": len(selected)},
    )
    db.flush()


# ---------- gameplay ----------


def _get_round(
    db: Session, experience: ExperienceInstance, round_id: uuid.UUID
) -> GameRound:
    game_round = db.get(GameRound, round_id)
    if not game_round or game_round.experience_instance_id != experience.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Round not found"
        )
    return game_round


def submit_guess(
    db: Session,
    experience: ExperienceInstance,
    round_id: uuid.UUID,
    guessing_participant_id: uuid.UUID,
    guessed_participant_id: uuid.UUID,
) -> dict:
    experience = _lock_experience(db, experience.id)
    game_round = _get_round(db, experience, round_id)
    if game_round.status != "active" or experience.game_state != "round_active":
        raise _conflict("Round is not active")

    player_ids = {p.id for p in _roster(db, experience)}
    if guessing_participant_id not in player_ids:
        raise _forbidden("You are not part of this game")
    if guessed_participant_id not in player_ids:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="That person is not in this game",
        )

    # Answer owner cannot guess on own round
    if guessing_participant_id == game_round.answering_participant_id:
        raise _forbidden("Cannot guess on your own answer")

    # No duplicate guesses
    existing = (
        db.query(GameGuess)
        .filter(
            GameGuess.game_round_id == round_id,
            GameGuess.guessing_participant_id == guessing_participant_id,
        )
        .first()
    )
    if existing:
        raise _conflict("Already guessed this round")

    is_correct = guessed_participant_id == game_round.answering_participant_id

    guess = GameGuess(
        game_round_id=round_id,
        guessing_participant_id=guessing_participant_id,
        guessed_participant_id=guessed_participant_id,
        is_correct=is_correct,
    )
    db.add(guess)
    db.flush()

    log_event(
        db,
        "game_guess_submitted",
        session_id=experience.session_id,
        experience_instance_id=experience.id,
        participant_id=guessing_participant_id,
        payload={"round_number": game_round.round_number, "is_correct": is_correct},
    )

    # Check if all eligible guesses are in
    all_guessed = _check_all_guesses(db, experience, game_round)
    db.commit()

    return {"ok": True, "is_correct": is_correct, "all_guessed": all_guessed}


def _check_all_guesses(
    db: Session, experience: ExperienceInstance, game_round: GameRound
) -> bool:
    eligible = [
        p.id
        for p in _roster(db, experience)
        if p.id != game_round.answering_participant_id
    ]
    guess_count = (
        db.query(GameGuess)
        .filter(
            GameGuess.game_round_id == game_round.id,
            GameGuess.guessing_participant_id.in_(eligible),
        )
        .count()
    )
    return guess_count >= len(eligible)


def reveal_round(
    db: Session,
    experience: ExperienceInstance,
    round_id: uuid.UUID,
    participant_id: uuid.UUID,
) -> dict:
    """The host can reveal at any time; anyone can once everyone has guessed,
    so a host who stepped away does not freeze the game."""
    experience = _lock_experience(db, experience.id)
    _require_member(db, experience, participant_id)
    game_round = _get_round(db, experience, round_id)

    if experience.game_state != "round_active" or game_round.status != "active":
        raise _conflict("This round has already been revealed.")
    if game_round.round_number != experience.current_round:
        raise _conflict("That is not the current round.")

    if not _is_host(db, experience, participant_id) and not _check_all_guesses(
        db, experience, game_round
    ):
        raise _forbidden("Only the host can reveal before everyone has guessed")

    game_round.status = "revealed"
    game_round.revealed_at = datetime.now(timezone.utc)
    transition_state(db, experience, "round_reveal")

    log_event(
        db,
        "game_round_revealed",
        session_id=experience.session_id,
        experience_instance_id=experience.id,
        payload={"round_number": game_round.round_number},
    )
    db.commit()

    return {"ok": True}


def advance_round(
    db: Session,
    experience: ExperienceInstance,
    round_id: uuid.UUID,
    participant_id: uuid.UUID,
) -> dict:
    experience = _lock_experience(db, experience.id)
    _require_member(db, experience, participant_id)
    if not _is_host(db, experience, participant_id):
        raise _forbidden("Only the host can move to the next round")

    current_round = _get_round(db, experience, round_id)
    if experience.game_state != "round_reveal" or current_round.status != "revealed":
        raise _conflict("Reveal the answer before moving on.")

    current_round.status = "completed"

    next_round_number = current_round.round_number + 1
    is_last = next_round_number > experience.max_rounds

    if is_last:
        transition_state(db, experience, "leaderboard")
        log_event(
            db,
            "game_completed",
            session_id=experience.session_id,
            experience_instance_id=experience.id,
        )
    else:
        next_round = (
            db.query(GameRound)
            .filter(
                GameRound.experience_instance_id == experience.id,
                GameRound.round_number == next_round_number,
            )
            .first()
        )
        if next_round:
            next_round.status = "active"
            next_round.started_at = datetime.now(timezone.utc)
        experience.current_round = next_round_number
        transition_state(db, experience, "round_active")
        log_event(
            db,
            "game_round_started",
            session_id=experience.session_id,
            experience_instance_id=experience.id,
            payload={"round_number": next_round_number},
        )

    db.commit()
    return {"ok": True, "is_last": is_last}


# ---------- replay ----------


def _add_present(experience: ExperienceInstance, participant_id: uuid.UUID) -> bool:
    """Mark a participant as being in this game's lobby. Returns True if new.

    The experience row must be locked by the caller."""
    ids = list(experience.present_participant_ids or [])
    if str(participant_id) in ids:
        return False
    ids.append(str(participant_id))
    experience.present_participant_ids = ids  # new list so the change is saved
    experience.state_version = (experience.state_version or 0) + 1
    return True


def _newest_child(db: Session, experience_id: uuid.UUID) -> ExperienceInstance | None:
    return (
        db.query(ExperienceInstance)
        .filter(
            ExperienceInstance.parent_experience_instance_id == experience_id,
            ExperienceInstance.experience_type == "who_knows_who",
        )
        .order_by(ExperienceInstance.created_at.desc(), ExperienceInstance.id)
        .first()
    )


def replay_game(
    db: Session,
    experience: ExperienceInstance,
    participant_id: uuid.UUID | None = None,
) -> dict:
    """"Play again".

    The first person to come back opens the next lobby and everyone else who
    comes back joins that same one (so the group is never split across several
    new games); anyone who does not come back is simply not in it. Safe to
    repeat, and safe from a stale results link: the call always lands in the
    newest game of this chain. Without a participant, everyone in the session
    is added, which keeps older clients that call the bare endpoint working."""
    if participant_id is not None:
        _require_session_member(db, experience, participant_id)

    # Walk to the newest game, locking each row on the way (parent before child)
    # so two simultaneous returns cannot both open a lobby.
    current = experience
    for _ in range(100):
        tail = _lock_experience(db, current.id)
        child = _newest_child(db, tail.id)
        if child is None:
            break
        current = child
    else:  # pragma: no cover - a chain this long means corrupt data
        raise _conflict("Couldn't find the current game.")

    if tail.game_state in ("leaderboard", "completed"):
        tail = _new_replay_experience(db, tail)
    elif tail.present_participant_ids is None:
        raise _conflict("This game isn't finished yet.")
    elif tail.game_state != "lobby":
        raise _conflict("The next game has already started.")

    if participant_id is not None:
        _add_present(tail, participant_id)
    else:
        for p in _session_members(db, tail):
            _add_present(tail, p.id)

    session = db.get(SessionModel, tail.session_id)
    result = {
        "experience_instance_id": str(tail.id),
        "game_state": tail.game_state,
        "join_code": session.join_code,
        "share_url": generate_share_url(tail.id, session.join_code),
    }
    db.commit()
    return result


def _session_members(db: Session, experience: ExperienceInstance) -> list[Participant]:
    return session_participants(db, experience.session_id)


def _require_session_member(
    db: Session, experience: ExperienceInstance, participant_id: uuid.UUID
) -> None:
    if not any(p.id == participant_id for p in _session_members(db, experience)):
        raise _forbidden("You are not part of this game")


def _new_replay_experience(
    db: Session, finished: ExperienceInstance
) -> ExperienceInstance:
    config = finished.game_config or DEFAULT_GAME_CONFIG
    new_config = {k: config[k] for k in _CARRY_OVER_CONFIG if k in config}
    for key, value in DEFAULT_GAME_CONFIG.items():
        new_config.setdefault(key, value)
    new_exp = ExperienceInstance(
        session_id=finished.session_id,
        experience_type="who_knows_who",
        game_state="lobby",
        game_config=new_config,
        max_rounds=new_config["max_rounds"],
        current_round=0,
        parent_experience_instance_id=finished.id,
        present_participant_ids=[],
    )
    db.add(new_exp)
    db.flush()
    log_event(
        db,
        "game_replayed",
        session_id=finished.session_id,
        experience_instance_id=new_exp.id,
        payload={"parent_id": str(finished.id)},
    )
    return new_exp


def replay_status(db: Session, experience: ExperienceInstance) -> dict:
    """What the results screen needs to know about the next game."""
    child = _newest_child(db, experience.id)
    total = len(_session_members(db, experience))
    if child is None:
        return {
            "next_experience_id": None,
            "next_game_state": None,
            "returned_ids": [],
            "participant_count": total,
        }
    return {
        "next_experience_id": str(child.id),
        "next_game_state": child.game_state,
        "returned_ids": list(child.present_participant_ids or []),
        "participant_count": total,
    }
