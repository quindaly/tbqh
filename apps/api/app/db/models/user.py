"""User model."""

from __future__ import annotations

from sqlalchemy import Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, UUIDPKMixin, TimestampMixin


class User(Base, UUIDPKMixin, TimestampMixin):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(Text, unique=True, nullable=False)

    # relationships
    groups = relationship("Group", back_populates="created_by_user")
    participants = relationship("Participant", back_populates="user")
