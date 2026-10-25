"""Magic-link tokens that have already been clicked."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class UsedMagicLink(Base):
    """One row per consumed link. The primary key is what makes a link single-use:
    two clicks racing each other cannot both insert the same id."""

    __tablename__ = "used_magic_links"

    jti: Mapped[str] = mapped_column(Text, primary_key=True)
    used_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
