"""User model."""

from __future__ import annotations

from sqlalchemy import Boolean, Text, false
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, UUIDPKMixin, TimestampMixin


class User(Base, UUIDPKMixin, TimestampMixin):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(Text, unique=True, nullable=False)

    # What to call them in "Welcome back". Optional: asked once at first sign-in.
    display_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    # True once they have been asked for a name, whether they gave one or skipped.
    name_prompt_done: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=false()
    )

    # relationships
    groups = relationship("Group", back_populates="created_by_user")
    participants = relationship("Participant", back_populates="user")
