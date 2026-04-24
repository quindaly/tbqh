"""Security utilities: magic-link tokens, cookie session."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired

from app.core.config import settings

_signer = URLSafeTimedSerializer(settings.COOKIE_SECRET)

# --------------- magic link tokens ---------------


def create_magic_link_token(email: str) -> str:
    """Create a signed token encoding the user email."""
    return _signer.dumps(email, salt="magic-link")


def verify_magic_link_token(token: str) -> str | None:
    """Return email if token is valid, else None."""
    try:
        email: str = _signer.loads(
            token, salt="magic-link", max_age=settings.MAGIC_LINK_MAX_AGE
        )
        return email
    except (BadSignature, SignatureExpired):
        return None


# --------------- session cookies ---------------


def create_session_token(user_id: uuid.UUID) -> str:
    return _signer.dumps(str(user_id), salt="session")


def verify_session_token(token: str) -> uuid.UUID | None:
    try:
        uid = _signer.loads(token, salt="session", max_age=86400 * 30)  # 30 days
        return uuid.UUID(uid)
    except (BadSignature, SignatureExpired):
        return None
