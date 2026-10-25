"""Auth routes: magic link, callback, me, logout."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, EmailStr, field_validator
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import (
    create_magic_link_token,
    verify_magic_link_token,
    create_session_token,
)
from app.db.models.user import User
from app.db.session import get_db
from app.api.v1.dependencies import get_current_user, get_current_user_id
from app.services.accounts import (
    get_or_create_user,
    is_placeholder_email,
    normalize_email,
)
from app.services.email import send_magic_link
from app.services.games.names import MAX_NAME_LEN
from app.services.redirects import clean_next
from app.services.magic_links import consume_magic_link
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
    # Where to land after signing in (a path on this site). Left out, it's the home page.
    next: str | None = None


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

    token = create_magic_link_token(email, clean_next(body.next))
    link = f"{settings.API_BASE_URL}/api/v1/auth/callback?token={token}"

    if not send_magic_link(email, link):
        raise HTTPException(
            status_code=503,
            detail="We couldn't send the email right now. Please try again in a minute.",
        )
    return {"ok": True}


@router.get("/callback")
def auth_callback(token: str, db: Session = Depends(get_db)):
    """Consume a magic-link token (once only), create or find the user, set the session cookie."""
    verified = verify_magic_link_token(token)
    if not verified or not consume_magic_link(db, verified[1]):
        # People land here from their inbox, so send them somewhere readable
        # instead of showing a bare JSON error.
        return RedirectResponse(
            url=f"{settings.WEB_BASE_URL}/login?error=expired", status_code=302
        )

    email, _, next_path = verified
    user = get_or_create_user(db, email)

    # Straight to the home page, or back to wherever they were when they chose
    # to sign in (the path was checked when the link was requested and is signed).
    landing = clean_next(next_path) or "/"
    redirect = RedirectResponse(url=f"{settings.WEB_BASE_URL}{landing}", status_code=302)
    redirect.set_cookie(
        key=settings.SESSION_COOKIE_NAME,
        value=create_session_token(user.id),
        max_age=86400 * 30,
        **_cookie_settings(),
    )
    return redirect


@router.get("/me")
def get_me(user: User = Depends(get_current_user)):
    guest = is_placeholder_email(user.email)
    return {
        "id": str(user.id),
        "email": user.email,
        # Guests and anonymous hosts carry a stand-in address, not a real one.
        "is_guest": guest,
        "name": user.display_name,
        # Signed in for real, never asked for a name yet.
        "needs_name": not guest and not user.name_prompt_done and not user.display_name,
    }


class UpdateMeRequest(BaseModel):
    name: str | None = None
    # "Not now": stop asking, and welcome them without a name.
    skip: bool = False

    @field_validator("name")
    @classmethod
    def _tidy(cls, v: str | None) -> str | None:
        if v is None:
            return None
        v = " ".join(v.split())
        if len(v) > MAX_NAME_LEN:
            raise ValueError(f"Names can be up to {MAX_NAME_LEN} characters.")
        return v or None


@router.patch("/me")
def update_me(
    body: UpdateMeRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Set or skip the name used in "Welcome back"."""
    if is_placeholder_email(user.email):
        raise HTTPException(status_code=403, detail="Sign in with your email first.")
    if body.name:
        user.display_name = body.name
    elif not body.skip:
        raise HTTPException(status_code=422, detail="Enter a name or choose not now.")
    user.name_prompt_done = True
    db.commit()
    return {"ok": True, "name": user.display_name}


@router.post("/guest")
def create_guest_session(
    response: Response,
    db: Session = Depends(get_db),
    current_user_id=Depends(get_current_user_id),
):
    """Create a group + session in one shot.

    Someone not signed in gets a throwaway account. Someone who is signed in
    keeps theirs: starting a session must never swap their login for a guest's."""
    import uuid
    from app.services.join_codes import new_join_code
    from app.db.models.group import Group
    from app.db.models.participant import Participant
    from app.db.models.session import Session as SessionModel, SessionParticipant
    from app.db.models.policy import PolicyProfile

    signed_in = db.get(User, current_user_id) if current_user_id else None
    if signed_in is not None and not is_placeholder_email(signed_in.email):
        anon_user = signed_in
        keep_login = True
    else:
        anon_user = User(email=f"guest-{uuid.uuid4().hex[:8]}@guest.local")
        db.add(anon_user)
        db.flush()
        keep_login = False

    # Create group
    group = Group(created_by_user_id=anon_user.id, name="Guest session")
    db.add(group)
    db.flush()

    # Host participant
    host = Participant(
        group_id=group.id,
        user_id=anon_user.id,
        display_name=(anon_user.display_name or "Guest") if keep_login else "Guest",
        role="host",
        join_type="authenticated" if keep_login else "anonymous",
    )
    db.add(host)
    db.flush()

    # Get or create default policy
    policy = (
        db.query(PolicyProfile).filter(PolicyProfile.name == "family_friendly").first()
        or db.query(PolicyProfile).order_by(PolicyProfile.created_at).first()
    )
    if not policy:
        policy = PolicyProfile(name="default", excluded_categories=[])
        db.add(policy)
        db.flush()

    # Create session
    join_code = new_join_code()
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
    if not keep_login:
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
