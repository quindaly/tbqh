"""Blocklist and policy filters for recommendation pipeline."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.feedback import UserQuestionFeedback
from app.db.models.experience import ContentExposure, ExperienceInstance
from app.db.models.content_item import ContentItem


def get_blocked_question_ids(
    db: Session,
    *,
    participant_ids: list[uuid.UUID],
    user_ids: list[uuid.UUID] | None = None,
) -> set[uuid.UUID]:
    """Return question_item_ids that any of the given participants/users have disliked."""
    conditions = [
        UserQuestionFeedback.participant_id.in_(participant_ids),
        UserQuestionFeedback.feedback == "dislike",
    ]

    stmt = select(UserQuestionFeedback.question_item_id).where(*conditions)

    if user_ids:
        # Also include user-level dislikes
        stmt2 = (
            select(UserQuestionFeedback.question_item_id)
            .where(UserQuestionFeedback.user_id.in_(user_ids))
            .where(UserQuestionFeedback.feedback == "dislike")
        )
        from sqlalchemy import union
        stmt = union(stmt, stmt2)

    result = db.execute(stmt).scalars().all()
    return set(result)


def get_previously_shown_question_ids(
    db: Session,
    group_profile_id: uuid.UUID,
) -> set[uuid.UUID]:
    """Return question_item_ids already shown in any experience for this group_profile."""
    stmt = (
        select(ContentItem.source_question_item_id)
        .join(ContentExposure, ContentExposure.content_item_id == ContentItem.id)
        .join(
            ExperienceInstance,
            ExperienceInstance.id == ContentExposure.experience_instance_id,
        )
        .where(ExperienceInstance.group_profile_id == group_profile_id)
        .where(ContentItem.source_question_item_id.isnot(None))
    )
    result = db.execute(stmt).scalars().all()
    return set(result)
