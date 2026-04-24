"""ExperienceInstance and ContentExposure models."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Integer,
    Text,
    CheckConstraint,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, UUIDPKMixin, TimestampMixin


class ExperienceInstance(Base, UUIDPKMixin, TimestampMixin):
    __tablename__ = "experience_instances"

    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sessions.id"), nullable=False
    )
    group_profile_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("group_profiles.id"), nullable=True
    )
    experience_type: Mapped[str] = mapped_column(Text, nullable=False)
    config: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="active")

    # Game-specific columns
    game_state: Mapped[str | None] = mapped_column(Text, nullable=True)
    current_round: Mapped[int | None] = mapped_column(
        Integer, nullable=True, server_default="0"
    )
    max_rounds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    game_config: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    parent_experience_instance_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("experience_instances.id"), nullable=True
    )

    __table_args__ = (
        CheckConstraint(
            "status IN ('active', 'completed')", name="ck_experience_status"
        ),
        CheckConstraint(
            "experience_type IN ('discussion_recs', 'who_knows_who')",
            name="ck_experience_type",
        ),
        CheckConstraint(
            "game_state IS NULL OR game_state IN ('lobby', 'question_collection', 'ready_to_start', 'round_active', 'round_reveal', 'leaderboard', 'completed')",
            name="ck_experience_game_state",
        ),
    )

    session = relationship("Session", back_populates="experience_instances")
    exposures = relationship("ContentExposure", back_populates="experience_instance")
    parent = relationship(
        "ExperienceInstance", remote_side="ExperienceInstance.id", uselist=False
    )
    game_rounds = relationship("GameRound", back_populates="experience_instance")


class ContentExposure(Base, UUIDPKMixin):
    __tablename__ = "content_exposures"

    experience_instance_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("experience_instances.id"), nullable=False
    )
    content_item_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("content_items.id"), nullable=False
    )
    shown_to_participant_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("participants.id"), nullable=True
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    shown_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    __table_args__ = (
        UniqueConstraint(
            "experience_instance_id",
            "content_item_id",
            name="uq_exposure_content",
        ),
    )

    experience_instance = relationship("ExperienceInstance", back_populates="exposures")
