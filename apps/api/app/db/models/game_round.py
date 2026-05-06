"""GameRound model."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, Text, CheckConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, UUIDPKMixin


class GameRound(Base, UUIDPKMixin):
    __tablename__ = "game_rounds"

    experience_instance_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("experience_instances.id"), nullable=False
    )
    round_number: Mapped[int] = mapped_column(Integer, nullable=False)
    source_prompt_instance_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("prompt_instances.id"), nullable=True
    )
    source_response_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("prompt_responses.id"), nullable=True
    )
    answering_participant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("participants.id"), nullable=False
    )
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="pending")
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    revealed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # HWDYK-specific columns
    question_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    correct_choice_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("game_choices.id"), nullable=True
    )
    timer_duration: Mapped[int | None] = mapped_column(
        Integer, nullable=True, server_default="60"
    )
    round_locked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'active', 'revealed', 'completed', 'setup')",
            name="ck_game_round_status",
        ),
    )

    experience_instance = relationship(
        "ExperienceInstance", back_populates="game_rounds"
    )
    source_prompt_instance = relationship("PromptInstance")
    source_response = relationship("PromptResponse")
    answering_participant = relationship("Participant")
    guesses = relationship("GameGuess", back_populates="game_round")
    choices = relationship(
        "GameChoice",
        back_populates="game_round",
        foreign_keys="GameChoice.game_round_id",
    )
    mc_guesses = relationship("GameMCGuess", back_populates="game_round")
