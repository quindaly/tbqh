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
    from app.db.models.experience import ExperienceInstance
    from app.services.games.roster import roster

    exp = db.get(ExperienceInstance, experience_instance_id)
    if not exp:
        return []
    players = roster(db, exp)

    results = [
        {
            "participant_id": str(p.id),
            "display_name": p.display_name,
            "score": score_map.get(p.id, 0),
        }
        for p in players
    ]
    # Highest first; ties keep a stable, readable order.
    results.sort(key=lambda x: (-x["score"], x["display_name"].casefold()))

    # Competition ranking: players on the same score share a rank (1, 1, 3).
    for i, r in enumerate(results):
        if i > 0 and r["score"] == results[i - 1]["score"]:
            r["rank"] = results[i - 1]["rank"]
        else:
            r["rank"] = i + 1

    return results
