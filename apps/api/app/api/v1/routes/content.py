"""Content routes: feedback."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db.models.content_item import ContentItem
from app.db.models.experience import ContentExposure, ExperienceInstance
from app.db.models.feedback import UserQuestionFeedback
from app.db.models.participant import Participant
from app.db.models.session import SessionParticipant
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

    exp = db.get(ExperienceInstance, body.experience_instance_id)
    if not exp:
        raise HTTPException(status_code=404, detail="Experience not found")
    # The question has to have been shown in this experience, to someone who is in it.
    shown = (
        db.query(ContentExposure.id)
        .filter(
            ContentExposure.experience_instance_id == exp.id,
            ContentExposure.content_item_id == content_item_id,
        )
        .first()
    )
    in_session = db.get(SessionParticipant, (exp.session_id, body.participant_id))
    if shown is None or in_session is None:
        raise HTTPException(status_code=403, detail="That question isn't part of your session.")

    if ci.source_question_item_id is None:
        raise HTTPException(status_code=400, detail="This question can't be rated.")

    # One rating per person per question: changing your mind replaces it.
    fb = (
        db.query(UserQuestionFeedback)
        .filter(
            UserQuestionFeedback.participant_id == body.participant_id,
            UserQuestionFeedback.content_item_id == content_item_id,
        )
        .first()
    )
    if fb is None:
        fb = UserQuestionFeedback(
            participant_id=body.participant_id,
            user_id=participant.user_id,
            question_item_id=ci.source_question_item_id,
            content_item_id=content_item_id,
            experience_instance_id=body.experience_instance_id,
            feedback=body.feedback,
        )
        db.add(fb)
    else:
        fb.feedback = body.feedback
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
