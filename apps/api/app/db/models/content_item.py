"""ContentItem model – generic displayed content wrapper."""

from __future__ import annotations

import uuid

from sqlalchemy import ForeignKey, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, UUIDPKMixin, TimestampMixin


class ContentItem(Base, UUIDPKMixin, TimestampMixin):
    __tablename__ = "content_items"

    content_type: Mapped[str] = mapped_column(Text, nullable=False)
    source_question_item_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("question_items.id"), nullable=True
    )
    text: Mapped[str] = mapped_column(Text, nullable=False)
    metadata_: Mapped[dict | None] = mapped_column(
        "metadata", JSONB, nullable=True
    )
