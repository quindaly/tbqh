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
    # Revision of the choice the client last saw; stale writes get a 409.
    expected_revision: int | None = None


class RegenerateBody(BaseModel):
    participant_id: str
    expected_revision: int | None = None


class ConfirmChoicesBody(BaseModel):
    participant_id: str
    # choice id -> revision the client has saved
    revisions: dict[str, int] | None = None


class FakeAnswerBody(BaseModel):
    round_id: str
    participant_id: str
    fake_text: str


class MCGuessBody(BaseModel):
    participant_id: str
    choice_id: str


# ---- helpers ----


def _uuid_or_404(value: str, detail: str = "Not found") -> uuid.UUID:
    """Parse a UUID taken from the URL path.

    A malformed ID (an old, mistyped or truncated link) must produce a normal
    404. Letting ``uuid.UUID`` raise would surface as an unhandled 500, which
    is sent without CORS headers and so looks like a network error in the
    browser instead of an error the page can handle.
    """
    try:
        return uuid.UUID(value)
    except (ValueError, TypeError, AttributeError):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=detail)


def _participant_uuid(value: str) -> uuid.UUID:
    """Parse a participant ID from a body/query. Malformed -> 400, not a 500."""
    try:
        return uuid.UUID(value)
    except (ValueError, TypeError, AttributeError):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid participant ID"
        )


def _get_experience(db: Session, experience_id: str) -> ExperienceInstance:
    exp_id = _uuid_or_404(experience_id, "Experience not found")
    exp = db.get(ExperienceInstance, exp_id)
    if not exp or exp.experience_type != "who_knows_who":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Experience not found"
        )
    return exp


def _get_hwdyk_experience(db: Session, experience_id: str) -> ExperienceInstance:
    exp_id = _uuid_or_404(experience_id, "Experience not found")
    exp = db.get(ExperienceInstance, exp_id)
    if not exp or exp.experience_type != "how_well_do_you_know":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Experience not found"
        )
    return exp


def _get_any_experience(db: Session, experience_id: str) -> ExperienceInstance:
    exp_id = _uuid_or_404(experience_id, "Experience not found")
    exp = db.get(ExperienceInstance, exp_id)
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
    return wkw.start_answer_collection(db, exp, _participant_uuid(body.participant_id))


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
        prompt_instance_id=_participant_uuid(body.prompt_instance_id),
        participant_id=_participant_uuid(body.participant_id),
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
        round_id=_uuid_or_404(round_id),
        guessing_participant_id=_participant_uuid(body.guessing_participant_id),
        guessed_participant_id=_participant_uuid(body.guessed_participant_id),
    )


@router.post("/experiences/{experience_id}/rounds/{round_id}/reveal")
def reveal_round(
    experience_id: str,
    round_id: str,
    db: Session = Depends(get_db),
):
    exp = _get_experience(db, experience_id)
    return wkw.reveal_round(db, experience=exp, round_id=_uuid_or_404(round_id))


@router.post("/experiences/{experience_id}/rounds/{round_id}/advance")
def advance_round(
    experience_id: str,
    round_id: str,
    db: Session = Depends(get_db),
):
    exp = _get_experience(db, experience_id)
    return wkw.advance_round(db, experience=exp, round_id=_uuid_or_404(round_id))


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
        _participant_uuid(body.host_participant_id),
        _participant_uuid(body.main_person_participant_id),
    )
    return {"ok": True}


@router.post("/experiences/{experience_id}/start-setup")
def start_hwdyk_setup(
    experience_id: str,
    body: StartBody,
    db: Session = Depends(get_db),
):
    exp = _get_hwdyk_experience(db, experience_id)
    return hwdyk.start_setup(db, exp, _participant_uuid(body.participant_id))


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
        _participant_uuid(body.prompt_instance_id),
        _participant_uuid(body.participant_id),
        body.answer_text,
    )


@router.get("/experiences/{experience_id}/review-choices")
def get_review_choices(
    experience_id: str,
    participant_id: str = Query(...),
    db: Session = Depends(get_db),
):
    exp = _get_hwdyk_experience(db, experience_id)
    return {
        "game_state": exp.game_state,
        "rounds": hwdyk.get_review_data(db, exp.id, _participant_uuid(participant_id)),
    }


@router.post("/experiences/{experience_id}/choices/{choice_id}/edit")
def edit_choice(
    experience_id: str,
    choice_id: str,
    body: EditChoiceBody,
    db: Session = Depends(get_db),
):
    exp = _get_hwdyk_experience(db, experience_id)
    result = hwdyk.edit_choice(
        db,
        exp,
        _uuid_or_404(choice_id),
        _participant_uuid(body.participant_id),
        body.new_text,
        expected_revision=body.expected_revision,
    )
    return {"ok": True, **result}


@router.post("/experiences/{experience_id}/choices/{choice_id}/regenerate")
def regenerate_choice(
    experience_id: str,
    choice_id: str,
    body: RegenerateBody,
    db: Session = Depends(get_db),
):
    exp = _get_hwdyk_experience(db, experience_id)
    return hwdyk.regenerate_choice(
        db,
        exp,
        _uuid_or_404(choice_id),
        _participant_uuid(body.participant_id),
        expected_revision=body.expected_revision,
    )


@router.post("/experiences/{experience_id}/confirm-choices")
def confirm_choices(
    experience_id: str,
    body: ConfirmChoicesBody,
    db: Session = Depends(get_db),
):
    exp = _get_hwdyk_experience(db, experience_id)
    hwdyk.confirm_choices(
        db, exp, _participant_uuid(body.participant_id), expected_revisions=body.revisions
    )
    return {"ok": True}


@router.get("/experiences/{experience_id}/fake-answer-questions")
def get_fake_answer_questions(
    experience_id: str,
    participant_id: str = Query(...),
    db: Session = Depends(get_db),
):
    return {
        "questions": hwdyk.get_fake_answer_questions(
            db, _uuid_or_404(experience_id, "Experience not found"), _participant_uuid(participant_id)
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
        _participant_uuid(body.round_id),
        _participant_uuid(body.participant_id),
        body.fake_text,
    )


@router.get("/experiences/{experience_id}/fake-answer-progress")
def get_fake_answer_progress(experience_id: str, db: Session = Depends(get_db)):
    return hwdyk.get_fake_answer_progress(db, _uuid_or_404(experience_id, "Experience not found"))


@router.post("/experiences/{experience_id}/lock-party-mode")
def lock_party_mode(
    experience_id: str,
    body: StartBody,
    db: Session = Depends(get_db),
):
    exp = _get_hwdyk_experience(db, experience_id)
    hwdyk.lock_party_mode(db, exp, _participant_uuid(body.participant_id))
    return {"ok": True}


@router.post("/experiences/{experience_id}/start-live")
def start_live_game(
    experience_id: str,
    body: StartBody,
    db: Session = Depends(get_db),
):
    exp = _get_hwdyk_experience(db, experience_id)
    hwdyk.start_live_game(db, exp, _participant_uuid(body.participant_id))
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
        _uuid_or_404(round_id),
        _participant_uuid(body.participant_id),
        _participant_uuid(body.choice_id),
    )


@router.post("/experiences/{experience_id}/rounds/{round_id}/hwdyk-reveal")
def reveal_hwdyk_round(
    experience_id: str,
    round_id: str,
    db: Session = Depends(get_db),
):
    exp = _get_hwdyk_experience(db, experience_id)
    hwdyk.reveal_round(db, exp, _uuid_or_404(round_id))
    return {"ok": True}


@router.post("/experiences/{experience_id}/rounds/{round_id}/hwdyk-advance")
def advance_hwdyk_round(
    experience_id: str,
    round_id: str,
    db: Session = Depends(get_db),
):
    exp = _get_hwdyk_experience(db, experience_id)
    return hwdyk.advance_round(db, exp, _uuid_or_404(round_id))


@router.get("/experiences/{experience_id}/hwdyk/leaderboard")
def get_hwdyk_leaderboard(experience_id: str, db: Session = Depends(get_db)):
    exp = _get_hwdyk_experience(db, experience_id)
    # Check if a replay (child) experience exists
    child = (
        db.query(ExperienceInstance)
        .filter(ExperienceInstance.parent_experience_instance_id == exp.id)
        .first()
    )
    return {
        "leaderboard": hwdyk.compute_hwdyk_scores(db, exp.id),
        "next_experience_id": str(child.id) if child else None,
    }


@router.post("/experiences/{experience_id}/hwdyk/replay")
def replay_hwdyk_game(experience_id: str, db: Session = Depends(get_db)):
    exp = _get_hwdyk_experience(db, experience_id)
    return hwdyk.replay_game(db, exp)
