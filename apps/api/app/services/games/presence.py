"""Who is at their screen right now.

Every game page checks in every few seconds. That keeps a ``last_seen_at`` on
each participant, which is how the lobby can show who has gone quiet, how the
host can clear them out, and how host controls pass to someone who is still
here.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.db.models.experience import ExperienceInstance
from app.db.models.participant import Participant
from app.db.models.session import Session as SessionModel, SessionParticipant
from app.services.games.roster import host_of, roster, session_participants

# Do not write on every ping from a busy room.
WRITE_EVERY_SECONDS = 8


def check_in(
    db: Session, experience: ExperienceInstance, participant_id: uuid.UUID
) -> dict:
    """Record that this person is here and tell their browser where it stands.

    ``member``: they are in this session. ``removed``: they were in it and the
    host cleared them out. ``left_out``: the host started the game without them.
    ``host_id``: who holds the host controls right now.
    """
    members = session_participants(db, experience.session_id)
    me = next((p for p in members if p.id == participant_id), None)

    if me is None:
        # Known to the group but no longer linked to the session = removed.
        session = db.get(SessionModel, experience.session_id)
        known = db.get(Participant, participant_id)
        removed = bool(known and session and known.group_id == session.group_id)
        return {"member": False, "removed": removed, "left_out": False, "host_id": None}

    now = datetime.now(timezone.utc)
    seen = me.last_seen_at
    if seen is not None and seen.tzinfo is None:
        seen = seen.replace(tzinfo=timezone.utc)
    if seen is None or (now - seen).total_seconds() >= WRITE_EVERY_SECONDS:
        me.last_seen_at = now
        db.commit()

    players = roster(db, experience)
    host = host_of(players, experience.present_participant_ids is not None, now)
    left_out = str(me.id) in (experience.excluded_participant_ids or [])
    return {
        "member": True,
        "removed": False,
        "left_out": left_out,
        "host_id": str(host.id) if host else None,
    }
