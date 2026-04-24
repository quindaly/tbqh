"""User routes: favorites, blocked."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db.models.feedback import UserQuestionFeedback
from app.db.models.question_item import QuestionItem
from app.db.models.user import User
from app.db.session import get_db
from app.api.v1.dependencies import get_current_user

router = APIRouter(prefix="/users", tags=["users"])


class FavoriteItem(BaseModel):
    question_item_id: str
    question_text: str
    liked_at: str


class FavoritesResponse(BaseModel):
    question_items: list[FavoriteItem]


class BlockedItem(BaseModel):
    question_item_id: str
    question_text: str
    blocked_at: str


class BlockedResponse(BaseModel):
    question_items: list[BlockedItem]


@router.get("/me/favorites", response_model=FavoritesResponse)
def get_favorites(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    rows = (
        db.query(UserQuestionFeedback, QuestionItem)
        .join(
            QuestionItem,
            QuestionItem.id == UserQuestionFeedback.question_item_id,
        )
        .filter(
            UserQuestionFeedback.user_id == user.id,
            UserQuestionFeedback.feedback == "like",
        )
        .order_by(UserQuestionFeedback.created_at.desc())
        .all()
    )
    return FavoritesResponse(
        question_items=[
            FavoriteItem(
                question_item_id=str(fb.question_item_id),
                question_text=q.question_text,
                liked_at=fb.created_at.isoformat(),
            )
            for fb, q in rows
        ]
    )


@router.get("/me/blocked", response_model=BlockedResponse)
def get_blocked(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    rows = (
        db.query(UserQuestionFeedback, QuestionItem)
        .join(
            QuestionItem,
            QuestionItem.id == UserQuestionFeedback.question_item_id,
        )
        .filter(
            UserQuestionFeedback.user_id == user.id,
            UserQuestionFeedback.feedback == "dislike",
        )
        .order_by(UserQuestionFeedback.created_at.desc())
        .all()
    )
    return BlockedResponse(
        question_items=[
            BlockedItem(
                question_item_id=str(fb.question_item_id),
                question_text=q.question_text,
                blocked_at=fb.created_at.isoformat(),
            )
            for fb, q in rows
        ]
    )
