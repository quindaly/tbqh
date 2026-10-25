"""Intake routes: submit group text, list followups, answer followups."""

from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from app.db.models.group_profile import GroupProfile
from app.db.models.session import Session as SessionModel, SessionParticipant
from app.db.models.prompt import PromptInstance, PromptResponse
from app.db.session import get_db
from app.services.intake.followups import generate_followups
from app.services.intake.options import is_other_option
from app.services.telemetry.events import log_event

logger = logging.getLogger(__name__)

router = APIRouter(tags=["intake"])

MAX_GROUP_TEXT = 2000
MAX_OTHER_TEXT = 200


def require_session_participant(
    db: Session, session_id: uuid.UUID, participant_id: uuid.UUID
) -> None:
    """Only people who are in the session may add to it."""
    link = db.get(SessionParticipant, (session_id, participant_id))
    if link is None:
        raise HTTPException(
            status_code=403, detail="You're not part of this session."
        )


class SubmitGroupTextRequest(BaseModel):
    text: str = Field(max_length=MAX_GROUP_TEXT)
    participant_id: uuid.UUID

    @field_validator("text")
    @classmethod
    def _not_blank(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Tell us a little about your group first.")
        return v


class SubmitGroupTextResponse(BaseModel):
    provisional_group_profile_id: uuid.UUID
    followups_created: int


class PromptInstanceView(BaseModel):
    id: uuid.UUID
    prompt_type: str
    prompt_text: str
    options: list[str]
    allow_other: bool


class ListFollowupsResponse(BaseModel):
    prompts: list[PromptInstanceView]
    # The profile these follow-ups belong to (the most recent description).
    provisional_group_profile_id: uuid.UUID | None = None


class AnswerFollowupRequest(BaseModel):
    prompt_instance_id: uuid.UUID
    participant_id: uuid.UUID
    selected_option: str | None = None
    other_text: str | None = None


@router.post(
    "/sessions/{session_id}/group-text",
    response_model=SubmitGroupTextResponse,
)
def submit_group_text(
    session_id: uuid.UUID,
    body: SubmitGroupTextRequest,
    db: Session = Depends(get_db),
):
    sess = db.get(SessionModel, session_id)
    if not sess:
        raise HTTPException(status_code=404, detail="Session not found")
    require_session_participant(db, session_id, body.participant_id)

    try:
        profile, instances = generate_followups(
            db, sess, body.text, body.participant_id
        )
    except Exception:
        db.rollback()
        logger.exception("Follow-up generation failed for session %s", session_id)
        raise HTTPException(
            status_code=502,
            detail="We couldn't put your follow-up questions together just now. Please try again.",
        )
    db.commit()

    log_event(
        db,
        "group_text_submitted",
        session_id=session_id,
        participant_id=body.participant_id,
        payload={"text_length": len(body.text)},
    )
    log_event(
        db,
        "followup_prompt_generated",
        session_id=session_id,
        payload={"count": len(instances)},
    )
    db.commit()

    return SubmitGroupTextResponse(
        provisional_group_profile_id=profile.id,
        followups_created=len(instances),
    )


@router.get(
    "/sessions/{session_id}/followups",
    response_model=ListFollowupsResponse,
)
def list_followups(session_id: uuid.UUID, db: Session = Depends(get_db)):
    # Going back and describing the group again creates a fresh set of
    # follow-ups under a newer profile version. Only show that latest set,
    # not the old ones stacked on top.
    latest_profile_id = (
        db.query(GroupProfile.id)
        .join(PromptInstance, PromptInstance.group_profile_id == GroupProfile.id)
        .filter(
            PromptInstance.session_id == session_id,
            PromptInstance.prompt_type == "group_followup",
        )
        .order_by(GroupProfile.version.desc(), GroupProfile.created_at.desc())
        .limit(1)
        .scalar()
    )
    instances = []
    if latest_profile_id is not None:
        instances = (
            db.query(PromptInstance)
            .filter(
                PromptInstance.session_id == session_id,
                PromptInstance.prompt_type == "group_followup",
                PromptInstance.group_profile_id == latest_profile_id,
            )
            .order_by(PromptInstance.round_number, PromptInstance.id)
            .all()
        )
    return ListFollowupsResponse(
        provisional_group_profile_id=latest_profile_id,
        prompts=[
            PromptInstanceView(
                id=i.id,
                prompt_type=i.prompt_type,
                prompt_text=i.prompt_text,
                options=list(i.options or []),
                allow_other=i.allow_other,
            )
            for i in instances
        ],
    )


@router.post("/sessions/{session_id}/followups/answer")
def answer_followup(
    session_id: uuid.UUID,
    body: AnswerFollowupRequest,
    db: Session = Depends(get_db),
):
    pi = db.get(PromptInstance, body.prompt_instance_id)
    if not pi or pi.session_id != session_id:
        raise HTTPException(status_code=404, detail="Prompt not found")
    require_session_participant(db, session_id, body.participant_id)

    options = list(pi.options or [])
    selected = (body.selected_option or "").strip() or None
    other_text = (body.other_text or "").strip() or None

    if selected is not None and not is_other_option(selected):
        if selected not in options:
            raise HTTPException(status_code=400, detail="That isn't one of the choices.")
        other_text = None
    else:
        # "Other": the written answer is the answer.
        if other_text is None:
            raise HTTPException(status_code=400, detail="Type your answer, or pick one of the choices.")
        if len(other_text) > MAX_OTHER_TEXT:
            raise HTTPException(
                status_code=400,
                detail=f"Please keep your answer under {MAX_OTHER_TEXT} characters.",
            )
        selected = None

    # One answer per person per question: answering again replaces the old one
    # (otherwise a reload or a back-and-forth doubles up in the group profile).
    db.query(PromptResponse).filter(
        PromptResponse.prompt_instance_id == body.prompt_instance_id,
        PromptResponse.participant_id == body.participant_id,
    ).delete(synchronize_session=False)

    resp = PromptResponse(
        prompt_instance_id=body.prompt_instance_id,
        participant_id=body.participant_id,
        selected_option=selected,
        other_text=other_text,
    )
    db.add(resp)
    db.commit()

    log_event(
        db,
        "followup_answered",
        session_id=session_id,
        participant_id=body.participant_id,
        payload={"prompt_instance_id": str(body.prompt_instance_id)},
    )
    db.commit()

    return {"ok": True}
