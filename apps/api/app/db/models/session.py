"""Session + SessionParticipant models."""

from __future__ import annotations

import uuid

from sqlalchemy import ForeignKey, Text, CheckConstraint, DateTime
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, UUIDPKMixin, TimestampMixin
from datetime import datetime


class Session(Base, UUIDPKMixin, TimestampMixin):
    __tablename__ = "sessions"

    group_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("groups.id"), nullable=False
    )
    policy_profile_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("policy_profiles.id"), nullable=False
    )
    join_code: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="active")
    ended_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    __table_args__ = (
        CheckConstraint("status IN ('active', 'ended')", name="ck_session_status"),
    )

    group = relationship("Group", back_populates="sessions")
    policy_profile = relationship("PolicyProfile", back_populates="sessions")
    participant_links = relationship("SessionParticipant", back_populates="session")
    experience_instances = relationship("ExperienceInstance", back_populates="session")


class SessionParticipant(Base):
    __tablename__ = "session_participants"

    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sessions.id"), primary_key=True
    )
    participant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("participants.id"), primary_key=True
    )

    session = relationship("Session", back_populates="participant_links")
    participant = relationship("Participant", back_populates="session_links")
