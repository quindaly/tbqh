"""Content routes: feedback."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db.models.content_item import ContentItem
from app.db.models.feedback import UserQuestionFeedback
from app.db.models.participant import Participant
from app.db.session import get_db
from app.services.telemetry.events import log_event

router = APIRouter(prefix="/content", tags=["content"])


class FeedbackRequest(BaseModel):
    experience_instance_id: uuid.UUID
    participant_id: uuid.UUID
    feedback: str  # like | dislike | skip


@router.post("/{content_item_id}/feedback")
def submit_feedback(
    content_item_id: uuid.UUID,
    body: FeedbackRequest,
    db: Session = Depends(get_db),
):
    ci = db.get(ContentItem, content_item_id)
    if not ci:
        raise HTTPException(status_code=404, detail="Content item not found")

    if body.feedback not in ("like", "dislike", "skip"):
        raise HTTPException(status_code=400, detail="Invalid feedback value")

    participant = db.get(Participant, body.participant_id)
    if not participant:
        raise HTTPException(status_code=404, detail="Participant not found")

    fb = UserQuestionFeedback(
        participant_id=body.participant_id,
        user_id=participant.user_id,
        question_item_id=ci.source_question_item_id,
        content_item_id=content_item_id,
        experience_instance_id=body.experience_instance_id,
        feedback=body.feedback,
    )
    db.add(fb)
    db.commit()

    log_event(
        db,
        "feedback_given",
        session_id=None,
        experience_instance_id=body.experience_instance_id,
        participant_id=body.participant_id,
        payload={
            "content_item_id": str(content_item_id),
            "feedback": body.feedback,
        },
    )
    db.commit()

    return {"ok": True}
