"""Append-only event logging."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.db.models.event_log import EventLog


def log_event(
    db: Session,
    event_type: str,
    *,
    session_id: uuid.UUID | None = None,
    experience_instance_id: uuid.UUID | None = None,
    participant_id: uuid.UUID | None = None,
    payload: dict[str, Any] | None = None,
) -> EventLog:
    evt = EventLog(
        session_id=session_id,
        experience_instance_id=experience_instance_id,
        participant_id=participant_id,
        event_type=event_type,
        payload=payload,
    )
    db.add(evt)
    db.flush()
    return evt
