"""Security utilities: magic-link tokens, cookie session."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired

from app.core.config import settings

_signer = URLSafeTimedSerializer(settings.COOKIE_SECRET)

# --------------- magic link tokens ---------------


def create_magic_link_token(email: str) -> str:
    """Create a signed token for one sign-in. The random id lets the server
    refuse a second use of the same link."""
    return _signer.dumps({"e": email, "j": uuid.uuid4().hex}, salt="magic-link")


def verify_magic_link_token(token: str) -> tuple[str, str] | None:
    """Return (email, link id) if the token is genuine and unexpired, else None.

    Tokens issued before links became single-use carry no id and are refused.
    They only lived ten minutes anyway.
    """
    try:
        data = _signer.loads(
            token, salt="magic-link", max_age=settings.MAGIC_LINK_MAX_AGE
        )
    except (BadSignature, SignatureExpired):
        return None
    if not isinstance(data, dict) or not data.get("e") or not data.get("j"):
        return None
    return data["e"], data["j"]


# --------------- session cookies ---------------


def create_session_token(user_id: uuid.UUID) -> str:
    return _signer.dumps(str(user_id), salt="session")


def verify_session_token(token: str) -> uuid.UUID | None:
    try:
        uid = _signer.loads(token, salt="session", max_age=86400 * 30)  # 30 days
        return uuid.UUID(uid)
    except (BadSignature, SignatureExpired):
        return None
