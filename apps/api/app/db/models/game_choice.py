"""GameChoice model — stores answer options for How Well Do You Know rounds."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    Text,
    CheckConstraint,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, UUIDPKMixin


class GameChoice(Base, UUIDPKMixin):
    __tablename__ = "game_choices"

    game_round_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("game_rounds.id"), nullable=False
    )
    choice_text: Mapped[str] = mapped_column(Text, nullable=False)
    is_correct: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )
    source_type: Mapped[str] = mapped_column(Text, nullable=False)
    created_by_participant_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("participants.id"), nullable=True
    )
    original_ai_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    display_order: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    __table_args__ = (
        CheckConstraint(
            "source_type IN ('main_person', 'ai_generated', 'main_person_edited', 'player_fake', 'ai_fallback')",
            name="ck_game_choice_source_type",
        ),
        UniqueConstraint("game_round_id", "choice_text", name="uq_round_choice_text"),
    )

    game_round = relationship("GameRound", back_populates="choices")
    created_by = relationship("Participant")
