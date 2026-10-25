"""Profile routes: commit group profile."""

from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db.models.group_profile import GroupProfile
from app.db.models.session import Session as SessionModel
from app.db.session import get_db
from app.services.intake.synthesis import commit_group_profile
from app.services.telemetry.events import log_event

logger = logging.getLogger(__name__)

router = APIRouter(tags=["profiles"])


class CommitGroupProfileRequest(BaseModel):
    provisional_group_profile_id: uuid.UUID


class CommitGroupProfileResponse(BaseModel):
    group_profile_id: uuid.UUID
    version: int


@router.post(
    "/sessions/{session_id}/group-profile/commit",
    response_model=CommitGroupProfileResponse,
)
def commit_profile(
    session_id: uuid.UUID,
    body: CommitGroupProfileRequest,
    db: Session = Depends(get_db),
):
    sess = db.get(SessionModel, session_id)
    if not sess:
        raise HTTPException(status_code=404, detail="Session not found")

    profile = db.get(GroupProfile, body.provisional_group_profile_id)
    if not profile or profile.group_id != sess.group_id:
        raise HTTPException(status_code=404, detail="Group profile not found")

    try:
        committed = commit_group_profile(db, sess, profile)
    except Exception:
        db.rollback()
        logger.exception("Group profile synthesis failed for session %s", session_id)
        raise HTTPException(
            status_code=502,
            detail="We couldn't build your group's profile just now. Please try again.",
        )

    log_event(
        db,
        "group_profile_created",
        session_id=session_id,
        payload={
            "group_profile_id": str(committed.id),
            "version": committed.version,
        },
    )
    db.commit()

    return CommitGroupProfileResponse(
        group_profile_id=committed.id,
        version=committed.version,
    )
