"""How Well Do You Know [Person]? game orchestration service."""

from __future__ import annotations

import logging
import random
import uuid
from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

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


def _get_participants(db: Session, experience: ExperienceInstance) -> list[Participant]:
    links = (
        db.query(SessionParticipant)
        .filter(SessionParticipant.session_id == experience.session_id)
        .all()
    )
    pids = [l.participant_id for l in links]
    return db.query(Participant).filter(Participant.id.in_(pids)).all()


def _verify_host(
    db: Session,
    participant_id: uuid.UUID,
    experience: ExperienceInstance | None = None,
) -> Participant:
    host = db.get(Participant, participant_id)
    if not host or host.role != "host":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the host can perform this action",
        )
    if experience is not None:
        # A host of some other game must not be able to act on this one.
        in_session = (
            db.query(SessionParticipant)
            .filter(
                SessionParticipant.session_id == experience.session_id,
                SessionParticipant.participant_id == participant_id,
            )
            .first()
        )
        if not in_session:
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

    experience = (
        db.query(ExperienceInstance)
        .filter(
            ExperienceInstance.session_id == session.id,
            ExperienceInstance.experience_type == "how_well_do_you_know",
        )
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


# ---------- lobby ----------


def get_lobby_payload(db: Session, experience: ExperienceInstance) -> dict:
    session = db.get(SessionModel, experience.session_id)
    participants = _get_participants(db, experience)
    host = next((p for p in participants if p.role == "host"), None)
    config = experience.game_config or DEFAULT_GAME_CONFIG

    progress = None
    if experience.game_state == phases.ANSWERING:
        progress = {
            "answered": phases.answered_count(db, experience),
            "total": int(config.get("num_questions", 5)),
        }

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
        "participants": [
            {"id": str(p.id), "display_name": p.display_name, "role": p.role}
            for p in participants
        ],
    }


def select_main_person(
    db: Session,
    experience: ExperienceInstance,
    host_participant_id: uuid.UUID,
    main_person_participant_id: uuid.UUID,
) -> None:
    _verify_host(db, host_participant_id, experience)

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


def start_live_game(
    db: Session,
    experience: ExperienceInstance,
    host_participant_id: uuid.UUID,
) -> None:
    _verify_host(db, host_participant_id, experience)

    # Activate round 1
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

    first_round.status = "active"
    first_round.started_at = datetime.now(timezone.utc)
    experience.current_round = 1
    db.flush()

    transition_state(db, experience, "round_active")
    db.commit()


def get_round_state(db: Session, experience: ExperienceInstance) -> dict:
    """Build full game state payload for HWDYK polling."""
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
        game_round = (
            db.query(GameRound)
            .filter(
                GameRound.experience_instance_id == experience.id,
                GameRound.round_number == experience.current_round,
            )
            .first()
        )
        if game_round:
            # Check timer expiry
            if game_round.status == "active" and not game_round.round_locked_at:
                _check_and_lock_timer(db, game_round)

            # Calculate time remaining
            time_remaining = 60
            if game_round.started_at:
                elapsed = (
                    datetime.now(timezone.utc) - game_round.started_at
                ).total_seconds()
                time_remaining = max(0, game_round.timer_duration - elapsed)

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

            # Non-main-person participants count (eligible guessers)
            non_main = [
                p for p in participants if p.id != experience.main_person_participant_id
            ]

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
                "time_remaining_seconds": int(time_remaining),
                "is_locked": game_round.round_locked_at is not None,
                "guesses_submitted": len(mc_guesses),
                "total_guessers": len(non_main),
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


def _check_and_lock_timer(db: Session, game_round: GameRound) -> bool:
    if game_round.status != "active":
        return False
    if game_round.started_at is None:
        return False

    elapsed = (datetime.now(timezone.utc) - game_round.started_at).total_seconds()
    if elapsed >= (game_round.timer_duration or 60):
        game_round.round_locked_at = datetime.now(timezone.utc)
        db.flush()
        return True
    return False


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

    game_round = db.get(GameRound, round_id)
    if not game_round or game_round.experience_instance_id != experience.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Round not found"
        )

    if game_round.status != "active":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Round is not active"
        )

    # Check if round is locked (timer expired)
    if game_round.round_locked_at:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Time has expired for this round",
        )

    # Verify choice belongs to this round
    choice = db.get(GameChoice, choice_id)
    if not choice or choice.game_round_id != round_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid choice for this round",
        )

    # Check duplicate guess
    existing = (
        db.query(GameMCGuess)
        .filter(
            GameMCGuess.game_round_id == round_id,
            GameMCGuess.participant_id == participant_id,
        )
        .first()
    )
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="You already submitted a guess for this round",
        )

    is_correct = choice.is_correct
    points = 100 if is_correct else 0

    guess = GameMCGuess(
        game_round_id=round_id,
        participant_id=participant_id,
        selected_choice_id=choice_id,
        is_correct=is_correct,
        points_awarded=points,
    )
    db.add(guess)
    db.flush()

    # Check if all players have guessed
    participants = _get_participants(db, experience)
    non_main = [
        p for p in participants if p.id != experience.main_person_participant_id
    ]
    guess_count = (
        db.query(GameMCGuess).filter(GameMCGuess.game_round_id == round_id).count()
    )
    all_guessed = guess_count >= len(non_main)

    if all_guessed:
        game_round.round_locked_at = datetime.now(timezone.utc)
        db.flush()
        db.commit()
        # Auto-reveal when all players have submitted
        reveal_round(db, experience, round_id)
        return {"ok": True, "is_correct": is_correct, "all_guessed": True}

    db.flush()
    db.commit()

    return {"ok": True, "is_correct": is_correct, "all_guessed": False}


def reveal_round(
    db: Session,
    experience: ExperienceInstance,
    round_id: uuid.UUID,
) -> None:
    game_round = db.get(GameRound, round_id)
    if not game_round or game_round.experience_instance_id != experience.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Round not found"
        )

    # Idempotent: if already revealed, skip
    if game_round.status == "revealed" or experience.game_state == "round_reveal":
        return

    # Calculate Party Mode fool points
    config = experience.game_config or DEFAULT_GAME_CONFIG
    mode = config.get("mode", "default")

    if mode == "party":
        mc_guesses = (
            db.query(GameMCGuess).filter(GameMCGuess.game_round_id == round_id).all()
        )
        # For each fake answer, count how many players (other than the creator) picked it
        fake_choices = (
            db.query(GameChoice)
            .filter(
                GameChoice.game_round_id == round_id,
                GameChoice.source_type == "player_fake",
            )
            .all()
        )
        for fake in fake_choices:
            if not fake.created_by_participant_id:
                continue
            fooled_count = sum(
                1
                for g in mc_guesses
                if g.selected_choice_id == fake.id
                and g.participant_id != fake.created_by_participant_id
            )
            # Award 50 points per fooled player to the fake author
            if fooled_count > 0:
                # Find or create a bonus record - add to existing guess points
                author_guess = next(
                    (
                        g
                        for g in mc_guesses
                        if g.participant_id == fake.created_by_participant_id
                    ),
                    None,
                )
                if author_guess:
                    author_guess.points_awarded += fooled_count * 50
                    db.flush()

    game_round.status = "revealed"
    game_round.revealed_at = datetime.now(timezone.utc)
    db.flush()

    transition_state(db, experience, "round_reveal")
    db.commit()


def advance_round(
    db: Session,
    experience: ExperienceInstance,
    round_id: uuid.UUID,
) -> dict:
    game_round = db.get(GameRound, round_id)
    if not game_round or game_round.experience_instance_id != experience.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Round not found"
        )

    game_round.status = "completed"
    db.flush()

    # Check if last round
    is_last = game_round.round_number >= experience.max_rounds

    if is_last:
        transition_state(db, experience, "completed")
        experience.completed_at = datetime.now(timezone.utc)
    else:
        # Activate next round
        next_round = (
            db.query(GameRound)
            .filter(
                GameRound.experience_instance_id == experience.id,
                GameRound.round_number == game_round.round_number + 1,
            )
            .first()
        )
        if next_round:
            next_round.status = "active"
            next_round.started_at = datetime.now(timezone.utc)
            experience.current_round = next_round.round_number
            db.flush()
            transition_state(db, experience, "round_active")

    db.commit()
    return {"ok": True, "is_last": is_last}


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
        score = sum(g.points_awarded for g in guesses)
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

        results.append(entry)

    # Sort by score desc, then by avg response time asc (faster wins ties)
    results.sort(key=lambda x: (-x["score"], x["avg_response_time"]))
    for i, entry in enumerate(results):
        entry["rank"] = i + 1

    return results


# ---------- replay ----------


def replay_game(db: Session, experience: ExperienceInstance) -> dict:
    config = experience.game_config or DEFAULT_GAME_CONFIG
    session = db.get(SessionModel, experience.session_id)

    # Clean config for new game (remove state from previous game)
    new_config = {k: v for k, v in config.items() if k not in ("regenerate_counts",)}

    join_code = generate_join_code()
    session_new = SessionModel(
        group_id=session.group_id,
        policy_profile_id=session.policy_profile_id,
        join_code=join_code,
    )
    db.add(session_new)
    db.flush()

    # Copy participants
    links = (
        db.query(SessionParticipant)
        .filter(SessionParticipant.session_id == experience.session_id)
        .all()
    )
    for link in links:
        sp = SessionParticipant(
            session_id=session_new.id, participant_id=link.participant_id
        )
        db.add(sp)
    db.flush()

    new_exp = ExperienceInstance(
        session_id=session_new.id,
        experience_type="how_well_do_you_know",
        game_state="lobby",
        game_config=new_config,
        max_rounds=new_config.get("num_questions", 5),
        current_round=0,
        parent_experience_instance_id=experience.id,
    )
    db.add(new_exp)
    db.flush()

    share_url = generate_share_url(
        new_exp.id, join_code, game_slug="how-well-do-you-know"
    )
    db.commit()

    return {
        "experience_instance_id": str(new_exp.id),
        "join_code": join_code,
        "share_url": share_url,
    }
