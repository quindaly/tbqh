"""Looking up and creating users by email."""

from __future__ import annotations

from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

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
