"""Auth routes: magic link, callback, me, logout."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import (
    create_magic_link_token,
    verify_magic_link_token,
    create_session_token,
)
from app.db.models.user import User
from app.db.session import get_db
from app.api.v1.dependencies import get_current_user
from app.services.accounts import (
    get_or_create_user,
    is_placeholder_email,
    normalize_email,
)
from app.services.email import send_magic_link
from app.services.throttle import sign_in_throttle

router = APIRouter(prefix="/auth", tags=["auth"])
logger = logging.getLogger(__name__)

# Per address and per network address, so one person cannot flood an inbox.
EMAIL_LIMIT = (5, 600)  # 5 requests per 10 minutes
IP_LIMIT = (30, 3600)  # 30 requests per hour


def _cookie_settings() -> dict:
    is_prod = not settings.API_BASE_URL.startswith("http://localhost")
    return {
        "httponly": True,
        "samesite": "none" if is_prod else "lax",
        "secure": is_prod,
    }


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


class MagicLinkRequest(BaseModel):
    email: EmailStr


@router.post("/magic-link")
def request_magic_link(
    body: MagicLinkRequest, request: Request, db: Session = Depends(get_db)
):
    """Email a one-time sign-in link."""
    email = normalize_email(body.email)

    if not sign_in_throttle.allow(f"email:{email}", *EMAIL_LIMIT) or not sign_in_throttle.allow(
        f"ip:{_client_ip(request)}", *IP_LIMIT
    ):
        raise HTTPException(
            status_code=429,
            detail="Too many sign-in requests. Wait a few minutes and try again.",
        )

    token = create_magic_link_token(email)
    link = f"{settings.API_BASE_URL}/api/v1/auth/callback?token={token}"

    if not send_magic_link(email, link):
        raise HTTPException(
            status_code=503,
            detail="We couldn't send the email right now. Please try again in a minute.",
        )
    return {"ok": True}


@router.get("/callback")
def auth_callback(token: str, db: Session = Depends(get_db)):
    """Consume a magic-link token, create or find the user, set the session cookie."""
    email = verify_magic_link_token(token)
    if not email:
        # People land here from their inbox, so send them somewhere readable
        # instead of showing a bare JSON error.
        return RedirectResponse(
            url=f"{settings.WEB_BASE_URL}/login?error=expired", status_code=302
        )

    user = get_or_create_user(db, email)

    redirect = RedirectResponse(url=f"{settings.WEB_BASE_URL}/dashboard", status_code=302)
    redirect.set_cookie(
        key=settings.SESSION_COOKIE_NAME,
        value=create_session_token(user.id),
        max_age=86400 * 30,
        **_cookie_settings(),
    )
    return redirect


@router.get("/me")
def get_me(user: User = Depends(get_current_user)):
    return {
        "id": str(user.id),
        "email": user.email,
        # Guests and anonymous hosts carry a stand-in address, not a real one.
        "is_guest": is_placeholder_email(user.email),
    }


@router.post("/guest")
def create_guest_session(response: Response, db: Session = Depends(get_db)):
    """Create an anonymous user + group + session in one shot for guests."""
    import uuid
    import secrets
    from app.db.models.group import Group
    from app.db.models.participant import Participant
    from app.db.models.session import Session as SessionModel, SessionParticipant
    from app.db.models.policy import PolicyProfile

    # Create anon user
    anon_user = User(email=f"guest-{uuid.uuid4().hex[:8]}@guest.local")
    db.add(anon_user)
    db.flush()

    # Create group
    group = Group(created_by_user_id=anon_user.id, name="Guest session")
    db.add(group)
    db.flush()

    # Host participant
    host = Participant(
        group_id=group.id,
        user_id=anon_user.id,
        display_name="Guest",
        role="host",
        join_type="anonymous",
    )
    db.add(host)
    db.flush()

    # Get or create default policy
    policy = db.query(PolicyProfile).first()
    if not policy:
        policy = PolicyProfile(name="default", excluded_categories=[])
        db.add(policy)
        db.flush()

    # Create session
    join_code = secrets.token_urlsafe(6).upper()[:8]
    sess = SessionModel(
        group_id=group.id,
        policy_profile_id=policy.id,
        join_code=join_code,
    )
    db.add(sess)
    db.flush()

    sp = SessionParticipant(session_id=sess.id, participant_id=host.id)
    db.add(sp)

    # Set session cookie so subsequent requests are "authenticated"
    response.set_cookie(
        key=settings.SESSION_COOKIE_NAME,
        value=create_session_token(anon_user.id),
        max_age=86400 * 30,
        **_cookie_settings(),
    )

    db.commit()

    return {
        "user_id": str(anon_user.id),
        "group_id": str(group.id),
        "session_id": str(sess.id),
        "participant_id": str(host.id),
        "join_code": join_code,
    }


@router.post("/logout")
def logout(response: Response):
    # Same attributes as when it was set, so the browser clears the right cookie.
    response.delete_cookie(settings.SESSION_COOKIE_NAME, **_cookie_settings())
    return {"ok": True}
