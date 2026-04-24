"""QuestionItem model – human-authored discussion dataset."""

from __future__ import annotations

from pgvector.sqlalchemy import Vector
from sqlalchemy import Integer, Text, CheckConstraint
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, UUIDPKMixin, TimestampMixin


class QuestionItem(Base, UUIDPKMixin, TimestampMixin):
    __tablename__ = "question_items"

    question_text: Mapped[str] = mapped_column(Text, nullable=False)
    embedding = mapped_column(Vector(1536), nullable=True)
    status: Mapped[str] = mapped_column(
        Text, nullable=False, server_default="active"
    )
    content_categories: Mapped[list[str] | None] = mapped_column(
        ARRAY(Text), nullable=True
    )
    topics: Mapped[list[str] | None] = mapped_column(ARRAY(Text), nullable=True)
    audience_fit: Mapped[list[str] | None] = mapped_column(ARRAY(Text), nullable=True)
    depth_level: Mapped[int | None] = mapped_column(Integer, nullable=True)

    __table_args__ = (
        CheckConstraint(
            "status IN ('active', 'retired')", name="ck_question_item_status"
        ),
    )
