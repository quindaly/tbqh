"""Who is in a game.

A first game has everyone in the session. A replay lobby only has the people
who came back for it (``ExperienceInstance.present_participant_ids``), so a
friend who wandered off never blocks the next game.
"""

from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

from app.db.models.experience import ExperienceInstance
from app.db.models.participant import Participant
from app.db.models.session import SessionParticipant


def session_participants(db: Session, session_id: uuid.UUID) -> list[Participant]:
    pids = [
        row[0]
        for row in db.query(SessionParticipant.participant_id)
        .filter(SessionParticipant.session_id == session_id)
        .all()
    ]
    if not pids:
        return []
    return (
        db.query(Participant)
        .filter(Participant.id.in_(pids))
        .order_by(Participant.created_at, Participant.id)
        .all()
    )


def roster(db: Session, experience: ExperienceInstance) -> list[Participant]:
    """The players in this game, oldest first."""
    everyone = session_participants(db, experience.session_id)
    present = experience.present_participant_ids
    if present is None:
        return everyone
    keep = set(present)
    return [p for p in everyone if str(p.id) in keep]


def host_of(players: list[Participant], replay: bool) -> Participant | None:
    """The session's host while they are in the game; in a replay without them,
    the longest-standing player, so a replay is never host-less."""
    host = next((p for p in players if p.role == "host"), None)
    if host or not replay:
        return host
    return players[0] if players else None
