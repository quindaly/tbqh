"""Auth routes: magic link, callback, me, logout."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import create_magic_link_token, verify_magic_link_token, create_session_token
from app.db.models.user import User
from app.db.session import get_db
from app.api.v1.dependencies import get_current_user
from app.services.telemetry.events import log_event

router = APIRouter(prefix="/auth", tags=["auth"])
logger = logging.getLogger(__name__)


class MagicLinkRequest(BaseModel):
    email: EmailStr


@router.post("/magic-link")
def request_magic_link(body: MagicLinkRequest, db: Session = Depends(get_db)):
    """Request a magic link. In dev mode, log the link to console."""
    token = create_magic_link_token(body.email)
    link = f"{settings.API_BASE_URL}/api/v1/auth/callback?token={token}"

    if settings.EMAIL_PROVIDER == "console":
        logger.info("🔗 Magic link for %s: %s", body.email, link)
        print(f"\n{'='*60}\n🔗 MAGIC LINK for {body.email}:\n{link}\n{'='*60}\n")
    # TODO: Add real email provider

    return {"ok": True}


@router.get("/callback")
def auth_callback(token: str, response: Response, db: Session = Depends(get_db)):
    """Consume magic-link token, create/get user, set session cookie."""
    email = verify_magic_link_token(token)
    if not email:
        raise HTTPException(status_code=400, detail="Invalid or expired token")

    # Get or create user
    user = db.query(User).filter(User.email == email).first()
    if not user:
        user = User(email=email)
        db.add(user)
        db.commit()
        db.refresh(user)

    session_token = create_session_token(user.id)
    response.set_cookie(
        key=settings.SESSION_COOKIE_NAME,
        value=session_token,
        httponly=True,
        samesite="lax",
        max_age=86400 * 30,
    )

    # Redirect to frontend
    from fastapi.responses import RedirectResponse
    redirect = RedirectResponse(url=f"{settings.WEB_BASE_URL}/dashboard", status_code=302)
    redirect.set_cookie(
        key=settings.SESSION_COOKIE_NAME,
        value=session_token,
        httponly=True,
        samesite="lax",
        max_age=86400 * 30,
    )
    return redirect


@router.get("/me")
def get_me(user: User = Depends(get_current_user)):
    return {"id": str(user.id), "email": user.email}


@router.post("/logout")
def logout(response: Response):
    response.delete_cookie(settings.SESSION_COOKIE_NAME)
    return {"ok": True}
