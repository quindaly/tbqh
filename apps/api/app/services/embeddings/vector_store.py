"""pgvector-based vector queries for candidate retrieval."""

from __future__ import annotations

import uuid
import logging

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.db.models.question_item import QuestionItem

logger = logging.getLogger(__name__)


def find_similar_questions(
    db: Session,
    embedding: list[float],
    *,
    limit: int = 200,
    excluded_ids: set[uuid.UUID] | None = None,
    excluded_categories: list[str] | None = None,
) -> list[tuple[QuestionItem, float]]:
    """Retrieve top-K question_items by cosine similarity to the given embedding.

    Returns list of (QuestionItem, distance) sorted by ascending distance (most similar first).
    """
    vec_literal = "[" + ",".join(str(v) for v in embedding) + "]"

    # Build the query with filters
    stmt = (
        select(
            QuestionItem,
            QuestionItem.embedding.cosine_distance(text(f"'{vec_literal}'::vector")).label("distance"),
        )
        .where(QuestionItem.status == "active")
        .where(QuestionItem.embedding.isnot(None))
    )

    if excluded_ids:
        stmt = stmt.where(QuestionItem.id.notin_(excluded_ids))

    if excluded_categories:
        # Exclude questions whose content_categories overlap with excluded
        for cat in excluded_categories:
            stmt = stmt.where(
                ~QuestionItem.content_categories.any(cat)
                | (QuestionItem.content_categories.is_(None))
            )

    stmt = stmt.order_by("distance").limit(limit)

    results = db.execute(stmt).all()
    return [(row[0], row[1]) for row in results]
