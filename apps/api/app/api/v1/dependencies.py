"""Shared FastAPI dependencies: auth, DB session."""

from __future__ import annotations

import uuid

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import verify_session_token
from app.db.models.user import User
from app.db.session import get_db


def get_current_user_id(request: Request) -> uuid.UUID | None:
    """Return user_id from the session cookie, or None if not present.

    The cookie name comes from settings, the same value the sign-in route uses
    to set it."""
    session = request.cookies.get(settings.SESSION_COOKIE_NAME)
    if not session:
        return None
    return verify_session_token(session)


def require_auth(
    user_id: uuid.UUID | None = Depends(get_current_user_id),
) -> uuid.UUID:
    if user_id is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    return user_id


def get_current_user(
    db: Session = Depends(get_db),
    user_id: uuid.UUID = Depends(require_auth),
) -> User:
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    return user
