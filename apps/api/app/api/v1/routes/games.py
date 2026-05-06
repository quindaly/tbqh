"""Game API routes – discovery, creation, lobby, gameplay, leaderboard."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.v1.dependencies import get_current_user_id, require_auth
from app.db.models.experience import ExperienceInstance
from app.db.session import get_db
from app.services.games import catalog, scoring
from app.services.games import who_knows_who as wkw
from app.services.games import how_well_do_you_know as hwdyk
from app.services.games.state import get_game_state_payload

router = APIRouter(tags=["games"])


# ---- request / response models ----


class CreateGameBody(BaseModel):
    display_name: str


class CreateHWDYKBody(BaseModel):
    display_name: str
    mode: str = "default"
    num_questions: int = 5
    intimacy_level: str = "personal"


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


class SelectMainPersonBody(BaseModel):
    host_participant_id: str
    main_person_participant_id: str


class MainPersonAnswerBody(BaseModel):
    prompt_instance_id: str
    participant_id: str
    answer_text: str


class EditChoiceBody(BaseModel):
    participant_id: str
    new_text: str


class RegenerateBody(BaseModel):
    participant_id: str


class FakeAnswerBody(BaseModel):
    round_id: str
    participant_id: str
    fake_text: str


class MCGuessBody(BaseModel):
    participant_id: str
    choice_id: str


# ---- helpers ----


def _get_experience(db: Session, experience_id: str) -> ExperienceInstance:
    exp = db.get(ExperienceInstance, uuid.UUID(experience_id))
    if not exp or exp.experience_type != "who_knows_who":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Experience not found"
        )
    return exp


def _get_hwdyk_experience(db: Session, experience_id: str) -> ExperienceInstance:
    exp = db.get(ExperienceInstance, uuid.UUID(experience_id))
    if not exp or exp.experience_type != "how_well_do_you_know":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Experience not found"
        )
    return exp


def _get_any_experience(db: Session, experience_id: str) -> ExperienceInstance:
    exp = db.get(ExperienceInstance, uuid.UUID(experience_id))
    if not exp:
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
    if game_slug == "how-well-do-you-know":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Use /games/how-well-do-you-know/create with mode parameter",
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


# ===========================================================
# How Well Do You Know [Person]? endpoints
# ===========================================================


@router.post("/games/how-well-do-you-know/create")
def create_hwdyk_game(
    body: CreateHWDYKBody,
    user_id: uuid.UUID | None = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    return hwdyk.create_game(
        db,
        user_id=user_id,
        display_name=body.display_name,
        mode=body.mode,
        num_questions=body.num_questions,
        intimacy_level=body.intimacy_level,
    )


@router.post("/games/how-well-do-you-know/join")
def join_hwdyk_game(
    body: JoinGameBody,
    user_id: uuid.UUID | None = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    return hwdyk.join_game(
        db,
        join_code=body.join_code,
        display_name=body.display_name,
        user_id=user_id,
        join_mode=body.join_mode,
    )


@router.get("/experiences/{experience_id}/hwdyk/lobby")
def get_hwdyk_lobby(experience_id: str, db: Session = Depends(get_db)):
    exp = _get_hwdyk_experience(db, experience_id)
    return hwdyk.get_lobby_payload(db, exp)


@router.post("/experiences/{experience_id}/select-main-person")
def select_main_person(
    experience_id: str,
    body: SelectMainPersonBody,
    db: Session = Depends(get_db),
):
    exp = _get_hwdyk_experience(db, experience_id)
    hwdyk.select_main_person(
        db,
        exp,
        uuid.UUID(body.host_participant_id),
        uuid.UUID(body.main_person_participant_id),
    )
    return {"ok": True}


@router.post("/experiences/{experience_id}/start-setup")
def start_hwdyk_setup(
    experience_id: str,
    body: StartBody,
    db: Session = Depends(get_db),
):
    exp = _get_hwdyk_experience(db, experience_id)
    return hwdyk.start_setup(db, exp, uuid.UUID(body.participant_id))


@router.get("/experiences/{experience_id}/main-person-questions")
def get_main_person_questions(experience_id: str, db: Session = Depends(get_db)):
    exp = _get_hwdyk_experience(db, experience_id)
    return {"questions": hwdyk.get_main_person_questions(db, exp.id)}


@router.post("/experiences/{experience_id}/main-person-answer")
def submit_main_person_answer(
    experience_id: str,
    body: MainPersonAnswerBody,
    db: Session = Depends(get_db),
):
    exp = _get_hwdyk_experience(db, experience_id)
    return hwdyk.submit_main_person_answer(
        db,
        exp,
        uuid.UUID(body.prompt_instance_id),
        uuid.UUID(body.participant_id),
        body.answer_text,
    )


@router.get("/experiences/{experience_id}/review-choices")
def get_review_choices(
    experience_id: str,
    participant_id: str = Query(...),
    db: Session = Depends(get_db),
):
    return {
        "rounds": hwdyk.get_review_data(
            db, uuid.UUID(experience_id), uuid.UUID(participant_id)
        )
    }


@router.post("/experiences/{experience_id}/choices/{choice_id}/edit")
def edit_choice(
    experience_id: str,
    choice_id: str,
    body: EditChoiceBody,
    db: Session = Depends(get_db),
):
    exp = _get_hwdyk_experience(db, experience_id)
    hwdyk.edit_choice(
        db, exp, uuid.UUID(choice_id), uuid.UUID(body.participant_id), body.new_text
    )
    return {"ok": True}


@router.post("/experiences/{experience_id}/choices/{choice_id}/regenerate")
def regenerate_choice(
    experience_id: str,
    choice_id: str,
    body: RegenerateBody,
    db: Session = Depends(get_db),
):
    exp = _get_hwdyk_experience(db, experience_id)
    return hwdyk.regenerate_choice(
        db, exp, uuid.UUID(choice_id), uuid.UUID(body.participant_id)
    )


@router.post("/experiences/{experience_id}/confirm-choices")
def confirm_choices(
    experience_id: str,
    body: StartBody,
    db: Session = Depends(get_db),
):
    exp = _get_hwdyk_experience(db, experience_id)
    hwdyk.confirm_choices(db, exp, uuid.UUID(body.participant_id))
    return {"ok": True}


@router.get("/experiences/{experience_id}/fake-answer-questions")
def get_fake_answer_questions(
    experience_id: str,
    participant_id: str = Query(...),
    db: Session = Depends(get_db),
):
    return {
        "questions": hwdyk.get_fake_answer_questions(
            db, uuid.UUID(experience_id), uuid.UUID(participant_id)
        )
    }


@router.post("/experiences/{experience_id}/fake-answer")
def submit_fake_answer(
    experience_id: str,
    body: FakeAnswerBody,
    db: Session = Depends(get_db),
):
    exp = _get_hwdyk_experience(db, experience_id)
    return hwdyk.submit_fake_answer(
        db,
        exp,
        uuid.UUID(body.round_id),
        uuid.UUID(body.participant_id),
        body.fake_text,
    )


@router.get("/experiences/{experience_id}/fake-answer-progress")
def get_fake_answer_progress(experience_id: str, db: Session = Depends(get_db)):
    return hwdyk.get_fake_answer_progress(db, uuid.UUID(experience_id))


@router.post("/experiences/{experience_id}/lock-party-mode")
def lock_party_mode(
    experience_id: str,
    body: StartBody,
    db: Session = Depends(get_db),
):
    exp = _get_hwdyk_experience(db, experience_id)
    hwdyk.lock_party_mode(db, exp, uuid.UUID(body.participant_id))
    return {"ok": True}


@router.post("/experiences/{experience_id}/start-live")
def start_live_game(
    experience_id: str,
    body: StartBody,
    db: Session = Depends(get_db),
):
    exp = _get_hwdyk_experience(db, experience_id)
    hwdyk.start_live_game(db, exp, uuid.UUID(body.participant_id))
    return {"ok": True}


@router.get("/experiences/{experience_id}/hwdyk/state")
def get_hwdyk_state(experience_id: str, db: Session = Depends(get_db)):
    exp = _get_hwdyk_experience(db, experience_id)
    return hwdyk.get_round_state(db, exp)


@router.post("/experiences/{experience_id}/rounds/{round_id}/mc-guess")
def submit_mc_guess(
    experience_id: str,
    round_id: str,
    body: MCGuessBody,
    db: Session = Depends(get_db),
):
    exp = _get_hwdyk_experience(db, experience_id)
    return hwdyk.submit_mc_guess(
        db,
        exp,
        uuid.UUID(round_id),
        uuid.UUID(body.participant_id),
        uuid.UUID(body.choice_id),
    )


@router.post("/experiences/{experience_id}/rounds/{round_id}/hwdyk-reveal")
def reveal_hwdyk_round(
    experience_id: str,
    round_id: str,
    db: Session = Depends(get_db),
):
    exp = _get_hwdyk_experience(db, experience_id)
    hwdyk.reveal_round(db, exp, uuid.UUID(round_id))
    return {"ok": True}


@router.post("/experiences/{experience_id}/rounds/{round_id}/hwdyk-advance")
def advance_hwdyk_round(
    experience_id: str,
    round_id: str,
    db: Session = Depends(get_db),
):
    exp = _get_hwdyk_experience(db, experience_id)
    return hwdyk.advance_round(db, exp, uuid.UUID(round_id))


@router.get("/experiences/{experience_id}/hwdyk/leaderboard")
def get_hwdyk_leaderboard(experience_id: str, db: Session = Depends(get_db)):
    exp = _get_hwdyk_experience(db, experience_id)
    return {"leaderboard": hwdyk.compute_hwdyk_scores(db, exp.id)}


@router.post("/experiences/{experience_id}/hwdyk/replay")
def replay_hwdyk_game(experience_id: str, db: Session = Depends(get_db)):
    exp = _get_hwdyk_experience(db, experience_id)
    return hwdyk.replay_game(db, exp)
