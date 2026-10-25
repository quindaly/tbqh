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
from app.db.models.user import User
from app.api.v1.dependencies import get_current_user_id
from app.db.session import get_db
from app.services.accounts import is_placeholder_email
from app.services.telemetry.events import log_event

router = APIRouter(prefix="/content", tags=["content"])


class FeedbackRequest(BaseModel):
    experience_instance_id: uuid.UUID
    participant_id: uuid.UUID
    feedback: str  # like | dislike | skip


def _participant_for_signed_in_user(
    db: Session, session_id: uuid.UUID, current: Participant, user: User
) -> Participant:
    """The participant that speaks for this signed-in user in this session.

    Someone who rated as a guest, or joined by code without an account, is a
    different participant from the account they have since signed in to. Their
    feedback belongs to the account, so give the account its own place in the
    session (keeping the name they were using) rather than trusting a
    participant id that someone else's browser could also send."""
    if current.user_id == user.id:
        return current
    if current.user_id is not None:
        owner = db.get(User, current.user_id)
        if owner is not None and not is_placeholder_email(owner.email):
            # Another real account's participant: not yours to speak for.
            raise HTTPException(status_code=403, detail="That isn't your place in this session.")
    mine = (
        db.query(Participant)
        .join(SessionParticipant, SessionParticipant.participant_id == Participant.id)
        .filter(
            SessionParticipant.session_id == session_id,
            Participant.user_id == user.id,
        )
        .order_by(Participant.created_at)
        .first()
    )
    if mine is not None:
        return mine
    mine = Participant(
        group_id=current.group_id,
        user_id=user.id,
        display_name=user.display_name or current.display_name,
        role="guest",
        join_type="authenticated",
    )
    db.add(mine)
    db.flush()
    db.add(SessionParticipant(session_id=session_id, participant_id=mine.id))
    db.flush()
    return mine


@router.post("/{content_item_id}/feedback")
def submit_feedback(
    content_item_id: uuid.UUID,
    body: FeedbackRequest,
    db: Session = Depends(get_db),
    user_id: uuid.UUID | None = Depends(get_current_user_id),
):
    ci = db.get(ContentItem, content_item_id)
    if not ci:
        raise HTTPException(status_code=404, detail="Content item not found")

    if body.feedback not in ("like", "dislike", "skip"):
        raise HTTPException(status_code=400, detail="Invalid feedback value")

    # Loving or blocking a question builds a profile and favorites list, which
    # need an account. Skipping is just "next" and stays open to everyone.
    account = db.get(User, user_id) if user_id else None
    if account is not None and is_placeholder_email(account.email):
        account = None
    if body.feedback in ("like", "dislike") and account is None:
        raise HTTPException(status_code=401, detail="Sign in to leave feedback.")

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

    if account is not None:
        participant = _participant_for_signed_in_user(db, exp.session_id, participant, account)

    # One rating per person per question: changing your mind replaces it.
    fb = (
        db.query(UserQuestionFeedback)
        .filter(
            UserQuestionFeedback.participant_id == participant.id,
            UserQuestionFeedback.content_item_id == content_item_id,
        )
        .first()
    )
    if fb is None:
        fb = UserQuestionFeedback(
            participant_id=participant.id,
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
        participant_id=participant.id,
        payload={
            "content_item_id": str(content_item_id),
            "feedback": body.feedback,
        },
    )
    db.commit()

    # The client keeps using this id from now on (it can differ from the one it sent).
    return {"ok": True, "participant_id": str(participant.id)}
