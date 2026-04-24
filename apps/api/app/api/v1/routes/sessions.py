"""Session routes: create, get, join."""

from __future__ import annotations

import secrets
import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session, joinedload

from app.db.models.session import Session as SessionModel, SessionParticipant
from app.db.models.participant import Participant
from app.db.models.group import Group
from app.db.models.policy import PolicyProfile
from app.db.session import get_db
from app.api.v1.dependencies import require_auth, get_current_user_id
from app.services.telemetry.events import log_event

router = APIRouter(tags=["sessions"])


class CreateSessionRequest(BaseModel):
    group_id: uuid.UUID
    policy_profile_id: uuid.UUID


class CreateSessionResponse(BaseModel):
    session_id: uuid.UUID
    join_code: str


class JoinSessionRequest(BaseModel):
    join_code: str
    display_name: str
    join_mode: str  # anonymous | authenticated


class JoinSessionResponse(BaseModel):
    participant_id: uuid.UUID
    session_id: uuid.UUID
    group_id: uuid.UUID


class ParticipantView(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID | None = None
    display_name: str
    role: str
    join_type: str


class PolicyView(BaseModel):
    id: uuid.UUID
    name: str
    excluded_categories: list[str]


class SessionView(BaseModel):
    id: uuid.UUID
    group_id: uuid.UUID
    policy_profile: PolicyView
    status: str
    participants: list[ParticipantView]


@router.post("/sessions", response_model=CreateSessionResponse)
def create_session(
    body: CreateSessionRequest,
    user_id: uuid.UUID = Depends(require_auth),
    db: Session = Depends(get_db),
):
    # Verify group ownership
    group = db.get(Group, body.group_id)
    if not group or group.created_by_user_id != user_id:
        raise HTTPException(status_code=404, detail="Group not found")

    policy = db.get(PolicyProfile, body.policy_profile_id)
    if not policy:
        raise HTTPException(status_code=404, detail="Policy profile not found")

    join_code = secrets.token_urlsafe(6).upper()[:8]

    sess = SessionModel(
        group_id=body.group_id,
        policy_profile_id=body.policy_profile_id,
        join_code=join_code,
    )
    db.add(sess)
    db.flush()

    # Add host participant to session
    host = (
        db.query(Participant)
        .filter(Participant.group_id == body.group_id, Participant.role == "host")
        .first()
    )
    if host:
        sp = SessionParticipant(session_id=sess.id, participant_id=host.id)
        db.add(sp)

    db.commit()
    db.refresh(sess)

    log_event(db, "session_created", session_id=sess.id)
    db.commit()

    return CreateSessionResponse(session_id=sess.id, join_code=join_code)


@router.get("/sessions/{session_id}", response_model=SessionView)
def get_session(session_id: uuid.UUID, db: Session = Depends(get_db)):
    sess = db.get(SessionModel, session_id)
    if not sess:
        raise HTTPException(status_code=404, detail="Session not found")

    policy = db.get(PolicyProfile, sess.policy_profile_id)
    sp_rows = (
        db.query(SessionParticipant)
        .filter(SessionParticipant.session_id == session_id)
        .all()
    )
    participant_ids = [sp.participant_id for sp in sp_rows]
    participants = (
        db.query(Participant).filter(Participant.id.in_(participant_ids)).all()
    )

    return SessionView(
        id=sess.id,
        group_id=sess.group_id,
        policy_profile=PolicyView(
            id=policy.id,
            name=policy.name,
            excluded_categories=list(policy.excluded_categories or []),
        ),
        status=sess.status,
        participants=[
            ParticipantView(
                id=p.id,
                user_id=p.user_id,
                display_name=p.display_name,
                role=p.role,
                join_type=p.join_type,
            )
            for p in participants
        ],
    )


@router.post("/sessions/{session_id}/join", response_model=JoinSessionResponse)
def join_session(
    session_id: uuid.UUID,
    body: JoinSessionRequest,
    db: Session = Depends(get_db),
    user_id: uuid.UUID | None = Depends(get_current_user_id),
):
    sess = db.get(SessionModel, session_id)
    if not sess or sess.join_code != body.join_code:
        raise HTTPException(status_code=400, detail="Invalid join code")
    if sess.status != "active":
        raise HTTPException(status_code=400, detail="Session is not active")

    participant = Participant(
        group_id=sess.group_id,
        user_id=user_id if body.join_mode == "authenticated" and user_id else None,
        display_name=body.display_name,
        role="guest",
        join_type=body.join_mode,
    )
    db.add(participant)
    db.flush()

    sp = SessionParticipant(session_id=session_id, participant_id=participant.id)
    db.add(sp)
    db.commit()

    log_event(
        db,
        "participant_joined",
        session_id=session_id,
        participant_id=participant.id,
    )
    db.commit()

    return JoinSessionResponse(
        participant_id=participant.id,
        session_id=session_id,
        group_id=sess.group_id,
    )
