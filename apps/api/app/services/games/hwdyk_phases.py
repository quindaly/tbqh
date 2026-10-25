"""Timed preparation phases for The Hot Seat.

Preparation has three steps, and the server owns the clock for all of them:

1. ``main_person_answering``   - the main person answers the questions, one at a
   time, 20 seconds each. A question that isn't answered in its 20 seconds is
   skipped and the next one starts straight away.
2. ``ai_generating_choices``   - the AI writes wrong answers. Untimed; the
   editing clock does not start until this finishes.
3. ``main_person_reviewing_choices`` - the main person edits them: 60 seconds
   for up to 5 questions, 90 seconds for 6 to 10.

Deadlines are stored on the experience (``phase_deadline_at``). Nothing runs on a
timer: any request that touches the game calls :func:`advance_if_expired`, which
moves an overdue phase along under a row lock. Because every player's browser
polls every few seconds, a phase ends within a few seconds of its deadline, and
if nobody is connected it simply ends the next time someone is.

Timeout policy (documented product decision):

* Everything the main person saved before the deadline is kept. Answers and
  edits are saved as they go, so nothing typed but never saved is used.
* Unedited AI wrong answers stay as the AI wrote them.
* A question the main person didn't answer in its 20 seconds is skipped (it is
  not played). If they answered some but not all questions, the game is played
  with the ones they did answer.
* If the result can't make a playable game (no questions answered, or choices
  that fail validation) the game returns to the lobby with a clear notice and
  the host can start setup again. Nothing is left half-built.
* A save that arrives within ``PHASE_GRACE_SECONDS`` after the deadline is still
  accepted, so an answer sent at 0:00 is not lost to network latency.
"""

from __future__ import annotations

import logging
import random
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.db.models.experience import ExperienceInstance
from app.db.models.game_choice import GameChoice
from app.db.models.game_round import GameRound
from app.db.models.participant import Participant
from app.db.models.prompt import PromptInstance
from app.services.games.hwdyk_common import (
    DEFAULT_GAME_CONFIG,
    FALLBACK_DISTRACTORS,
    clean_text,
    conflict,
    lock_experience,
    norm,
    unique_wrong_answers,
)
from app.services.games.hwdyk_questions import format_question_self
from app.services.games.state import transition_state
from app.services.llm.client import call_llm_json
from app.services.llm.prompts import (
    DISTRACTOR_GENERATION_SYSTEM,
    DISTRACTOR_GENERATION_USER,
)
from app.services.llm.schemas import distractor_generation_schema

logger = logging.getLogger(__name__)

# Answering is timed per question; editing is timed once for the whole set.
ANSWER_SECONDS_PER_QUESTION = 20
EDIT_SECONDS_SHORT = 60  # 1 to 5 questions
EDIT_SECONDS_LONG = 90  # 6 to 10 questions
EDIT_SHORT_MAX_QUESTIONS = 5
PHASE_GRACE_SECONDS = 2
# An AI-generation step that has made no progress for this long is retried.
GENERATION_STALE_SECONDS = 120

ANSWERING = "main_person_answering"
GENERATING = "ai_generating_choices"
REVIEWING = "main_person_reviewing_choices"
TIMED_STATES = (ANSWERING, REVIEWING)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _config(exp: ExperienceInstance) -> dict:
    return exp.game_config or DEFAULT_GAME_CONFIG


# ---------- clock ----------


def start_phase_clock(exp: ExperienceInstance, seconds: int, now: datetime | None = None):
    now = now or _now()
    exp.phase_started_at = now
    exp.phase_deadline_at = now + timedelta(seconds=seconds)


def answer_seconds(exp: ExperienceInstance) -> int:
    """Seconds allowed for each question."""
    return int(_config(exp).get("answer_seconds", ANSWER_SECONDS_PER_QUESTION))


def edit_seconds(exp: ExperienceInstance) -> int:
    """Seconds for editing, by how many questions are being played."""
    configured = _config(exp).get("edit_seconds")
    if configured is not None:
        return int(configured)
    if (exp.max_rounds or 0) <= EDIT_SHORT_MAX_QUESTIONS:
        return EDIT_SECONDS_SHORT
    return EDIT_SECONDS_LONG


# ---------- which question is up ----------


def question_ids(db: Session, exp: ExperienceInstance) -> list[uuid.UUID]:
    """The main person's questions, in the order they are asked."""
    return [
        pid
        for (pid,) in db.query(PromptInstance.id)
        .filter(
            PromptInstance.experience_instance_id == exp.id,
            PromptInstance.prompt_type == "hwdyk_main_person_question",
        )
        .order_by(PromptInstance.round_number, PromptInstance.id)
    ]


def answer_cursor(exp: ExperienceInstance) -> int:
    """Index of the question currently being asked (0-based). Questions before
    it were answered or skipped."""
    return int(_config(exp).get("answer_cursor", 0))


def set_answer_cursor(exp: ExperienceInstance, index: int | None) -> None:
    config = dict(_config(exp))
    if index is None:
        config.pop("answer_cursor", None)
    else:
        config["answer_cursor"] = index
    exp.game_config = config


def answer_progress(db: Session, exp: ExperienceInstance) -> dict:
    return {
        "answered": answered_count(db, exp),
        "total": len(question_ids(db, exp)),
        "current_index": answer_cursor(exp),
    }


def phase_info(exp: ExperienceInstance, now: datetime | None = None) -> dict | None:
    """What clients need to draw a countdown, or None when the phase is untimed.

    Clients should count down from ``seconds_remaining`` as measured when the
    response arrived, not compare ``deadline_at`` to their own clock."""
    if exp.game_state not in TIMED_STATES or exp.phase_deadline_at is None:
        return None
    now = now or _now()
    started = exp.phase_started_at or now
    return {
        "name": exp.game_state,
        "seconds_remaining": round(
            max(0.0, (exp.phase_deadline_at - now).total_seconds()), 1
        ),
        "duration_seconds": int(
            round((exp.phase_deadline_at - started).total_seconds())
        ),
        "deadline_at": exp.phase_deadline_at.isoformat(),
        "server_now": now.isoformat(),
    }


def _due(exp: ExperienceInstance, now: datetime) -> bool:
    if exp.game_state in TIMED_STATES:
        return (
            exp.phase_deadline_at is not None
            and now >= exp.phase_deadline_at + timedelta(seconds=PHASE_GRACE_SECONDS)
        )
    if exp.game_state == GENERATING:
        return exp.phase_started_at is not None and now >= exp.phase_started_at + timedelta(
            seconds=GENERATION_STALE_SECONDS
        )
    return False


def answered_count(db: Session, exp: ExperienceInstance) -> int:
    return (
        db.query(GameRound)
        .filter(GameRound.experience_instance_id == exp.id)
        .count()
    )


# ---------- advancing an overdue phase ----------


def advance_if_expired(
    db: Session, experience_id: uuid.UUID, now: datetime | None = None
) -> str | None:
    """Move an overdue preparation phase along. Safe to call from any request.

    Returns ``"generate"`` when the caller should now run
    :func:`run_generation` (typically as a background task), otherwise None.
    Concurrent callers are harmless: only one gets the row lock, the others see
    the phase already moved on and return."""
    now = now or _now()
    exp = (
        db.query(ExperienceInstance)
        .filter(ExperienceInstance.id == experience_id)
        .populate_existing()
        .first()
    )
    if exp is None or not _due(exp, now):
        db.commit()  # end the read transaction
        return None

    exp = lock_experience(db, experience_id, skip_locked=True)
    if exp is None:  # someone else is advancing it right now
        return None
    if not _due(exp, now):
        db.commit()
        return None

    if exp.game_state == ANSWERING:
        return skip_overdue_questions(db, exp, now)
    if exp.game_state == REVIEWING:
        finish_review(db, exp, timed_out=True)
        return None
    if exp.game_state == GENERATING:
        # The step that was generating never finished (crash, redeploy). Take it over.
        logger.warning("Retrying stalled choice generation for %s", exp.id)
        exp.phase_started_at = now
        db.commit()
        return "generate"
    db.commit()
    return None


def skip_overdue_questions(
    db: Session, exp: ExperienceInstance, now: datetime
) -> str | None:
    """The current question's 20 seconds are up: skip it and start the next.

    Each question's window begins when the previous one ended (not when this
    request happened to arrive), so if nobody was connected for a while every
    question whose time passed is skipped, and the first one still open gets
    its true remaining time. Caller holds the lock."""
    per = timedelta(seconds=answer_seconds(exp))
    total = len(question_ids(db, exp))
    cursor = answer_cursor(exp)
    deadline = exp.phase_deadline_at
    grace = timedelta(seconds=PHASE_GRACE_SECONDS)
    while cursor < total and now >= deadline + grace:
        cursor += 1
        deadline = deadline + per
    exp.state_version = (exp.state_version or 0) + 1
    if cursor >= total:
        set_answer_cursor(exp, None)
        return finish_answering(db, exp)
    set_answer_cursor(exp, cursor)
    exp.phase_started_at = deadline - per
    exp.phase_deadline_at = deadline
    db.commit()
    return None


def _main_person_name(db: Session, exp: ExperienceInstance) -> str:
    person = (
        db.get(Participant, exp.main_person_participant_id)
        if exp.main_person_participant_id
        else None
    )
    return person.display_name if person else "The person in the hot seat"


def finish_answering(db: Session, exp: ExperienceInstance) -> str | None:
    """End the answering phase (all answered, or time ran out). Caller holds the lock.

    Returns ``"generate"`` if AI generation was started."""
    rounds = (
        db.query(GameRound)
        .filter(GameRound.experience_instance_id == exp.id)
        .order_by(GameRound.round_number)
        .all()
    )
    if not rounds:
        reset_to_lobby(
            db,
            exp,
            code="no_answers",
            message=(
                f"{_main_person_name(db, exp)} ran out of time before answering any "
                "questions. Start setup to try again."
            ),
        )
        return None

    set_answer_cursor(exp, None)
    config = _config(exp)
    if len(rounds) != exp.max_rounds:
        # Timed out part-way: play with the questions that were answered.
        for i, r in enumerate(rounds, start=1):
            r.round_number = i
        exp.max_rounds = len(rounds)
        db.flush()

    if config.get("mode", "default") == "default":
        transition_state(db, exp, GENERATING)
        db.commit()
        return "generate"

    transition_state(db, exp, "players_submitting_fake_answers")
    db.commit()
    return None


def reset_to_lobby(db: Session, exp: ExperienceInstance, code: str, message: str) -> None:
    """Throw away a failed preparation and return to a lobby the host can restart.

    Players and the chosen main person stay; questions, rounds and choices are
    deleted so the next setup starts clean. Only valid before live play (no
    guesses exist yet)."""
    round_ids = [
        rid
        for (rid,) in db.query(GameRound.id).filter(
            GameRound.experience_instance_id == exp.id
        )
    ]
    if round_ids:
        db.query(GameRound).filter(GameRound.id.in_(round_ids)).update(
            {GameRound.correct_choice_id: None}, synchronize_session=False
        )
        db.query(GameChoice).filter(GameChoice.game_round_id.in_(round_ids)).delete(
            synchronize_session=False
        )
        db.query(GameRound).filter(GameRound.id.in_(round_ids)).delete(
            synchronize_session=False
        )
    db.query(PromptInstance).filter(
        PromptInstance.experience_instance_id == exp.id,
        PromptInstance.prompt_type == "hwdyk_main_person_question",
    ).delete(synchronize_session=False)
    db.flush()

    config = dict(_config(exp))
    config.pop("regenerate_counts", None)
    config.pop("answer_cursor", None)
    config["notice"] = {"code": code, "message": message}
    exp.game_config = config
    exp.max_rounds = int(config.get("num_questions", 5))
    exp.current_round = 0
    transition_state(db, exp, "lobby")
    db.commit()


# ---------- AI choice generation ----------


def draft_distractors(
    question_text: str, correct_text: str, intimacy: str, count: int = 3
) -> list[str]:
    """Ask the AI for wrong answers; always return ``count`` clean, unique ones.

    Slow (network). Never call while holding a database lock."""
    try:
        result = call_llm_json(
            system_prompt=DISTRACTOR_GENERATION_SYSTEM,
            user_prompt=DISTRACTOR_GENERATION_USER.format(
                question_text=question_text,
                correct_answer=correct_text,
                num_distractors=count,
                intimacy_level=intimacy,
                person_context="Not available",
            ),
            json_schema=distractor_generation_schema(),
            temperature=0.8,
        )
        candidates = list(result.get("wrong_answers", []))
    except Exception:
        logger.exception("Failed to generate distractors")
        candidates = []

    out = unique_wrong_answers(candidates, taken=[correct_text], limit=count)
    if len(out) < count:
        # Keep every round playable even when the AI failed or repeated itself;
        # the main person can edit these during review.
        out += unique_wrong_answers(
            FALLBACK_DISTRACTORS, taken=[correct_text, *out], limit=count - len(out)
        )
    return out


def run_generation(db: Session, experience_id: uuid.UUID) -> bool:
    """Write the AI wrong answers, then open the editing phase.

    Idempotent and safe to run twice: the slow AI calls happen with no locks
    held, and the results are applied in one short transaction only if the game
    is still waiting on them. The editing clock starts at that moment, so slow
    AI never eats into the main person's editing time."""
    exp = (
        db.query(ExperienceInstance)
        .filter(ExperienceInstance.id == experience_id)
        .populate_existing()
        .first()
    )
    if exp is None or exp.game_state != GENERATING:
        db.commit()
        return False

    intimacy = _config(exp).get("intimacy_level", "personal")
    snapshots: list[tuple[uuid.UUID, str, str]] = []
    for game_round in (
        db.query(GameRound)
        .filter(GameRound.experience_instance_id == exp.id)
        .order_by(GameRound.round_number)
        .all()
    ):
        correct = (
            db.query(GameChoice)
            .filter(
                GameChoice.game_round_id == game_round.id,
                GameChoice.is_correct.is_(True),
            )
            .first()
        )
        if correct:
            snapshots.append(
                (game_round.id, format_question_self(game_round.question_text), correct.choice_text)
            )
    db.commit()  # release the connection's transaction before the slow part

    drafted = {
        round_id: draft_distractors(question, correct_text, intimacy)
        for round_id, question, correct_text in snapshots
    }

    exp = lock_experience(db, experience_id)
    if exp.game_state != GENERATING:
        db.commit()
        return False

    for round_id, _question, _correct in snapshots:
        existing = [
            t
            for (t,) in db.query(GameChoice.choice_text).filter(
                GameChoice.game_round_id == round_id
            )
        ]
        wrong_existing = (
            db.query(GameChoice)
            .filter(
                GameChoice.game_round_id == round_id,
                GameChoice.is_correct.is_(False),
            )
            .count()
        )
        needed = 3 - wrong_existing
        if needed <= 0:
            continue
        for text in unique_wrong_answers(drafted[round_id], taken=existing, limit=needed):
            db.add(
                GameChoice(
                    game_round_id=round_id,
                    choice_text=text,
                    is_correct=False,
                    source_type="ai_generated",
                )
            )
    db.flush()

    transition_state(db, exp, REVIEWING)
    start_phase_clock(exp, edit_seconds(exp))
    db.commit()
    return True


# ---------- locking in the reviewed choices ----------


def lock_in_choices(
    db: Session,
    exp: ExperienceInstance,
    expected_revisions: dict[str, int] | None = None,
) -> None:
    """Validate every round, fix the display order and move to ready_to_start.

    Caller holds the experience lock and has checked the state. Raises
    HTTPException if the choices can't make a playable game."""
    rounds = (
        db.query(GameRound)
        .filter(GameRound.experience_instance_id == exp.id)
        .order_by(GameRound.round_number)
        .all()
    )

    all_choices: dict[uuid.UUID, list[GameChoice]] = {}
    for r in rounds:
        all_choices[r.id] = (
            db.query(GameChoice)
            .filter(GameChoice.game_round_id == r.id)
            .with_for_update()
            .populate_existing()
            .order_by(GameChoice.created_at, GameChoice.id)
            .all()
        )

    if expected_revisions is not None:
        for choices in all_choices.values():
            for c in choices:
                seen = expected_revisions.get(str(c.id))
                if seen is not None and seen != (c.revision or 0):
                    raise conflict(
                        "stale_revision",
                        "Your answers changed since this screen loaded. Reload and check them before confirming.",
                    )

    if not rounds:
        raise HTTPException(status_code=400, detail="There are no questions to play")

    for r in rounds:
        choices = all_choices[r.id]
        correct_count = sum(1 for c in choices if c.is_correct)
        wrong = [c for c in choices if not c.is_correct]

        if correct_count != 1:
            raise HTTPException(
                status_code=400,
                detail=f"Round {r.round_number} must have exactly 1 correct answer",
            )
        if len(wrong) < 2:
            raise HTTPException(
                status_code=400,
                detail=f"Round {r.round_number} must have at least 2 wrong answers",
            )
        if any(not clean_text(c.choice_text) for c in choices):
            raise HTTPException(
                status_code=400, detail=f"Round {r.round_number} has a blank answer"
            )
        if len({norm(c.choice_text) for c in choices}) != len(choices):
            raise HTTPException(
                status_code=400,
                detail=f"Round {r.round_number} has two matching answers",
            )

        indices = list(range(len(choices)))
        random.shuffle(indices)
        for i, c in enumerate(choices):
            c.display_order = indices[i]

    db.flush()
    transition_state(db, exp, "ready_to_start")
    db.commit()


def finish_review(db: Session, exp: ExperienceInstance, timed_out: bool = False) -> None:
    """End the editing phase using whatever was saved. Caller holds the lock."""
    try:
        lock_in_choices(db, exp)
    except HTTPException as e:
        if not timed_out:
            raise
        logger.warning("Editing timed out with unusable choices for %s: %s", exp.id, e.detail)
        # Nothing is persisted yet (validation runs before the state change), and
        # the reset below discards the rounds anyway.
        reset_to_lobby(
            db,
            exp,
            code="invalid_choices",
            message=(
                "Time ran out and the answer choices weren't ready to play. "
                "Start setup to try again."
            ),
        )
