"""Helpers for building How Well Do You Know games in tests."""

import uuid
from unittest.mock import patch

from app.db.models.experience import ExperienceInstance
from app.db.models.game_choice import GameChoice
from app.db.models.game_round import GameRound
from app.services.games import how_well_do_you_know as hwdyk
from app.services.games import hwdyk_phases as phases

LLM = "app.services.games.how_well_do_you_know.call_llm_json"  # regenerate
GEN_LLM = "app.services.games.hwdyk_phases.call_llm_json"  # initial generation


def fake_llm(**kwargs):
    return {"wrong_answers": ["Tacos", "Sushi", "Burgers"]}


def new_game(db, mode="default", num_questions=2, players=("Bea", "Cal")):
    """A lobby with the host as main person and setup started (answering phase)."""
    created = hwdyk.create_game(db, None, "Quin", mode=mode, num_questions=num_questions)
    exp = db.get(ExperienceInstance, uuid.UUID(created["experience_instance_id"]))
    host_id = uuid.UUID(created["participant_id"])
    joined = [
        uuid.UUID(hwdyk.join_game(db, created["join_code"], name)["participant_id"])
        for name in players
    ]
    hwdyk.select_main_person(db, exp, host_id, host_id)
    hwdyk.start_setup(db, exp, host_id)
    return exp, host_id, joined


def answer(db, exp, host_id, count=None):
    """Submit answers for the first ``count`` questions (all if None)."""
    prompts = hwdyk.get_main_person_questions(db, exp.id)
    last = None
    for i, q in enumerate(prompts[:count]):
        last = hwdyk.submit_main_person_answer(
            db, exp, uuid.UUID(q["id"]), host_id, f"Pizza {i}"
        )
    return last


def generate(db, exp, llm=fake_llm):
    with patch(GEN_LLM, side_effect=llm):
        return phases.run_generation(db, exp.id)


def make_game(db, mode="default", num_questions=2, players=("Bea", "Cal")):
    """Play setup through to review (default) or fake-answer collection (party)."""
    exp, host_id, joined = new_game(db, mode, num_questions, players)
    answer(db, exp, host_id)
    if exp.game_state == phases.GENERATING:
        # In production this runs as a background task after the last answer.
        generate(db, exp)
    db.refresh(exp)
    return exp, host_id, joined


def wrong_choices(db, exp):
    rounds = (
        db.query(GameRound)
        .filter(GameRound.experience_instance_id == exp.id)
        .order_by(GameRound.round_number)
        .all()
    )
    return [
        db.query(GameChoice)
        .filter(GameChoice.game_round_id == r.id, GameChoice.is_correct.is_(False))
        .order_by(GameChoice.created_at, GameChoice.id)
        .all()
        for r in rounds
    ]


def go_live(db, mode="default", num_questions=2, players=("Bea", "Cal")):
    """Play a game through prep and start round 1. Returns (exp, host, players, round1)."""
    exp, host, joined = make_game(db, mode, num_questions, players)
    if mode == "party":
        r1 = (
            db.query(GameRound)
            .filter(GameRound.experience_instance_id == exp.id)
            .order_by(GameRound.round_number)
            .all()
        )
        for r in r1:
            for who, text in zip(joined, ("Salad", "Soup", "Stew", "Curry")):
                hwdyk.submit_fake_answer(db, exp, r.id, who, f"{text} {r.round_number}")
        hwdyk.lock_party_mode(db, exp, host)
    else:
        hwdyk.confirm_choices(db, exp, host)
    hwdyk.start_live_game(db, exp, host)
    db.refresh(exp)
    first = (
        db.query(GameRound)
        .filter(GameRound.experience_instance_id == exp.id, GameRound.round_number == 1)
        .one()
    )
    return exp, host, joined, first


def choice_ids(db, game_round):
    """(correct_id, [wrong ids]) of the cards on screen."""
    cards = (
        db.query(GameChoice)
        .filter(GameChoice.game_round_id == game_round.id, GameChoice.display_order.isnot(None))
        .all()
    )
    return (
        [c.id for c in cards if c.is_correct][0],
        [c.id for c in cards if not c.is_correct],
    )
