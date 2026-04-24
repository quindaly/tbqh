"""Game state machine — centralised transitions and payload building."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.db.models.experience import ExperienceInstance
from app.db.models.game_round import GameRound
from app.db.models.session import SessionParticipant
from app.db.models.participant import Participant
from app.services.games.scoring import compute_scores

VALID_TRANSITIONS: dict[str, list[str]] = {
    "lobby": ["question_collection"],
    "question_collection": ["ready_to_start"],
    "ready_to_start": ["round_active"],
    "round_active": ["round_reveal"],
    "round_reveal": ["round_active", "leaderboard"],
    "leaderboard": ["completed"],
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
    if target_state == "round_active" and experience.started_at is None:
        experience.started_at = now
    if target_state == "completed":
        experience.completed_at = now
    db.flush()
    return experience


def get_game_state_payload(db: Session, experience: ExperienceInstance) -> dict:
    """Build the full state object returned by GET /state."""
    # Participants
    links = (
        db.query(SessionParticipant)
        .filter(SessionParticipant.session_id == experience.session_id)
        .all()
    )
    participant_ids = [l.participant_id for l in links]
    participants = (
        db.query(Participant).filter(Participant.id.in_(participant_ids)).all()
    )
    participants_payload = [
        {"id": str(p.id), "display_name": p.display_name, "role": p.role}
        for p in participants
    ]

    payload: dict = {
        "experience_id": str(experience.id),
        "experience_type": experience.experience_type,
        "game_state": experience.game_state,
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
            round_payload: dict = {
                "round_id": str(game_round.id),
                "round_number": game_round.round_number,
                "status": game_round.status,
                "question_text": game_round.source_prompt_instance.prompt_text,
                "answer_text": game_round.source_response.other_text
                or game_round.source_response.selected_option,
                "answering_participant_id": str(game_round.answering_participant_id),
            }
            if experience.game_state == "round_reveal":
                round_payload["answering_participant_name"] = (
                    game_round.answering_participant.display_name
                )
                guesses = [
                    {
                        "guessing_participant_id": str(g.guessing_participant_id),
                        "guessed_participant_id": str(g.guessed_participant_id),
                        "is_correct": g.is_correct,
                    }
                    for g in game_round.guesses
                ]
                round_payload["guesses"] = guesses
            payload["round"] = round_payload

    # Scores
    if experience.game_state in ("round_reveal", "leaderboard", "completed"):
        payload["scores"] = compute_scores(db, experience.id)

    return payload
