"""Looking up and creating users by email."""

from __future__ import annotations

from sqlalchemy import func, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.models.feedback import UserQuestionFeedback
from app.db.models.group import Group
from app.db.models.participant import Participant
from app.db.models.user import User

# Guests and anonymous game hosts get a stand-in address so they can own rows.
# These are never real, deliverable emails.
PLACEHOLDER_DOMAINS = ("@guest.local", "@game.local")


def normalize_email(email: str) -> str:
    """One canonical spelling per address.

    Addresses differ only by case in practice, so ``Quin@Gmail.com`` and
    ``quin@gmail.com`` must be the same account."""
    return (email or "").strip().lower()


def is_placeholder_email(email: str) -> bool:
    return normalize_email(email).endswith(PLACEHOLDER_DOMAINS)


def find_user_by_email(db: Session, email: str) -> User | None:
    """Case-insensitive, so accounts created before normalization are found too.
    If an old database has two rows differing only by case, the oldest wins."""
    return (
        db.query(User)
        .filter(func.lower(User.email) == normalize_email(email))
        .order_by(User.created_at, User.id)
        .first()
    )


def get_or_create_user(db: Session, email: str) -> User:
    email = normalize_email(email)
    user = find_user_by_email(db, email)
    if user:
        return user
    user = User(email=email)
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        # Two sign-ins for a new address landed together; the other one won.
        db.rollback()
        existing = find_user_by_email(db, email)
        if existing is None:
            raise
        return existing
    db.refresh(user)
    return user


GUEST_NAME = "Guest"


def adopt_guest_name(db: Session, user: User) -> None:
    """Sessions started as a guest list their host as "Guest". Once the account
    has a name, use it."""
    if not user.display_name:
        return
    db.execute(
        update(Participant)
        .where(Participant.user_id == user.id, Participant.display_name == GUEST_NAME)
        .values(display_name=user.display_name)
    )


def merge_guest_into_user(db: Session, guest: User, user: User) -> dict[str, int]:
    """Give a signed-in account everything a throwaway guest account made.

    Someone who starts a discussion session or a game without signing in is
    working under a stand-in account. When they then sign in from the same
    browser, their sessions, their seat in them, and anything they rated come
    with them, so nothing they did before signing in is orphaned. The guest
    account is left empty and unused.

    Only ever folds a stand-in account (never a real one) into a real one.
    The caller commits, ideally inside a savepoint so a failure undoes only this.
    """
    if guest.id == user.id:
        return {"groups": 0, "participants": 0, "feedback": 0}
    if not is_placeholder_email(guest.email) or is_placeholder_email(user.email):
        return {"groups": 0, "participants": 0, "feedback": 0}

    groups = db.execute(
        update(Group).where(Group.created_by_user_id == guest.id).values(created_by_user_id=user.id)
    ).rowcount
    participants = db.execute(
        update(Participant)
        .where(Participant.user_id == guest.id)
        .values(user_id=user.id, join_type="authenticated")
    ).rowcount
    feedback = db.execute(
        update(UserQuestionFeedback)
        .where(UserQuestionFeedback.user_id == guest.id)
        .values(user_id=user.id)
    ).rowcount
    adopt_guest_name(db, user)
    db.flush()
    return {"groups": groups, "participants": participants, "feedback": feedback}
