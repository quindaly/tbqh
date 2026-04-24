"""Intake routes: submit group text, list followups, answer followups."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db.models.session import Session as SessionModel
from app.db.models.prompt import PromptInstance, PromptResponse
from app.db.session import get_db
from app.services.intake.followups import generate_followups
from app.services.telemetry.events import log_event

router = APIRouter(tags=["intake"])


class SubmitGroupTextRequest(BaseModel):
    text: str
    participant_id: uuid.UUID


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

    profile, instances = generate_followups(
        db, sess, body.text, body.participant_id
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
    instances = (
        db.query(PromptInstance)
        .filter(
            PromptInstance.session_id == session_id,
            PromptInstance.prompt_type == "group_followup",
        )
        .order_by(PromptInstance.created_at)
        .all()
    )
    return ListFollowupsResponse(
        prompts=[
            PromptInstanceView(
                id=i.id,
                prompt_type=i.prompt_type,
                prompt_text=i.prompt_text,
                options=list(i.options or []),
                allow_other=i.allow_other,
            )
            for i in instances
        ]
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

    resp = PromptResponse(
        prompt_instance_id=body.prompt_instance_id,
        participant_id=body.participant_id,
        selected_option=body.selected_option,
        other_text=body.other_text,
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
