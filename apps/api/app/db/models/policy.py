"""PolicyProfile model."""

from __future__ import annotations

from sqlalchemy import Text
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, UUIDPKMixin, TimestampMixin


class PolicyProfile(Base, UUIDPKMixin, TimestampMixin):
    __tablename__ = "policy_profiles"

    name: Mapped[str] = mapped_column(Text, nullable=False)
    excluded_categories: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, server_default="{}"
    )

    sessions = relationship("Session", back_populates="policy_profile")
