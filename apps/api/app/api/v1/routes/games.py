"""Game API routes – discovery, creation, lobby, gameplay, leaderboard."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.v1.dependencies import get_current_user_id, require_auth
from app.db.models.experience import ExperienceInstance
from app.db.session import get_db
from app.services.games import catalog, scoring
from app.services.games import who_knows_who as wkw
from app.services.games.state import get_game_state_payload

router = APIRouter(tags=["games"])


# ---- request / response models ----


class CreateGameBody(BaseModel):
    display_name: str


class JoinGameBody(BaseModel):
    join_code: str
    display_name: str
    join_mode: str = "anonymous"


class SubmitAnswerBody(BaseModel):
    prompt_instance_id: str
    participant_id: str
    answer_text: str


class SubmitGuessBody(BaseModel):
    guessing_participant_id: str
    guessed_participant_id: str


class StartBody(BaseModel):
    participant_id: str


# ---- helpers ----


def _get_experience(db: Session, experience_id: str) -> ExperienceInstance:
    exp = db.get(ExperienceInstance, uuid.UUID(experience_id))
    if not exp or exp.experience_type != "who_knows_who":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Experience not found"
        )
    return exp


# ---- game discovery ----


@router.get("/games")
def list_games():
    return {"games": catalog.list_games()}


# ---- create / join ----


@router.post("/games/{game_slug}/create")
def create_game(
    game_slug: str,
    body: CreateGameBody,
    user_id: uuid.UUID | None = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    game = catalog.get_game(game_slug)
    if not game:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Game not found"
        )
    return wkw.create_game(db, user_id=user_id, display_name=body.display_name)


@router.post("/games/{game_slug}/join")
def join_game(
    game_slug: str,
    body: JoinGameBody,
    user_id: uuid.UUID | None = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    game = catalog.get_game(game_slug)
    if not game:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Game not found"
        )
    return wkw.join_game(
        db,
        join_code=body.join_code,
        display_name=body.display_name,
        user_id=user_id,
        join_mode=body.join_mode,
    )


# ---- lobby ----


@router.get("/experiences/{experience_id}/lobby")
def get_lobby(experience_id: str, db: Session = Depends(get_db)):
    exp = _get_experience(db, experience_id)
    return wkw.get_lobby_payload(db, exp)


# ---- answer collection ----


@router.post("/experiences/{experience_id}/start")
def start_collection(
    experience_id: str,
    body: StartBody,
    db: Session = Depends(get_db),
):
    exp = _get_experience(db, experience_id)
    return wkw.start_answer_collection(db, exp, uuid.UUID(body.participant_id))


@router.get("/experiences/{experience_id}/prompts")
def get_prompts(experience_id: str, db: Session = Depends(get_db)):
    exp = _get_experience(db, experience_id)
    return {"prompts": wkw.get_prompts_for_experience(db, exp.id)}


@router.post("/experiences/{experience_id}/prompts/answer")
def submit_answer(
    experience_id: str,
    body: SubmitAnswerBody,
    db: Session = Depends(get_db),
):
    exp = _get_experience(db, experience_id)
    return wkw.submit_self_answer(
        db,
        experience=exp,
        prompt_instance_id=uuid.UUID(body.prompt_instance_id),
        participant_id=uuid.UUID(body.participant_id),
        answer_text=body.answer_text,
    )


# ---- game state ----


@router.get("/experiences/{experience_id}/state")
def get_state(experience_id: str, db: Session = Depends(get_db)):
    exp = _get_experience(db, experience_id)
    return get_game_state_payload(db, exp)


# ---- rounds ----


@router.post("/experiences/{experience_id}/rounds/{round_id}/guess")
def submit_guess(
    experience_id: str,
    round_id: str,
    body: SubmitGuessBody,
    db: Session = Depends(get_db),
):
    exp = _get_experience(db, experience_id)
    return wkw.submit_guess(
        db,
        experience=exp,
        round_id=uuid.UUID(round_id),
        guessing_participant_id=uuid.UUID(body.guessing_participant_id),
        guessed_participant_id=uuid.UUID(body.guessed_participant_id),
    )


@router.post("/experiences/{experience_id}/rounds/{round_id}/reveal")
def reveal_round(
    experience_id: str,
    round_id: str,
    db: Session = Depends(get_db),
):
    exp = _get_experience(db, experience_id)
    return wkw.reveal_round(db, experience=exp, round_id=uuid.UUID(round_id))


@router.post("/experiences/{experience_id}/rounds/{round_id}/advance")
def advance_round(
    experience_id: str,
    round_id: str,
    db: Session = Depends(get_db),
):
    exp = _get_experience(db, experience_id)
    return wkw.advance_round(db, experience=exp, round_id=uuid.UUID(round_id))


# ---- leaderboard ----


@router.get("/experiences/{experience_id}/leaderboard")
def get_leaderboard(experience_id: str, db: Session = Depends(get_db)):
    exp = _get_experience(db, experience_id)
    return {"leaderboard": scoring.compute_scores(db, exp.id)}


# ---- replay ----


@router.post("/experiences/{experience_id}/replay")
def replay_game(experience_id: str, db: Session = Depends(get_db)):
    exp = _get_experience(db, experience_id)
    return wkw.replay_game(db, exp)
