"""GameGuess model."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, UUIDPKMixin


class GameGuess(Base, UUIDPKMixin):
    __tablename__ = "game_guesses"

    game_round_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("game_rounds.id"), nullable=False
    )
    guessing_participant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("participants.id"), nullable=False
    )
    guessed_participant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("participants.id"), nullable=False
    )
    is_correct: Mapped[bool] = mapped_column(Boolean, nullable=False)
    submitted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    __table_args__ = (
        UniqueConstraint(
            "game_round_id", "guessing_participant_id", name="uq_guess_per_round"
        ),
    )

    game_round = relationship("GameRound", back_populates="guesses")
    guessing_participant = relationship(
        "Participant", foreign_keys=[guessing_participant_id]
    )
    guessed_participant = relationship(
        "Participant", foreign_keys=[guessed_participant_id]
    )
