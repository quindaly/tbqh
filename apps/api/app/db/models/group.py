"""Group model."""

from __future__ import annotations

import uuid

from sqlalchemy import ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, UUIDPKMixin, TimestampMixin


class Group(Base, UUIDPKMixin, TimestampMixin):
    __tablename__ = "groups"

    created_by_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    name: Mapped[str | None] = mapped_column(Text, nullable=True)

    # relationships
    created_by_user = relationship("User", back_populates="groups")
    participants = relationship("Participant", back_populates="group")
    sessions = relationship("Session", back_populates="group")
    group_profiles = relationship("GroupProfile", back_populates="group")
