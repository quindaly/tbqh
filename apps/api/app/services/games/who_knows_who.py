"""Who Knows Who game orchestration service."""

from __future__ import annotations

import random
import uuid
from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.db.models.experience import ExperienceInstance
from app.db.models.game_guess import GameGuess
from app.db.models.game_round import GameRound
from app.db.models.group import Group
from app.db.models.participant import Participant
from app.db.models.prompt import PromptInstance, PromptResponse
from app.db.models.session import Session as SessionModel, SessionParticipant
from app.services.games.question_bank import select_questions
from app.services.games.sharing import generate_join_code, generate_share_url
from app.services.games.state import transition_state
from app.services.telemetry.events import log_event

DEFAULT_GAME_CONFIG = {
    "num_questions": 10,
    "max_rounds": 10,
    "min_answer_length": 3,
}


# ---------- create / join ----------


def create_game(
    db: Session,
    user_id: uuid.UUID | None,
    display_name: str,
) -> dict:
    # If no authenticated user, create an anonymous user for the host
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

    experience = (
        db.query(ExperienceInstance)
        .filter(
            ExperienceInstance.session_id == session.id,
            ExperienceInstance.experience_type == "who_knows_who",
        )
        .first()
    )
    if not experience:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Game not found"
        )
    if experience.game_state != "lobby":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Game has already started — cannot join",
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
    links = (
        db.query(SessionParticipant)
        .filter(SessionParticipant.session_id == session.id)
        .all()
    )
    pids = [l.participant_id for l in links]
    participants = db.query(Participant).filter(Participant.id.in_(pids)).all()

    host = next((p for p in participants if p.role == "host"), None)

    return {
        "experience_id": str(experience.id),
        "game_state": experience.game_state,
        "game_slug": "who-knows-who",
        "join_code": session.join_code,
        "share_url": generate_share_url(experience.id, session.join_code),
        "host_id": str(host.id) if host else None,
        "participants": [
            {"id": str(p.id), "display_name": p.display_name, "role": p.role}
            for p in participants
        ],
    }


# ---------- answer collection ----------


def start_answer_collection(
    db: Session,
    experience: ExperienceInstance,
    participant_id: uuid.UUID,
) -> dict:
    # Verify host
    host = db.get(Participant, participant_id)
    if not host or host.role != "host":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the host can start the game",
        )

    # Check minimum participants
    link_count = (
        db.query(SessionParticipant)
        .filter(SessionParticipant.session_id == experience.session_id)
        .count()
    )
    if link_count < 2:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Need at least 2 participants to start",
        )

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
    db: Session, experience_instance_id: uuid.UUID
) -> list[dict]:
    prompts = (
        db.query(PromptInstance)
        .filter(
            PromptInstance.experience_instance_id == experience_instance_id,
            PromptInstance.prompt_type == "who_knows_who_self_answer",
        )
        .order_by(PromptInstance.created_at)
        .all()
    )
    return [
        {
            "id": str(p.id),
            "prompt_text": p.prompt_text,
            "prompt_type": p.prompt_type,
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
    min_len = (experience.game_config or {}).get("min_answer_length", 3)
    if not answer_text or len(answer_text.strip()) < min_len:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Answer must be at least {min_len} characters",
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
        other_text=answer_text.strip(),
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

    links = (
        db.query(SessionParticipant)
        .filter(SessionParticipant.session_id == experience.session_id)
        .all()
    )
    num_participants = len(links)
    expected = num_participants * len(prompt_ids)

    actual = (
        db.query(PromptResponse)
        .filter(PromptResponse.prompt_instance_id.in_(prompt_ids))
        .count()
    )
    return actual >= expected


# ---------- round generation ----------


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

    min_len = (experience.game_config or {}).get("min_answer_length", 3)
    responses = (
        db.query(PromptResponse)
        .filter(PromptResponse.prompt_instance_id.in_(prompt_ids))
        .all()
    )
    # Filter blanks
    valid = [
        r for r in responses if r.other_text and len(r.other_text.strip()) >= min_len
    ]

    random.shuffle(valid)

    max_rounds = experience.max_rounds or 10
    selected = valid[:max_rounds]

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


def submit_guess(
    db: Session,
    experience: ExperienceInstance,
    round_id: uuid.UUID,
    guessing_participant_id: uuid.UUID,
    guessed_participant_id: uuid.UUID,
) -> dict:
    game_round = db.get(GameRound, round_id)
    if not game_round or game_round.experience_instance_id != experience.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Round not found"
        )
    if game_round.status != "active":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Round is not active"
        )

    # Answer owner cannot guess on own round
    if guessing_participant_id == game_round.answering_participant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot guess on your own answer",
        )

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
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Already guessed this round"
        )

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
    links = (
        db.query(SessionParticipant)
        .filter(SessionParticipant.session_id == experience.session_id)
        .all()
    )
    eligible = [
        l.participant_id
        for l in links
        if l.participant_id != game_round.answering_participant_id
    ]
    guess_count = (
        db.query(GameGuess).filter(GameGuess.game_round_id == game_round.id).count()
    )
    return guess_count >= len(eligible)


def reveal_round(
    db: Session,
    experience: ExperienceInstance,
    round_id: uuid.UUID,
) -> dict:
    game_round = db.get(GameRound, round_id)
    if not game_round or game_round.experience_instance_id != experience.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Round not found"
        )

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
) -> dict:
    current_round = db.get(GameRound, round_id)
    if not current_round or current_round.experience_instance_id != experience.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Round not found"
        )

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


def replay_game(
    db: Session,
    experience: ExperienceInstance,
) -> dict:
    config = dict(experience.game_config or DEFAULT_GAME_CONFIG)
    new_exp = ExperienceInstance(
        session_id=experience.session_id,
        experience_type="who_knows_who",
        game_state="lobby",
        game_config=config,
        max_rounds=config.get("max_rounds", 10),
        current_round=0,
        parent_experience_instance_id=experience.id,
    )
    db.add(new_exp)
    db.flush()

    session = db.get(SessionModel, experience.session_id)
    share_url = generate_share_url(new_exp.id, session.join_code)

    log_event(
        db,
        "game_replayed",
        session_id=experience.session_id,
        experience_instance_id=new_exp.id,
        payload={"parent_id": str(experience.id)},
    )
    db.commit()

    return {
        "experience_instance_id": str(new_exp.id),
        "join_code": session.join_code,
        "share_url": share_url,
    }
