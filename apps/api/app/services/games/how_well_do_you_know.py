"""How Well Do You Know [Person]? game orchestration service."""

from __future__ import annotations

import logging
import random
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, status
from sqlalchemy import exists
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, aliased

from app.db.models.experience import ExperienceInstance
from app.db.models.game_choice import GameChoice
from app.db.models.game_mc_guess import GameMCGuess
from app.db.models.game_round import GameRound
from app.db.models.group import Group
from app.db.models.participant import Participant
from app.db.models.prompt import PromptInstance
from app.db.models.session import Session as SessionModel, SessionParticipant
from app.services.games.hwdyk_questions import (
    select_questions,
    format_question_self,
    format_question_other,
)
from app.services.games.sharing import generate_join_code, generate_share_url
from app.services.games.hwdyk_common import (
    DEFAULT_GAME_CONFIG,
    CORRECT_POINTS,
    FOOL_POINTS,
    GUESS_GRACE_SECONDS,
    GUESS_SECONDS,
    MAX_CHOICE_LEN,
    MAX_REGENERATIONS,
    clean_text as _clean_text,
    conflict as _conflict,
    lock_experience as _lock_experience,
    norm as _norm,
    unique_wrong_answers as _unique_wrong_answers,
)
from app.services.games import hwdyk_phases as phases
from app.services.games.state import transition_state
from app.services.llm.client import call_llm_json
from app.services.llm.prompts import (
    DISTRACTOR_GENERATION_SYSTEM,
    DISTRACTOR_GENERATION_USER,
)
from app.services.llm.schemas import distractor_generation_schema
from app.services.telemetry.events import log_event

logger = logging.getLogger(__name__)



# ---------- helpers ----------


def _session_participants(db: Session, session_id: uuid.UUID) -> list[Participant]:
    """Everyone who has ever joined this session, in join order."""
    links = (
        db.query(SessionParticipant)
        .filter(SessionParticipant.session_id == session_id)
        .all()
    )
    pids = [l.participant_id for l in links]
    if not pids:
        return []
    return (
        db.query(Participant)
        .filter(Participant.id.in_(pids))
        .order_by(Participant.created_at, Participant.id)
        .all()
    )


def _get_participants(db: Session, experience: ExperienceInstance) -> list[Participant]:
    """The players in *this* game.

    A replay lobby only contains the people who came back for it
    (``present_participant_ids``); any other game has the whole session."""
    everyone = _session_participants(db, experience.session_id)
    present = experience.present_participant_ids
    if present is None:
        return everyone
    keep = set(present)
    return [p for p in everyone if str(p.id) in keep]


def _effective_host(
    db: Session, experience: ExperienceInstance
) -> Participant | None:
    """The host of this game: the session's host while they are in it, otherwise
    the longest-standing player who is, so a replay never ends up host-less."""
    participants = _get_participants(db, experience)
    host = next((p for p in participants if p.role == "host"), None)
    if host or experience.present_participant_ids is None:
        return host
    return participants[0] if participants else None


def _verify_host(
    db: Session,
    participant_id: uuid.UUID,
    experience: ExperienceInstance | None = None,
) -> Participant:
    if experience is None:
        host = db.get(Participant, participant_id)
        if not host or host.role != "host":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only the host can perform this action",
            )
        return host
    # A host of some other game must not be able to act on this one.
    host = _effective_host(db, experience)
    if not host or host.id != participant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the host can perform this action",
        )
    return host


def _verify_main_person(
    experience: ExperienceInstance, participant_id: uuid.UUID
) -> None:
    if experience.main_person_participant_id != participant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the main person can perform this action",
        )


# ---------- create / join ----------


def create_game(
    db: Session,
    user_id: uuid.UUID | None,
    display_name: str,
    mode: str = "default",
    num_questions: int = 5,
    intimacy_level: str = "personal",
) -> dict:
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
        join_type="authenticated" if user_id else "anonymous",
    )
    db.add(host)
    db.flush()

    join_code = generate_join_code()

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

    config = {
        "mode": mode,
        "num_questions": num_questions,
        "intimacy_level": intimacy_level,
        "min_answer_length": DEFAULT_GAME_CONFIG["min_answer_length"],
    }
    experience = ExperienceInstance(
        session_id=session.id,
        experience_type="how_well_do_you_know",
        game_state="lobby",
        game_config=config,
        max_rounds=num_questions,
        current_round=0,
    )
    db.add(experience)
    db.flush()

    share_url = generate_share_url(
        experience.id, join_code, game_slug="how-well-do-you-know"
    )

    log_event(
        db,
        "game_created",
        session_id=session.id,
        experience_instance_id=experience.id,
        participant_id=host.id,
        payload={"game_slug": "how-well-do-you-know", "mode": mode},
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


def join_game(
    db: Session,
    join_code: str,
    display_name: str,
    user_id: uuid.UUID | None = None,
    join_mode: str = "anonymous",
) -> dict:
    session = db.query(SessionModel).filter(SessionModel.join_code == join_code).first()
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Invalid join code"
        )

    # The join code outlives a single game, so people joining land in the
    # newest game of the session: the one no later game follows.
    later = aliased(ExperienceInstance)
    experience = (
        db.query(ExperienceInstance)
        .filter(
            ExperienceInstance.session_id == session.id,
            ExperienceInstance.experience_type == "how_well_do_you_know",
            ~exists().where(later.parent_experience_instance_id == ExperienceInstance.id),
        )
        .order_by(ExperienceInstance.created_at.desc(), ExperienceInstance.id)
        .first()
    )
    if not experience:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Game not found"
        )
    if experience.game_state not in (
        "lobby",
        "main_person_answering",
        "ai_generating_choices",
        "main_person_reviewing_choices",
        "players_submitting_fake_answers",
        "ready_to_start",
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Game has already started — cannot join",
        )

    # A replay lobby keeps its own roster, so settle (under lock) that it is
    # still a lobby before anyone is added to it.
    locked = None
    if experience.present_participant_ids is not None:
        locked = _lock_experience(db, experience.id)
        if locked.game_state != "lobby":
            raise _conflict(
                "game_in_progress",
                "The next game has already started — you can join the one after.",
            )

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

    if locked is not None:
        # Joining a replay lobby: the newcomer is in it from the start.
        _add_present(locked, participant.id)

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


# ---------- lobby ----------


def get_lobby_payload(db: Session, experience: ExperienceInstance) -> dict:
    session = db.get(SessionModel, experience.session_id)
    participants = _get_participants(db, experience)
    host = _effective_host(db, experience)
    config = experience.game_config or DEFAULT_GAME_CONFIG

    progress = None
    if experience.game_state == phases.ANSWERING:
        progress = {
            "answered": phases.answered_count(db, experience),
            "total": int(config.get("num_questions", 5)),
        }

    # In a replay lobby, also say who has not come back yet and who was in the
    # hot seat last time, so the host can see the room and rotate the turn.
    absent: list[dict] = []
    previous_main = None
    if experience.present_participant_ids is not None:
        here = {p.id for p in participants}
        absent = [
            {"id": str(p.id), "display_name": p.display_name}
            for p in _session_participants(db, experience.session_id)
            if p.id not in here
        ]
    if experience.parent_experience_instance_id:
        parent = db.get(ExperienceInstance, experience.parent_experience_instance_id)
        if parent and parent.main_person_participant_id:
            previous_main = str(parent.main_person_participant_id)

    return {
        "experience_id": str(experience.id),
        "game_state": experience.game_state,
        "state_version": experience.state_version or 0,
        # Countdown for timed prep phases (None otherwise), measured by the server.
        "phase": phases.phase_info(experience),
        "progress": progress,
        # Set when a timed-out/invalid preparation sent everyone back to the lobby.
        "notice": config.get("notice"),
        "game_slug": "how-well-do-you-know",
        "mode": config.get("mode", "default"),
        "join_code": session.join_code,
        "share_url": generate_share_url(
            experience.id, session.join_code, game_slug="how-well-do-you-know"
        ),
        "host_id": str(host.id) if host else None,
        "main_person_participant_id": (
            str(experience.main_person_participant_id)
            if experience.main_person_participant_id
            else None
        ),
        "is_replay": experience.present_participant_ids is not None,
        "previous_main_person_id": previous_main,
        "participants": [
            {
                "id": str(p.id),
                "display_name": p.display_name,
                "role": "host" if host and p.id == host.id else "guest",
            }
            for p in participants
        ],
        "absent_participants": absent,
    }


def select_main_person(
    db: Session,
    experience: ExperienceInstance,
    host_participant_id: uuid.UUID,
    main_person_participant_id: uuid.UUID,
) -> None:
    _verify_host(db, host_participant_id, experience)
    experience = _lock_experience(db, experience.id)
    if experience.game_state != "lobby":
        # Changing the hot seat mid-setup would orphan the answers already given.
        raise _conflict(
            "setup_in_progress", "The main person can only be changed from the lobby."
        )

    # Verify main person is a participant in this game
    participants = _get_participants(db, experience)
    pids = {p.id for p in participants}
    if main_person_participant_id not in pids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Selected person is not a participant in this game",
        )

    experience.main_person_participant_id = main_person_participant_id
    db.flush()
    db.commit()


# ---------- start setup ----------


def start_setup(
    db: Session,
    experience: ExperienceInstance,
    host_participant_id: uuid.UUID,
) -> dict:
    _verify_host(db, host_participant_id, experience)
    # Lock so a double click can't create the question set twice.
    experience = _lock_experience(db, experience.id)

    if not experience.main_person_participant_id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Main person must be selected before starting",
        )

    # Idempotent: if already in main_person_answering, return existing prompts count
    if experience.game_state == "main_person_answering":
        existing_count = (
            db.query(PromptInstance)
            .filter(
                PromptInstance.experience_instance_id == experience.id,
                PromptInstance.prompt_type == "hwdyk_main_person_question",
            )
            .count()
        )
        db.commit()
        return {"prompts_created": existing_count}

    players = _get_participants(db, experience)
    if len(players) < 2 or experience.main_person_participant_id not in {
        p.id for p in players
    }:
        # The hot seat needs at least one other player to do the guessing.
        raise _conflict(
            "not_enough_players",
            "You need at least two players in the lobby to start.",
        )

    transition_state(db, experience, "main_person_answering")
    phases.start_phase_clock(experience, phases.answer_seconds(experience))

    config = dict(experience.game_config or DEFAULT_GAME_CONFIG)
    config.pop("notice", None)  # a fresh attempt clears the last failure message
    experience.game_config = config
    num_q = config.get("num_questions", 5)
    questions = select_questions(num_q)

    session = db.get(SessionModel, experience.session_id)

    created_prompts = []
    for idx, q_text in enumerate(questions):
        pi = PromptInstance(
            session_id=session.id,
            experience_instance_id=experience.id,
            prompt_type="hwdyk_main_person_question",
            prompt_text=q_text,
            options=None,
            allow_other=True,
            round_number=idx + 1,
        )
        db.add(pi)
        created_prompts.append(pi)
    db.flush()

    log_event(
        db,
        "hwdyk_setup_started",
        session_id=session.id,
        experience_instance_id=experience.id,
        participant_id=host_participant_id,
        payload={"num_questions": len(questions)},
    )
    db.commit()

    return {"prompts_created": len(created_prompts)}


# ---------- main person answer collection ----------


def get_main_person_questions(db: Session, experience_id: uuid.UUID) -> list[dict]:
    prompts = (
        db.query(PromptInstance)
        .filter(
            PromptInstance.experience_instance_id == experience_id,
            PromptInstance.prompt_type == "hwdyk_main_person_question",
        )
        .order_by(PromptInstance.round_number)
        .all()
    )
    # Answers are saved one by one, so a reload resumes where the main person
    # left off instead of asking questions they already answered.
    answered = {
        r.source_prompt_instance_id
        for r in db.query(GameRound).filter(
            GameRound.experience_instance_id == experience_id
        )
    }
    return [
        {
            "id": str(p.id),
            "prompt_text": format_question_self(p.prompt_text),
            "round_number": p.round_number,
            "answered": p.id in answered,
        }
        for p in prompts
    ]


def submit_main_person_answer(
    db: Session,
    experience: ExperienceInstance,
    prompt_instance_id: uuid.UUID,
    participant_id: uuid.UUID,
    answer_text: str,
) -> dict:
    """Save one answer (each is kept as soon as it is submitted).

    Returns ``needs_generation`` when this was the last answer in default mode:
    the caller should then run :func:`hwdyk_phases.run_generation` (as a
    background task) so the request returns immediately."""
    _verify_main_person(experience, participant_id)

    config = experience.game_config or DEFAULT_GAME_CONFIG
    min_len = config.get("min_answer_length", 3)
    cleaned_answer = _clean_text(answer_text)
    if len(cleaned_answer) < min_len:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Answer must be at least {min_len} characters",
        )
    if len(cleaned_answer) > MAX_CHOICE_LEN:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Answer must be {MAX_CHOICE_LEN} characters or fewer",
        )

    experience = _lock_experience(db, experience.id)
    _verify_main_person(experience, participant_id)
    if experience.game_state != phases.ANSWERING:
        raise _conflict(
            "answering_closed",
            "The time for answering questions is over."
            if experience.game_state != "lobby"
            else "Setup was reset. Wait for the host to start again.",
        )

    prompt = db.get(PromptInstance, prompt_instance_id)
    if (
        not prompt
        or prompt.experience_instance_id != experience.id
        or prompt.prompt_type != "hwdyk_main_person_question"
    ):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Prompt not found"
        )

    # Check if already answered
    existing_round = (
        db.query(GameRound)
        .filter(
            GameRound.experience_instance_id == experience.id,
            GameRound.source_prompt_instance_id == prompt_instance_id,
        )
        .first()
    )
    if existing_round:
        raise _conflict("already_answered", "This question has already been answered")

    # Create GameRound
    game_round = GameRound(
        experience_instance_id=experience.id,
        round_number=prompt.round_number or 1,
        source_prompt_instance_id=prompt_instance_id,
        source_response_id=None,
        answering_participant_id=participant_id,
        status="setup",
        question_text=prompt.prompt_text,
        timer_duration=GUESS_SECONDS,
    )
    db.add(game_round)
    db.flush()

    # Create correct choice
    correct_choice = GameChoice(
        game_round_id=game_round.id,
        choice_text=cleaned_answer,
        is_correct=True,
        source_type="main_person",
        created_by_participant_id=participant_id,
    )
    db.add(correct_choice)
    db.flush()

    game_round.correct_choice_id = correct_choice.id
    db.flush()

    num_q = config.get("num_questions", 5)
    all_answered = phases.answered_count(db, experience) >= num_q

    needs_generation = False
    if all_answered:
        needs_generation = phases.finish_answering(db, experience) == "generate"
    else:
        db.commit()

    return {
        "ok": True,
        "all_answered": all_answered,
        "needs_generation": needs_generation,
    }


# ---------- Default Mode: review / edit choices ----------

REVIEW_STATE = "main_person_reviewing_choices"


def get_review_data(
    db: Session, experience_id: uuid.UUID, participant_id: uuid.UUID
) -> list[dict]:
    experience = db.get(ExperienceInstance, experience_id)
    if not experience:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    _verify_main_person(experience, participant_id)

    regen_counts = (experience.game_config or {}).get("regenerate_counts", {})

    rounds = (
        db.query(GameRound)
        .filter(GameRound.experience_instance_id == experience_id)
        .order_by(GameRound.round_number)
        .all()
    )

    result = []
    for r in rounds:
        choices = (
            db.query(GameChoice)
            .filter(GameChoice.game_round_id == r.id)
            .order_by(GameChoice.is_correct.desc(), GameChoice.created_at, GameChoice.id)
            .all()
        )
        result.append(
            {
                "round_id": str(r.id),
                "round_number": r.round_number,
                "question_text": format_question_self(r.question_text),
                "choices": [
                    {
                        "id": str(c.id),
                        "text": c.choice_text,
                        "is_correct": c.is_correct,
                        "source_type": c.source_type,
                        "revision": c.revision or 0,
                        "regenerations_used": int(regen_counts.get(str(c.id), 0)),
                    }
                    for c in choices
                ],
            }
        )
    return result


def _load_editable_choice(
    db: Session, experience: ExperienceInstance, choice_id: uuid.UUID
) -> GameChoice:
    """Load a wrong-answer choice that the main person may still change.

    Must be called with the experience row locked (see ``_lock_experience``)."""
    if experience.game_state != REVIEW_STATE:
        raise _conflict(
            "choices_locked",
            "These answer choices can't be changed any more.",
        )

    choice = (
        db.query(GameChoice)
        .filter(GameChoice.id == choice_id)
        .with_for_update()
        .populate_existing()
        .first()
    )
    game_round = db.get(GameRound, choice.game_round_id) if choice else None
    if (
        not choice
        or not game_round
        or game_round.experience_instance_id != experience.id
    ):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Choice not found"
        )
    if choice.is_correct:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot edit the correct answer through this endpoint",
        )
    return choice


def _round_texts(db: Session, round_id: uuid.UUID, exclude_id: uuid.UUID) -> list[str]:
    return [
        t
        for (t,) in db.query(GameChoice.choice_text)
        .filter(GameChoice.game_round_id == round_id, GameChoice.id != exclude_id)
        .all()
    ]


def edit_choice(
    db: Session,
    experience: ExperienceInstance,
    choice_id: uuid.UUID,
    participant_id: uuid.UUID,
    new_text: str,
    expected_revision: int | None = None,
) -> dict:
    """Save the main person's edit of a wrong answer.

    ``expected_revision`` is the revision the client last saw. If the choice has
    moved on since (another tab, a regeneration, a retried request arriving
    late) the write is refused with 409 instead of silently overwriting."""
    experience = _lock_experience(db, experience.id)
    _verify_main_person(experience, participant_id)
    choice = _load_editable_choice(db, experience, choice_id)

    cleaned = _clean_text(new_text)
    if not cleaned:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Choice text cannot be blank",
        )
    if len(cleaned) > MAX_CHOICE_LEN:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Choice text must be {MAX_CHOICE_LEN} characters or fewer",
        )

    if expected_revision is not None and expected_revision != (choice.revision or 0):
        raise _conflict(
            "stale_revision",
            "This answer changed since you loaded it. Reload to see the latest.",
        )

    # Saving the text it already has is a no-op (idempotent retries).
    if cleaned == choice.choice_text:
        view = _choice_view(choice)
        db.commit()  # nothing changed; this just releases the row locks
        return view

    if _norm(cleaned) in {_norm(t) for t in _round_texts(db, choice.game_round_id, choice.id)}:
        raise _conflict(
            "duplicate_choice",
            "Another choice for this question already says that.",
        )

    if choice.original_ai_text is None and choice.source_type in (
        "ai_generated",
        "ai_fallback",
    ):
        choice.original_ai_text = choice.choice_text
    choice.choice_text = cleaned
    choice.source_type = "main_person_edited"
    choice.revision = (choice.revision or 0) + 1
    db.flush()
    db.commit()
    return _choice_view(choice)


def _choice_view(choice: GameChoice) -> dict:
    return {
        "id": str(choice.id),
        "text": choice.choice_text,
        "source_type": choice.source_type,
        "revision": choice.revision or 0,
    }


def regenerate_choice(
    db: Session,
    experience: ExperienceInstance,
    choice_id: uuid.UUID,
    participant_id: uuid.UUID,
    expected_revision: int | None = None,
) -> dict:
    _verify_main_person(experience, participant_id)

    # Phase A: validate and snapshot, then release locks before the slow AI call.
    experience = _lock_experience(db, experience.id)
    choice = _load_editable_choice(db, experience, choice_id)
    revision_seen = choice.revision or 0
    if expected_revision is not None and expected_revision != revision_seen:
        raise _conflict(
            "stale_revision",
            "This answer changed since you loaded it. Reload to see the latest.",
        )

    config = experience.game_config or DEFAULT_GAME_CONFIG
    choice_key = str(choice_id)
    current_count = int(config.get("regenerate_counts", {}).get(choice_key, 0))
    if current_count >= MAX_REGENERATIONS:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Limit of {MAX_REGENERATIONS} AI regenerations per answer reached",
        )

    game_round = db.get(GameRound, choice.game_round_id)
    correct_choice = (
        db.query(GameChoice)
        .filter(
            GameChoice.game_round_id == game_round.id,
            GameChoice.is_correct.is_(True),
        )
        .first()
    )
    intimacy = config.get("intimacy_level", "personal")
    existing_texts = _round_texts(db, game_round.id, choice_id)
    existing_texts.append(choice.choice_text)
    question_text = format_question_self(game_round.question_text)
    correct_text = correct_choice.choice_text
    db.commit()  # nothing changed; this just releases the row locks

    schema = distractor_generation_schema()
    # Override minItems since we only ask for 1 distractor here
    regen_schema = {**schema}
    regen_schema["properties"] = {
        **schema["properties"],
        "wrong_answers": {**schema["properties"]["wrong_answers"], "minItems": 1},
    }
    candidates: list = []
    try:
        result = call_llm_json(
            system_prompt=DISTRACTOR_GENERATION_SYSTEM,
            user_prompt=DISTRACTOR_GENERATION_USER.format(
                question_text=question_text,
                correct_answer=correct_text,
                num_distractors=1,
                intimacy_level=intimacy,
                person_context=f"Avoid these existing answers: {existing_texts}",
            ),
            json_schema=regen_schema,
            temperature=0.9,
        )
        candidates = list(result.get("wrong_answers", []))
    except Exception:
        logger.exception("Failed to regenerate distractor")

    fresh = _unique_wrong_answers(candidates, taken=[correct_text, *existing_texts], limit=1)
    if not fresh:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Couldn't come up with a new answer — please try again",
        )

    # Phase B: apply only if nothing changed while the AI was thinking.
    experience = _lock_experience(db, experience.id)
    choice = _load_editable_choice(db, experience, choice_id)
    if (choice.revision or 0) != revision_seen:
        raise _conflict(
            "stale_revision",
            "You changed this answer while a new one was being generated, so it was kept.",
        )
    # Re-check against the current round contents (a sibling may have been edited).
    if _norm(fresh[0]) in {
        _norm(t) for t in _round_texts(db, choice.game_round_id, choice.id)
    }:
        raise _conflict("duplicate_choice", "That suggestion is already used — try again.")

    config = experience.game_config or DEFAULT_GAME_CONFIG
    regen_counts = dict(config.get("regenerate_counts", {}))
    used = int(regen_counts.get(choice_key, 0))
    if used >= MAX_REGENERATIONS:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Limit of {MAX_REGENERATIONS} AI regenerations per answer reached",
        )

    if choice.original_ai_text is None:
        choice.original_ai_text = choice.choice_text
    choice.choice_text = fresh[0]
    choice.source_type = "ai_generated"
    choice.revision = revision_seen + 1

    regen_counts[choice_key] = used + 1
    updated_config = dict(config)
    updated_config["regenerate_counts"] = regen_counts
    experience.game_config = updated_config

    db.flush()
    db.commit()

    view = _choice_view(choice)
    view["new_text"] = choice.choice_text  # kept for older clients
    view["regenerations_used"] = used + 1
    view["regenerations_remaining"] = MAX_REGENERATIONS - (used + 1)
    return view


def confirm_choices(
    db: Session,
    experience: ExperienceInstance,
    participant_id: uuid.UUID,
    expected_revisions: dict[str, int] | None = None,
) -> None:
    """Lock the reviewed choices and move on to the live game.

    ``expected_revisions`` maps choice id -> revision the client has saved. If
    any differs from the database the confirm is refused, so the game can never
    start with answers other than the ones on the main person's screen."""
    _verify_main_person(experience, participant_id)
    experience = _lock_experience(db, experience.id)
    _verify_main_person(experience, participant_id)

    # Idempotent: a retried confirm after success is a success.
    if experience.game_state == "ready_to_start":
        db.commit()
        return
    if experience.game_state != REVIEW_STATE:
        raise _conflict(
            "choices_locked", "These answer choices can't be confirmed right now."
        )

    phases.lock_in_choices(db, experience, expected_revisions)


# ---------- Party Mode: fake answer collection ----------


def get_fake_answer_questions(
    db: Session, experience_id: uuid.UUID, participant_id: uuid.UUID
) -> list[dict]:
    experience = db.get(ExperienceInstance, experience_id)
    if not experience:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")

    if experience.main_person_participant_id == participant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Main person does not submit fake answers",
        )

    main_person = db.get(Participant, experience.main_person_participant_id)
    main_name = main_person.display_name if main_person else None

    rounds = (
        db.query(GameRound)
        .filter(GameRound.experience_instance_id == experience_id)
        .order_by(GameRound.round_number)
        .all()
    )

    result = []
    for r in rounds:
        already_submitted = (
            db.query(GameChoice)
            .filter(
                GameChoice.game_round_id == r.id,
                GameChoice.source_type == "player_fake",
                GameChoice.created_by_participant_id == participant_id,
            )
            .first()
            is not None
        )
        q_display = (
            format_question_other(r.question_text, main_name)
            if main_name
            else format_question_self(r.question_text)
        )
        result.append(
            {
                "round_id": str(r.id),
                "question_text": q_display,
                "round_number": r.round_number,
                "already_submitted": already_submitted,
            }
        )
    return result


def submit_fake_answer(
    db: Session,
    experience: ExperienceInstance,
    round_id: uuid.UUID,
    participant_id: uuid.UUID,
    fake_text: str,
) -> dict:
    if experience.main_person_participant_id == participant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Main person cannot submit fake answers",
        )

    fake_text = _clean_text(fake_text)
    if not fake_text:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Fake answer cannot be blank",
        )
    if len(fake_text) > 80:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Fake answer must be 80 characters or fewer",
        )

    experience = _lock_experience(db, experience.id)
    if experience.game_state != "players_submitting_fake_answers":
        raise _conflict(
            "fake_answers_closed", "Fake answers are no longer being collected."
        )

    game_round = db.get(GameRound, round_id)
    if not game_round or game_round.experience_instance_id != experience.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Round not found"
        )

    # Check duplicate submission by this participant
    existing = (
        db.query(GameChoice)
        .filter(
            GameChoice.game_round_id == round_id,
            GameChoice.source_type == "player_fake",
            GameChoice.created_by_participant_id == participant_id,
        )
        .first()
    )
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="You already submitted a fake answer for this question",
        )

    # Must not match the correct answer or any answer already on the card
    # (the database rejects two identical choice texts in a round).
    taken = [
        t
        for (t,) in db.query(GameChoice.choice_text)
        .filter(GameChoice.game_round_id == round_id)
        .all()
    ]
    correct_choice = (
        db.query(GameChoice)
        .filter(
            GameChoice.game_round_id == round_id,
            GameChoice.is_correct.is_(True),
        )
        .first()
    )
    if correct_choice and _norm(fake_text) == _norm(correct_choice.choice_text):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Your fake answer matches the correct answer",
        )
    if _norm(fake_text) in {_norm(t) for t in taken}:
        raise _conflict(
            "duplicate_choice",
            "Someone already used that answer. Try something different.",
        )

    choice = GameChoice(
        game_round_id=round_id,
        choice_text=fake_text,
        is_correct=False,
        source_type="player_fake",
        created_by_participant_id=participant_id,
    )
    db.add(choice)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise _conflict(
            "duplicate_choice",
            "Someone already used that answer. Try something different.",
        )
    db.commit()

    return {"ok": True}


def get_fake_answer_progress(db: Session, experience_id: uuid.UUID) -> dict:
    experience = db.get(ExperienceInstance, experience_id)
    if not experience:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")

    rounds = (
        db.query(GameRound)
        .filter(GameRound.experience_instance_id == experience_id)
        .order_by(GameRound.round_number)
        .all()
    )

    participants = _get_participants(db, experience)
    non_main = [
        p for p in participants if p.id != experience.main_person_participant_id
    ]

    round_progress = []
    for r in rounds:
        fake_count = (
            db.query(GameChoice)
            .filter(
                GameChoice.game_round_id == r.id,
                GameChoice.source_type == "player_fake",
            )
            .count()
        )
        round_progress.append(
            {
                "round_id": str(r.id),
                "round_number": r.round_number,
                "fake_count": fake_count,
            }
        )

    player_progress = []
    for p in non_main:
        submitted_count = (
            db.query(GameChoice)
            .filter(
                GameChoice.source_type == "player_fake",
                GameChoice.created_by_participant_id == p.id,
                GameChoice.game_round_id.in_([r.id for r in rounds]),
            )
            .count()
        )
        player_progress.append(
            {
                "participant_id": str(p.id),
                "display_name": p.display_name,
                "submitted_count": submitted_count,
                "total": len(rounds),
            }
        )

    return {"rounds": round_progress, "players": player_progress}


def lock_party_mode(
    db: Session,
    experience: ExperienceInstance,
    host_participant_id: uuid.UUID,
) -> None:
    _verify_host(db, host_participant_id, experience)
    experience = _lock_experience(db, experience.id)
    if experience.game_state == "ready_to_start":
        db.commit()  # already locked; a repeated click is a no-op
        return
    if experience.game_state != "players_submitting_fake_answers":
        raise _conflict("not_collecting_fakes", "Fake answers aren't being collected.")

    config = experience.game_config or DEFAULT_GAME_CONFIG
    intimacy = config.get("intimacy_level", "personal")

    rounds = (
        db.query(GameRound)
        .filter(GameRound.experience_instance_id == experience.id)
        .order_by(GameRound.round_number)
        .all()
    )

    schema = distractor_generation_schema()

    for game_round in rounds:
        correct_choice = (
            db.query(GameChoice)
            .filter(
                GameChoice.game_round_id == game_round.id,
                GameChoice.is_correct.is_(True),
            )
            .first()
        )
        fake_choices = (
            db.query(GameChoice)
            .filter(
                GameChoice.game_round_id == game_round.id,
                GameChoice.source_type == "player_fake",
            )
            .all()
        )

        # If fewer than 2 fakes, generate AI fallback
        if len(fake_choices) < 2:
            needed = 2 - len(fake_choices)
            try:
                result = call_llm_json(
                    system_prompt=DISTRACTOR_GENERATION_SYSTEM,
                    user_prompt=DISTRACTOR_GENERATION_USER.format(
                        question_text=format_question_self(game_round.question_text),
                        correct_answer=correct_choice.choice_text,
                        num_distractors=needed,
                        intimacy_level=intimacy,
                        person_context="Not available",
                    ),
                    json_schema=schema,
                    temperature=0.8,
                )
                taken = [correct_choice.choice_text] + [
                    c.choice_text for c in fake_choices
                ]
                for ans in _unique_wrong_answers(
                    list(result.get("wrong_answers", [])), taken=taken, limit=needed
                ):
                    db.add(
                        GameChoice(
                            game_round_id=game_round.id,
                            choice_text=ans,
                            is_correct=False,
                            source_type="ai_fallback",
                        )
                    )
            except Exception:
                logger.exception("Failed AI fallback for round %s", game_round.id)

        # Assemble final choices: correct + up to 5 fakes (max 6 total)
        all_wrong = (
            db.query(GameChoice)
            .filter(
                GameChoice.game_round_id == game_round.id,
                GameChoice.is_correct.is_(False),
            )
            .all()
        )
        if len(all_wrong) > 5:
            selected_wrong = random.sample(all_wrong, 5)
            # Remove unselected from display (keep in DB but no display_order)
            selected_ids = {c.id for c in selected_wrong}
            for c in all_wrong:
                if c.id not in selected_ids:
                    c.display_order = None
        else:
            selected_wrong = all_wrong

        # Shuffle display order
        all_display = [correct_choice] + selected_wrong
        indices = list(range(len(all_display)))
        random.shuffle(indices)
        for i, c in enumerate(all_display):
            c.display_order = indices[i]

    db.flush()
    transition_state(db, experience, "ready_to_start")
    db.commit()


# ---------- live gameplay ----------
#
# Each round has a server-owned guessing window (``guess_deadline_at``, 30s by
# default) and a roster of eligible guessers frozen when the round starts. A
# round ends exactly once, by whichever comes first: every eligible player has
# guessed, or the deadline passes. Both paths go through ``_reveal_locked`` under
# the experience row lock, so a simultaneous last guess, timeout poll and manual
# reveal cannot reveal twice or award anything twice.


def _now() -> datetime:
    return datetime.now(timezone.utc)


def guess_seconds(experience: ExperienceInstance) -> int:
    return int((experience.game_config or {}).get("guess_seconds", GUESS_SECONDS))


def _eligible_ids(db: Session, experience: ExperienceInstance) -> list[str]:
    """Everyone in the game except the main person, in a stable order."""
    return sorted(
        str(p.id)
        for p in _get_participants(db, experience)
        if p.id != experience.main_person_participant_id
    )


def _round_eligible(
    db: Session, experience: ExperienceInstance, game_round: GameRound
) -> list[str]:
    # Rounds started before rosters were frozen fall back to the live roster.
    if game_round.eligible_participant_ids is not None:
        return list(game_round.eligible_participant_ids)
    return _eligible_ids(db, experience)


def _round_deadline(game_round: GameRound) -> datetime | None:
    if game_round.guess_deadline_at is not None:
        return game_round.guess_deadline_at
    if game_round.started_at is not None:
        return game_round.started_at + timedelta(
            seconds=game_round.timer_duration or GUESS_SECONDS
        )
    return None


def _activate_round(
    experience: ExperienceInstance,
    game_round: GameRound,
    eligible: list[str],
    now: datetime,
) -> None:
    seconds = guess_seconds(experience)
    game_round.status = "active"
    game_round.started_at = now
    game_round.timer_duration = seconds
    game_round.guess_deadline_at = now + timedelta(seconds=seconds)
    game_round.eligible_participant_ids = eligible
    game_round.round_locked_at = None
    experience.current_round = game_round.round_number


def _current_round(db: Session, experience: ExperienceInstance) -> GameRound | None:
    return (
        db.query(GameRound)
        .filter(
            GameRound.experience_instance_id == experience.id,
            GameRound.round_number == experience.current_round,
        )
        .populate_existing()
        .first()
    )


def _guessed_ids(db: Session, game_round: GameRound) -> set[str]:
    return {
        str(pid)
        for (pid,) in db.query(GameMCGuess.participant_id).filter(
            GameMCGuess.game_round_id == game_round.id
        )
    }


def start_live_game(
    db: Session,
    experience: ExperienceInstance,
    host_participant_id: uuid.UUID,
) -> None:
    _verify_host(db, host_participant_id, experience)
    experience = _lock_experience(db, experience.id)

    # Idempotent: a double click on "Start" must not restart round 1.
    if experience.game_state == "round_active":
        db.commit()
        return

    first_round = (
        db.query(GameRound)
        .filter(
            GameRound.experience_instance_id == experience.id,
            GameRound.round_number == 1,
        )
        .first()
    )
    if not first_round:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="No rounds found",
        )

    transition_state(db, experience, "round_active")  # 409 unless ready_to_start
    _activate_round(experience, first_round, _eligible_ids(db, experience), _now())
    db.commit()


def get_round_state(db: Session, experience: ExperienceInstance) -> dict:
    """Build full game state payload for HWDYK polling (read-only)."""
    participants = _get_participants(db, experience)
    config = experience.game_config or DEFAULT_GAME_CONFIG

    # Get main person display name for question personalization
    main_person_name = None
    if experience.main_person_participant_id:
        main_person = next(
            (p for p in participants if p.id == experience.main_person_participant_id),
            None,
        )
        if main_person:
            main_person_name = main_person.display_name

    payload: dict = {
        "experience_id": str(experience.id),
        "experience_type": experience.experience_type,
        "game_state": experience.game_state,
        "state_version": experience.state_version or 0,
        "mode": config.get("mode", "default"),
        "current_round": experience.current_round,
        "max_rounds": experience.max_rounds,
        "main_person_participant_id": (
            str(experience.main_person_participant_id)
            if experience.main_person_participant_id
            else None
        ),
        "main_person_display_name": main_person_name,
        "participants": [
            {"id": str(p.id), "display_name": p.display_name, "role": p.role}
            for p in participants
        ],
    }

    if experience.game_state in ("round_active", "round_reveal"):
        game_round = _current_round(db, experience)
        if game_round:
            now = _now()
            deadline = _round_deadline(game_round)
            seconds_remaining = 0.0
            if game_round.status == "active" and deadline is not None:
                seconds_remaining = max(0.0, (deadline - now).total_seconds())

            # Get choices (sorted by display_order)
            choices = (
                db.query(GameChoice)
                .filter(
                    GameChoice.game_round_id == game_round.id,
                    GameChoice.display_order.isnot(None),
                )
                .order_by(GameChoice.display_order)
                .all()
            )

            # Get guesses
            mc_guesses = (
                db.query(GameMCGuess)
                .filter(GameMCGuess.game_round_id == game_round.id)
                .all()
            )

            eligible = _round_eligible(db, experience, game_round)
            guessed = {str(g.participant_id) for g in mc_guesses}

            round_payload: dict = {
                "round_id": str(game_round.id),
                "round_number": game_round.round_number,
                "status": game_round.status,
                "question_text": (
                    format_question_other(game_round.question_text, main_person_name)
                    if main_person_name
                    else format_question_self(game_round.question_text)
                ),
                "question_text_self": format_question_self(game_round.question_text),
                # Server-measured countdown; clients count down from this.
                "seconds_remaining": round(seconds_remaining, 1),
                "time_remaining_seconds": int(seconds_remaining),
                "duration_seconds": game_round.timer_duration or GUESS_SECONDS,
                "deadline_at": deadline.isoformat() if deadline else None,
                "server_now": now.isoformat(),
                "is_locked": game_round.round_locked_at is not None,
                # Who may guess (frozen at round start) and who already has.
                "eligible_participant_ids": eligible,
                "guessed_participant_ids": sorted(guessed & set(eligible)),
                "guesses_submitted": len(guessed & set(eligible)),
                "total_guessers": len(eligible),
            }

            if experience.game_state == "round_active":
                # Hide correct answer during active round
                round_payload["choices"] = [
                    {"id": str(c.id), "text": c.choice_text} for c in choices
                ]
            else:
                # Reveal: show correct + distribution
                round_payload["choices"] = [
                    {
                        "id": str(c.id),
                        "text": c.choice_text,
                        "is_correct": c.is_correct,
                        "source_type": c.source_type,
                        "created_by_participant_id": (
                            str(c.created_by_participant_id)
                            if c.created_by_participant_id
                            else None
                        ),
                    }
                    for c in choices
                ]

                # Distribution: who picked what
                distribution = []
                for c in choices:
                    guessers = [
                        str(g.participant_id)
                        for g in mc_guesses
                        if g.selected_choice_id == c.id
                    ]
                    distribution.append(
                        {
                            "choice_id": str(c.id),
                            "choice_text": c.choice_text,
                            "is_correct": c.is_correct,
                            "guessers": guessers,
                        }
                    )
                round_payload["distribution"] = distribution

            payload["round"] = round_payload

    # Scores in reveal/completed states
    if experience.game_state in ("round_reveal", "completed"):
        payload["scores"] = compute_hwdyk_scores(db, experience.id)

    return payload


def _reveal_locked(
    db: Session,
    experience: ExperienceInstance,
    round_id: uuid.UUID,
    reason: str,
) -> bool:
    """End a round's guessing and show the answer. Exactly-once.

    Caller holds the experience row lock. Returns False (doing nothing) if the
    round was already revealed or is no longer the live round, which is what
    makes concurrent "last guess", timeout and manual reveals harmless.
    Scores are derived from the guesses at read time, so revealing awards
    nothing and there is nothing to double count."""
    game_round = (
        db.query(GameRound).filter(GameRound.id == round_id).populate_existing().first()
    )
    if (
        game_round is None
        or game_round.status != "active"
        or experience.game_state != "round_active"
        or experience.current_round != game_round.round_number
    ):
        db.commit()
        return False

    now = _now()
    if game_round.round_locked_at is None:
        game_round.round_locked_at = now
    game_round.status = "revealed"
    game_round.revealed_at = now
    db.flush()
    transition_state(db, experience, "round_reveal")
    log_event(
        db,
        "hwdyk_round_revealed",
        session_id=experience.session_id,
        experience_instance_id=experience.id,
        payload={
            "round_number": game_round.round_number,
            "reason": reason,
            "guesses": len(_guessed_ids(db, game_round)),
            "eligible": len(_round_eligible(db, experience, game_round)),
        },
    )
    db.commit()
    return True


def close_round_if_due(
    db: Session, experience_id: uuid.UUID, now: datetime | None = None
) -> bool:
    """Reveal the live round once its guessing window has closed.

    Called from every live request (like the prep-phase clock), so a round ends
    within a poll or two of its deadline with nothing scheduled. Returns True if
    this call revealed the round."""
    now = now or _now()
    experience = (
        db.query(ExperienceInstance)
        .filter(ExperienceInstance.id == experience_id)
        .populate_existing()
        .first()
    )
    if experience is None or experience.game_state != "round_active":
        db.commit()
        return False
    game_round = _current_round(db, experience)
    if game_round is None or game_round.status != "active":
        db.commit()
        return False
    deadline = _round_deadline(game_round)
    if deadline is None or now < deadline + timedelta(seconds=GUESS_GRACE_SECONDS):
        db.commit()
        return False

    experience = _lock_experience(db, experience_id, skip_locked=True)
    if experience is None:  # another request is already handling it
        return False
    return _reveal_locked(db, experience, game_round.id, reason="timeout")


def advance(db: Session, experience_id: uuid.UUID) -> str | None:
    """Move any overdue timed phase of this game along (prep or live round).

    Returns ``"generate"`` if AI choice generation should now be run."""
    result = phases.advance_if_expired(db, experience_id)
    close_round_if_due(db, experience_id)
    return result


def submit_mc_guess(
    db: Session,
    experience: ExperienceInstance,
    round_id: uuid.UUID,
    participant_id: uuid.UUID,
    choice_id: uuid.UUID,
) -> dict:
    # Verify not main person
    if experience.main_person_participant_id == participant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Main person cannot guess",
        )

    # Serialise guesses, the timeout and reveals for this game.
    experience = _lock_experience(db, experience.id)

    game_round = (
        db.query(GameRound).filter(GameRound.id == round_id).populate_existing().first()
    )
    if not game_round or game_round.experience_instance_id != experience.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Round not found"
        )

    if str(participant_id) not in _round_eligible(db, experience, game_round):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You're not a guesser in this round",
        )

    existing = (
        db.query(GameMCGuess)
        .filter(
            GameMCGuess.game_round_id == round_id,
            GameMCGuess.participant_id == participant_id,
        )
        .first()
    )
    if existing:
        if existing.selected_choice_id == choice_id:
            # A retried request after a lost response: same answer, same result.
            db.commit()
            return {"ok": True, "is_correct": existing.is_correct, "all_guessed": False}
        raise _conflict("already_guessed", "You already submitted a guess for this round")

    deadline = _round_deadline(game_round)
    over = (
        game_round.status != "active"
        or experience.game_state != "round_active"
        or experience.current_round != game_round.round_number
        or game_round.round_locked_at is not None
    )
    if not over and deadline is not None:
        if _now() >= deadline + timedelta(seconds=GUESS_GRACE_SECONDS):
            # Too late. End the round now so everyone moves on together.
            _reveal_locked(db, experience, game_round.id, reason="timeout")
            over = True
    if over:
        raise _conflict("round_closed", "Time's up for this question")

    # Verify choice belongs to this round and is one of the cards on screen
    choice = db.get(GameChoice, choice_id)
    if (
        not choice
        or choice.game_round_id != round_id
        or choice.display_order is None
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid choice for this round",
        )

    is_correct = choice.is_correct
    guess = GameMCGuess(
        game_round_id=round_id,
        participant_id=participant_id,
        selected_choice_id=choice_id,
        is_correct=is_correct,
        points_awarded=CORRECT_POINTS if is_correct else 0,
    )
    db.add(guess)
    try:
        db.flush()
    except IntegrityError:  # unique (round, participant): lost a race with ourselves
        db.rollback()
        raise _conflict("already_guessed", "You already submitted a guess for this round")

    # Everyone eligible has guessed -> end the round now instead of waiting.
    eligible = set(_round_eligible(db, experience, game_round))
    all_guessed = bool(eligible) and eligible <= _guessed_ids(db, game_round)
    if all_guessed:
        _reveal_locked(db, experience, game_round.id, reason="all_guessed")
    else:
        db.commit()

    return {"ok": True, "is_correct": is_correct, "all_guessed": all_guessed}


def reveal_round(
    db: Session,
    experience: ExperienceInstance,
    round_id: uuid.UUID,
) -> dict:
    """Reveal on request (host's fallback button). Idempotent."""
    experience = _lock_experience(db, experience.id)
    game_round = (
        db.query(GameRound).filter(GameRound.id == round_id).populate_existing().first()
    )
    if not game_round or game_round.experience_instance_id != experience.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Round not found"
        )

    # Already revealed (or the game has moved on): nothing to do.
    if game_round.status in ("revealed", "completed"):
        db.commit()
        return {"ok": True, "revealed": False}

    if experience.game_state != "round_active" or (
        experience.current_round != game_round.round_number
    ):
        raise _conflict("round_not_active", "That round isn't the live round")

    # Can't be used to cut guessing short.
    deadline = _round_deadline(game_round)
    eligible = set(_round_eligible(db, experience, game_round))
    everyone_in = bool(eligible) and eligible <= _guessed_ids(db, game_round)
    time_up = deadline is not None and _now() >= deadline
    if not (game_round.round_locked_at or everyone_in or time_up):
        raise _conflict("round_in_progress", "Guessing is still open")

    revealed = _reveal_locked(db, experience, round_id, reason="manual")
    return {"ok": True, "revealed": revealed}


def advance_round(
    db: Session,
    experience: ExperienceInstance,
    round_id: uuid.UUID,
) -> dict:
    """Move from a revealed round to the next one (or the final scores). Idempotent:
    a repeated call for a round that has already been advanced changes nothing."""
    experience = _lock_experience(db, experience.id)
    game_round = (
        db.query(GameRound).filter(GameRound.id == round_id).populate_existing().first()
    )
    if not game_round or game_round.experience_instance_id != experience.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Round not found"
        )

    is_last = game_round.round_number >= experience.max_rounds

    if (
        experience.game_state != "round_reveal"
        or experience.current_round != game_round.round_number
    ):
        db.commit()
        return {"ok": True, "is_last": is_last, "advanced": False}

    game_round.status = "completed"
    db.flush()

    if is_last:
        transition_state(db, experience, "completed")
        experience.completed_at = _now()
    else:
        next_round = (
            db.query(GameRound)
            .filter(
                GameRound.experience_instance_id == experience.id,
                GameRound.round_number == game_round.round_number + 1,
            )
            .first()
        )
        if next_round is None:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Next round is missing",
            )
        # Same guessers as the round before: the roster is fixed once play begins.
        _activate_round(
            experience, next_round, _round_eligible(db, experience, game_round), _now()
        )
        transition_state(db, experience, "round_active")

    db.commit()
    return {"ok": True, "is_last": is_last, "advanced": True}


# ---------- scoring ----------


def compute_hwdyk_scores(db: Session, experience_id: uuid.UUID) -> list[dict]:
    """Compute leaderboard from GameMCGuess records."""
    experience = db.get(ExperienceInstance, experience_id)
    if not experience:
        return []

    config = experience.game_config or DEFAULT_GAME_CONFIG
    mode = config.get("mode", "default")

    rounds = (
        db.query(GameRound)
        .filter(GameRound.experience_instance_id == experience_id)
        .all()
    )
    round_ids = [r.id for r in rounds]
    round_start_map = {r.id: r.started_at for r in rounds}

    participants = _get_participants(db, experience)
    non_main = [
        p for p in participants if p.id != experience.main_person_participant_id
    ]

    results = []
    for p in non_main:
        guesses = (
            db.query(GameMCGuess)
            .filter(
                GameMCGuess.participant_id == p.id,
                GameMCGuess.game_round_id.in_(round_ids),
            )
            .all()
        )
        score = sum(g.points_awarded for g in guesses)  # correct guesses
        correct_count = sum(1 for g in guesses if g.is_correct)

        # Calculate average response time for tie-breaking
        response_times = []
        for g in guesses:
            round_start = round_start_map.get(g.game_round_id)
            if round_start and g.submitted_at:
                delta = (g.submitted_at - round_start).total_seconds()
                response_times.append(delta)
        avg_time = (
            sum(response_times) / len(response_times) if response_times else 999.0
        )

        entry = {
            "participant_id": str(p.id),
            "display_name": p.display_name,
            "score": score,
            "correct_count": correct_count,
            "avg_response_time": round(avg_time, 1),
        }

        if mode == "party":
            # Count how many players were fooled by this person's fakes
            fake_choices = (
                db.query(GameChoice)
                .filter(
                    GameChoice.source_type == "player_fake",
                    GameChoice.created_by_participant_id == p.id,
                    GameChoice.game_round_id.in_(round_ids),
                )
                .all()
            )
            fool_count = 0
            for fake in fake_choices:
                fooled = (
                    db.query(GameMCGuess)
                    .filter(
                        GameMCGuess.selected_choice_id == fake.id,
                        GameMCGuess.participant_id != p.id,
                    )
                    .count()
                )
                fool_count += fooled
            entry["fool_count"] = fool_count
            # Bonus for fooling others is derived here from the guesses, not
            # stored, so revealing a round twice can never award it twice.
            entry["score"] = score + fool_count * FOOL_POINTS

        results.append(entry)

    # Sort by score desc, then by avg response time asc (faster wins ties)
    results.sort(key=lambda x: (-x["score"], x["avg_response_time"]))
    for i, entry in enumerate(results):
        entry["rank"] = i + 1

    return results


# ---------- replay ----------

# Settings that carry over to the next game. Everything else in a game's config
# (regeneration counts, failure notices, ...) belongs to that one game, so the
# replay starts from this list rather than from a copy minus a few keys.
_CARRY_OVER_CONFIG = (
    "mode",
    "num_questions",
    "intimacy_level",
    "min_answer_length",
    "guess_seconds",
    "answer_seconds",
    "edit_seconds",
)


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
            ExperienceInstance.experience_type == "how_well_do_you_know",
        )
        .order_by(ExperienceInstance.created_at.desc(), ExperienceInstance.id)
        .first()
    )


def get_replay_experience(
    db: Session, experience: ExperienceInstance
) -> ExperienceInstance | None:
    """The game that follows this one, if any (read-only)."""
    return _newest_child(db, experience.id)


def _new_replay_experience(
    db: Session, finished: ExperienceInstance
) -> ExperienceInstance:
    config = finished.game_config or DEFAULT_GAME_CONFIG
    new_config = {k: config[k] for k in _CARRY_OVER_CONFIG if k in config}
    new_exp = ExperienceInstance(
        session_id=finished.session_id,
        experience_type="how_well_do_you_know",
        game_state="lobby",
        game_config=new_config,
        max_rounds=int(new_config.get("num_questions", 5)),
        current_round=0,
        parent_experience_instance_id=finished.id,
        present_participant_ids=[],
    )
    db.add(new_exp)
    db.flush()
    log_event(
        db,
        "hwdyk_replay_created",
        session_id=finished.session_id,
        experience_instance_id=new_exp.id,
        payload={"previous_experience_id": str(finished.id)},
    )
    return new_exp


def enter_lobby(
    db: Session,
    experience: ExperienceInstance,
    participant_id: uuid.UUID | None,
    everyone: bool = False,
) -> dict:
    """"Return to lobby" / "Play again".

    The session (and its join code) stays the same; each game is its own
    experience, so the finished game's rounds, guesses and scores are kept as
    history and the new game starts clean. The first person to come back opens
    the next lobby, everyone else joins it, and anyone who does not come back
    simply is not part of it.

    Safe to repeat, from any number of devices, and from a stale results link:
    the call always lands in the newest game of this chain. ``everyone`` adds the
    whole session, which keeps older clients that call the bare replay endpoint
    working."""
    if participant_id is not None:
        member = (
            db.query(SessionParticipant)
            .filter(
                SessionParticipant.session_id == experience.session_id,
                SessionParticipant.participant_id == participant_id,
            )
            .first()
        )
        if not member:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You are not part of this game",
            )

    # Walk to the newest game, locking each row on the way (always parent
    # before child) so two simultaneous returns can't both open a lobby.
    current = experience
    for _ in range(100):
        tail = _lock_experience(db, current.id)
        child = _newest_child(db, tail.id)
        if child is None:
            break
        current = child
    else:  # pragma: no cover - a chain this long means corrupt data
        raise _conflict("replay_chain_invalid", "Couldn't find the current game.")

    if tail.game_state == "completed":
        tail = _new_replay_experience(db, tail)
    elif tail.present_participant_ids is not None:
        if tail.game_state != "lobby":
            raise _conflict(
                "game_in_progress",
                "The next game has already started — you can join the one after.",
            )
    # else: a first game that hasn't finished. Everyone in the session is
    # already in it, so there is nothing to do but point at it.

    if tail.present_participant_ids is not None:
        if everyone:
            for p in _session_participants(db, tail.session_id):
                _add_present(tail, p.id)
        elif participant_id is not None:
            if _add_present(tail, participant_id):
                log_event(
                    db,
                    "hwdyk_returned_to_lobby",
                    session_id=tail.session_id,
                    experience_instance_id=tail.id,
                    participant_id=participant_id,
                )

    session = db.get(SessionModel, tail.session_id)
    result = {
        "experience_instance_id": str(tail.id),
        "game_state": tail.game_state,
        "join_code": session.join_code,
        "share_url": generate_share_url(
            tail.id, session.join_code, game_slug="how-well-do-you-know"
        ),
    }
    db.commit()
    return result


def replay_status(db: Session, experience: ExperienceInstance) -> dict:
    """What the results screen needs to show about the next game."""
    child = _newest_child(db, experience.id)
    total = len(_session_participants(db, experience.session_id))
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
