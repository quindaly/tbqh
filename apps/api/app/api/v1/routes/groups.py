"""Group routes."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db.models.group import Group
from app.db.models.participant import Participant
from app.db.session import get_db
from app.api.v1.dependencies import require_auth
from app.services.telemetry.events import log_event

router = APIRouter(prefix="/groups", tags=["groups"])


class CreateGroupRequest(BaseModel):
    name: str | None = None


class CreateGroupResponse(BaseModel):
    group_id: uuid.UUID
    host_participant_id: uuid.UUID


@router.post("", response_model=CreateGroupResponse)
def create_group(
    body: CreateGroupRequest = CreateGroupRequest(),
    user_id: uuid.UUID = Depends(require_auth),
    db: Session = Depends(get_db),
):
    group = Group(created_by_user_id=user_id, name=body.name)
    db.add(group)
    db.flush()

    host = Participant(
        group_id=group.id,
        user_id=user_id,
        display_name="Host",
        role="host",
        join_type="authenticated",
    )
    db.add(host)
    db.commit()
    db.refresh(group)
    db.refresh(host)

    return CreateGroupResponse(group_id=group.id, host_participant_id=host.id)
