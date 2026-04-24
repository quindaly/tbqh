"""UserQuestionFeedback model."""

from __future__ import annotations

import uuid

from sqlalchemy import ForeignKey, Text, CheckConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, UUIDPKMixin, TimestampMixin


class UserQuestionFeedback(Base, UUIDPKMixin, TimestampMixin):
    __tablename__ = "user_question_feedback"

    participant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("participants.id"), nullable=False
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    question_item_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("question_items.id"), nullable=False
    )
    content_item_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("content_items.id"), nullable=True
    )
    experience_instance_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("experience_instances.id"), nullable=True
    )
    feedback: Mapped[str] = mapped_column(Text, nullable=False)

    __table_args__ = (
        CheckConstraint(
            "feedback IN ('like', 'dislike', 'skip')",
            name="ck_feedback_type",
        ),
    )
