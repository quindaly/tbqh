"""Participant model."""

from __future__ import annotations

import uuid

from sqlalchemy import ForeignKey, Text, CheckConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, UUIDPKMixin, TimestampMixin


class Participant(Base, UUIDPKMixin, TimestampMixin):
    __tablename__ = "participants"

    group_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("groups.id"), nullable=False
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    display_name: Mapped[str] = mapped_column(Text, nullable=False)
    role: Mapped[str] = mapped_column(
        Text, nullable=False
    )  # host, guest
    join_type: Mapped[str] = mapped_column(
        Text, nullable=False
    )  # authenticated, anonymous

    __table_args__ = (
        CheckConstraint("role IN ('host', 'guest')", name="ck_participant_role"),
        CheckConstraint(
            "join_type IN ('authenticated', 'anonymous')",
            name="ck_participant_join_type",
        ),
    )

    # relationships
    group = relationship("Group", back_populates="participants")
    user = relationship("User", back_populates="participants")
    session_links = relationship("SessionParticipant", back_populates="participant")
