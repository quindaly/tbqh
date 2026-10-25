"""Game state machine — centralised transitions and payload building."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.db.models.experience import ExperienceInstance
from app.db.models.game_guess import GameGuess
from app.db.models.game_round import GameRound
from app.db.models.session import SessionParticipant
from app.db.models.participant import Participant
from app.services.games.scoring import compute_scores

VALID_TRANSITIONS: dict[str, list[str]] = {
    # Who Knows Who
    "lobby": ["question_collection", "main_person_answering"],
    "question_collection": ["ready_to_start"],
    "ready_to_start": ["round_active"],
    "round_active": ["round_reveal"],
    "round_reveal": ["round_active", "leaderboard", "completed"],
    "leaderboard": ["completed"],
    # The Hot Seat
    # "lobby" is also a target here: a timed-out or invalid preparation returns
    # to a recoverable lobby state so the host can start setup again.
    "main_person_answering": [
        "ai_generating_choices",
        "players_submitting_fake_answers",
        "lobby",
    ],
    "ai_generating_choices": ["main_person_reviewing_choices", "lobby"],
    "main_person_reviewing_choices": ["ready_to_start", "lobby"],
    "players_submitting_fake_answers": ["ready_to_start"],
}


def transition_state(
    db: Session,
    experience: ExperienceInstance,
    target_state: str,
) -> ExperienceInstance:
    current = experience.game_state
    allowed = VALID_TRANSITIONS.get(current, [])
    if target_state not in allowed:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Cannot transition from '{current}' to '{target_state}'",
        )
    experience.game_state = target_state
    now = datetime.now(timezone.utc)
    # Every transition starts a fresh phase: bump the version (lets clients drop
    # out-of-order poll responses) and clear any deadline, so a timed phase must
    # set its own and can never inherit the previous phase's clock.
    experience.state_version = (experience.state_version or 0) + 1
    experience.phase_started_at = now
    experience.phase_deadline_at = None
    if target_state == "round_active" and experience.started_at is None:
        experience.started_at = now
    if target_state == "completed":
        experience.completed_at = now
    db.flush()
    return experience


def get_game_state_payload(
    db: Session,
    experience: ExperienceInstance,
    viewer_id: uuid.UUID | None = None,
) -> dict:
    """Build the full state object returned by GET /state.

    While a round is being guessed, nothing in it says whose answer it is:
    the viewer is only told whether it is *theirs* and whether they have
    already guessed. The owner is named at the reveal."""
    from app.services.games.roster import host_of, roster

    players = roster(db, experience)
    is_replay = experience.present_participant_ids is not None
    host = host_of(players, is_replay)
    participants_payload = [
        {
            "id": str(p.id),
            "display_name": p.display_name,
            "role": "host" if host and p.id == host.id else "guest",
        }
        for p in players
    ]

    payload: dict = {
        "experience_id": str(experience.id),
        "experience_type": experience.experience_type,
        "game_state": experience.game_state,
        "state_version": experience.state_version,
        "current_round": experience.current_round,
        "max_rounds": experience.max_rounds,
        "participants": participants_payload,
    }

    # Current round info
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
            owner_id = game_round.answering_participant_id
            guesses = (
                db.query(GameGuess).filter(GameGuess.game_round_id == game_round.id).all()
            )
            round_payload: dict = {
                "round_id": str(game_round.id),
                "round_number": game_round.round_number,
                "status": game_round.status,
                "question_text": game_round.source_prompt_instance.prompt_text,
                "answer_text": game_round.source_response.other_text
                or game_round.source_response.selected_option,
                "is_yours": viewer_id is not None and viewer_id == owner_id,
                "you_guessed": viewer_id is not None
                and any(g.guessing_participant_id == viewer_id for g in guesses),
                "guessed_count": len(guesses),
                "guesser_count": len([p for p in players if p.id != owner_id]),
            }
            if experience.game_state == "round_reveal":
                round_payload["answering_participant_id"] = str(owner_id)
                round_payload["answering_participant_name"] = (
                    game_round.answering_participant.display_name
                )
                round_payload["guesses"] = [
                    {
                        "guessing_participant_id": str(g.guessing_participant_id),
                        "guessed_participant_id": str(g.guessed_participant_id),
                        "is_correct": g.is_correct,
                    }
                    for g in guesses
                ]
            payload["round"] = round_payload

    # Scores
    if experience.game_state in ("round_reveal", "leaderboard", "completed"):
        payload["scores"] = compute_scores(db, experience.id)

    return payload
