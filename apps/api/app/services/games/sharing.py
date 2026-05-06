"""Share / join-code utilities."""

from __future__ import annotations

import secrets
import uuid

from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.models.session import Session as SessionModel


def generate_join_code() -> str:
    """6-character alphanumeric join code."""
    return secrets.token_hex(3).upper()  # e.g. "A3F1B2"


def generate_share_url(
    experience_instance_id: uuid.UUID, join_code: str, game_slug: str = "who-knows-who"
) -> str:
    if game_slug == "how-well-do-you-know":
        return f"{settings.WEB_BASE_URL}/games/how-well-do-you-know?code={join_code}"
    return f"{settings.WEB_BASE_URL}/games/experience/{experience_instance_id}/lobby?code={join_code}"


def lookup_session_by_join_code(db: Session, join_code: str) -> SessionModel | None:
    return db.query(SessionModel).filter(SessionModel.join_code == join_code).first()
