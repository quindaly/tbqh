"""Experience routes: create, recommendations, more."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db.models.experience import ExperienceInstance
from app.db.models.group_profile import GroupProfile
from app.db.models.session import Session as SessionModel
from app.db.session import get_db
from app.services.recommend.ranker import generate_recommendations
from app.services.telemetry.events import log_event

router = APIRouter(tags=["experiences"])


class CreateExperienceRequest(BaseModel):
    group_profile_id: uuid.UUID
    experience_type: str = "discussion_recs"
    config: dict | None = None


class CreateExperienceResponse(BaseModel):
    experience_instance_id: uuid.UUID


class ContentItemView(BaseModel):
    id: uuid.UUID
    content_type: str
    text: str
    metadata: dict


class GenerateRecommendationsRequest(BaseModel):
    batch_size: int = 10
    config_overrides: dict | None = None


class GenerateRecommendationsResponse(BaseModel):
    content_items: list[ContentItemView]


@router.post(
    "/sessions/{session_id}/experiences",
    response_model=CreateExperienceResponse,
)
def create_experience(
    session_id: uuid.UUID,
    body: CreateExperienceRequest,
    db: Session = Depends(get_db),
):
    sess = db.get(SessionModel, session_id)
    if not sess:
        raise HTTPException(status_code=404, detail="Session not found")

    profile = db.get(GroupProfile, body.group_profile_id)
    if not profile or not profile.is_active:
        raise HTTPException(status_code=400, detail="Invalid or inactive group profile")

    exp = ExperienceInstance(
        session_id=session_id,
        group_profile_id=body.group_profile_id,
        experience_type=body.experience_type,
        config=body.config,
    )
    db.add(exp)
    db.commit()
    db.refresh(exp)

    return CreateExperienceResponse(experience_instance_id=exp.id)


@router.post(
    "/experiences/{experience_id}/recommendations",
    response_model=GenerateRecommendationsResponse,
)
def get_recommendations(
    experience_id: uuid.UUID,
    body: GenerateRecommendationsRequest = GenerateRecommendationsRequest(),
    db: Session = Depends(get_db),
):
    exp = db.get(ExperienceInstance, experience_id)
    if not exp:
        raise HTTPException(status_code=404, detail="Experience not found")

    overrides = body.config_overrides or {}
    if body.batch_size != 10:
        overrides["batch_size"] = body.batch_size

    items = generate_recommendations(db, exp, config_overrides=overrides)

    log_event(
        db,
        "recommendation_generated",
        session_id=exp.session_id,
        experience_instance_id=exp.id,
        payload={"count": len(items)},
    )
    db.commit()

    return GenerateRecommendationsResponse(
        content_items=[
            ContentItemView(
                id=ci.id,
                content_type=ci.content_type,
                text=ci.text,
                metadata=ci.metadata_ or {},
            )
            for ci in items
        ]
    )


@router.post(
    "/experiences/{experience_id}/more",
    response_model=GenerateRecommendationsResponse,
)
def get_more_recommendations(
    experience_id: uuid.UUID,
    body: GenerateRecommendationsRequest = GenerateRecommendationsRequest(),
    db: Session = Depends(get_db),
):
    """Get 10 more – same experience instance, new batch appended."""
    exp = db.get(ExperienceInstance, experience_id)
    if not exp:
        raise HTTPException(status_code=404, detail="Experience not found")

    overrides = body.config_overrides or {}
    if body.batch_size != 10:
        overrides["batch_size"] = body.batch_size

    items = generate_recommendations(db, exp, config_overrides=overrides)

    log_event(
        db,
        "get_more_clicked",
        session_id=exp.session_id,
        experience_instance_id=exp.id,
        payload={"count": len(items)},
    )
    db.commit()

    return GenerateRecommendationsResponse(
        content_items=[
            ContentItemView(
                id=ci.id,
                content_type=ci.content_type,
                text=ci.text,
                metadata=ci.metadata_ or {},
            )
            for ci in items
        ]
    )
