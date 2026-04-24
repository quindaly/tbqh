"""Score computation from game_guesses."""

from __future__ import annotations

import uuid

from sqlalchemy import func as sa_func
from sqlalchemy.orm import Session

from app.db.models.game_guess import GameGuess
from app.db.models.game_round import GameRound
from app.db.models.participant import Participant


def compute_scores(db: Session, experience_instance_id: uuid.UUID) -> list[dict]:
    """Return leaderboard-sorted list of {participant_id, display_name, score}."""
    rows = (
        db.query(
            GameGuess.guessing_participant_id,
            sa_func.count().label("score"),
        )
        .join(GameRound, GameRound.id == GameGuess.game_round_id)
        .filter(
            GameRound.experience_instance_id == experience_instance_id,
            GameGuess.is_correct.is_(True),
        )
        .group_by(GameGuess.guessing_participant_id)
        .all()
    )
    score_map = {row[0]: row[1] for row in rows}

    # Include participants with 0 correct guesses
    from app.db.models.session import SessionParticipant
    from app.db.models.experience import ExperienceInstance

    exp = db.get(ExperienceInstance, experience_instance_id)
    if not exp:
        return []
    links = (
        db.query(SessionParticipant)
        .filter(SessionParticipant.session_id == exp.session_id)
        .all()
    )
    pids = [l.participant_id for l in links]
    participants = db.query(Participant).filter(Participant.id.in_(pids)).all()

    results = []
    for p in participants:
        results.append(
            {
                "participant_id": str(p.id),
                "display_name": p.display_name,
                "score": score_map.get(p.id, 0),
            }
        )
    results.sort(key=lambda x: x["score"], reverse=True)

    # Add rank
    for i, r in enumerate(results, 1):
        r["rank"] = i

    return results
