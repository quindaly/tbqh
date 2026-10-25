"""Who is in a game.

A first game has everyone in the session. A replay lobby only has the people
who came back for it (``ExperienceInstance.present_participant_ids``), so a
friend who wandered off never blocks the next game.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.db.models.experience import ExperienceInstance
from app.db.models.participant import Participant
from app.db.models.session import SessionParticipant


# Browsers check in every ~10 seconds while a game page is open.
AWAY_AFTER_SECONDS = 30
# The host keeps the controls through a short blip (a phone switching to
# Messages to share the code). After this long they pass to someone who is here.
HOST_HANDOVER_SECONDS = 60


def seconds_since_seen(p: Participant, now: datetime | None = None) -> float:
    now = now or datetime.now(timezone.utc)
    seen = p.last_seen_at
    if seen is None:
        return 0.0
    if seen.tzinfo is None:
        seen = seen.replace(tzinfo=timezone.utc)
    return (now - seen).total_seconds()


def is_away(p: Participant, now: datetime | None = None) -> bool:
    return seconds_since_seen(p, now) > AWAY_AFTER_SECONDS


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
    if present is not None:
        keep = set(present)
        everyone = [p for p in everyone if str(p.id) in keep]
    left_out = experience.excluded_participant_ids
    if left_out:
        skip = set(left_out)
        everyone = [p for p in everyone if str(p.id) not in skip]
    return everyone


def host_of(
    players: list[Participant], replay: bool, now: datetime | None = None
) -> Participant | None:
    """Who holds the host controls right now.

    Normally the session's host. If their browser has been silent for a minute
    and someone else is here, the longest-standing player who is here takes
    over; the host gets the controls back as soon as they return. In a replay
    without the original host, the longest-standing player, so a replay is
    never host-less.
    """
    now = now or datetime.now(timezone.utc)
    host = next((p for p in players if p.role == "host"), None)
    if host:
        if seconds_since_seen(host, now) > HOST_HANDOVER_SECONDS:
            stand_in = next(
                (p for p in players if p.id != host.id and not is_away(p, now)), None
            )
            if stand_in:
                return stand_in
        return host
    if not replay:
        return None
    here = next((p for p in players if not is_away(p, now)), None)
    return here or (players[0] if players else None)
