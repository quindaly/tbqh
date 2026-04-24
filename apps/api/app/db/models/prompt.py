"""PromptTemplate, PromptInstance, PromptResponse models."""

from __future__ import annotations

import uuid

from sqlalchemy import Boolean, ForeignKey, Integer, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, UUIDPKMixin, TimestampMixin


class PromptTemplate(Base, UUIDPKMixin, TimestampMixin):
    __tablename__ = "prompt_templates"

    name: Mapped[str] = mapped_column(Text, nullable=False)
    template: Mapped[str] = mapped_column(Text, nullable=False)


class PromptInstance(Base, UUIDPKMixin, TimestampMixin):
    __tablename__ = "prompt_instances"

    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sessions.id"), nullable=False
    )
    group_profile_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("group_profiles.id"), nullable=True
    )
    participant_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("participants.id"), nullable=True
    )
    experience_instance_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("experience_instances.id"), nullable=True
    )
    round_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    prompt_type: Mapped[str] = mapped_column(Text, nullable=False)
    prompt_text: Mapped[str] = mapped_column(Text, nullable=False)
    options: Mapped[dict | None] = mapped_column(
        JSONB, nullable=True
    )  # list of strings
    allow_other: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    responses = relationship("PromptResponse", back_populates="prompt_instance")


class PromptResponse(Base, UUIDPKMixin, TimestampMixin):
    __tablename__ = "prompt_responses"

    prompt_instance_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("prompt_instances.id"), nullable=False
    )
    participant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("participants.id"), nullable=False
    )
    selected_option: Mapped[str | None] = mapped_column(Text, nullable=True)
    other_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    normalized_value: Mapped[str | None] = mapped_column(Text, nullable=True)

    prompt_instance = relationship("PromptInstance", back_populates="responses")
