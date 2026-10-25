"""Single-use enforcement for sign-in links."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import delete
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.models.used_magic_link import UsedMagicLink


def consume_magic_link(db: Session, jti: str) -> bool:
    """Mark a link as used. True the first time, False for every later click.

    The insert either succeeds or hits the primary key, so two simultaneous
    clicks cannot both get True.
    """
    result = db.execute(
        insert(UsedMagicLink)
        .values(jti=jti)
        .on_conflict_do_nothing(index_elements=["jti"])
        .returning(UsedMagicLink.jti)
    )
    # A conflict inserts nothing and returns no row.
    first_use = result.first() is not None

    # An expired link is refused by its signature, so old rows are dead weight.
    cutoff = datetime.now(timezone.utc) - timedelta(
        seconds=settings.MAGIC_LINK_MAX_AGE * 2
    )
    db.execute(delete(UsedMagicLink).where(UsedMagicLink.used_at < cutoff))
    db.commit()
    return first_use
