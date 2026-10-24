"""How Well Do You Know: persistence and safety of the answer-review phase."""

import uuid
from unittest.mock import patch

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.db.models.game_choice import GameChoice
from app.db.models.game_round import GameRound
from app.services.games import how_well_do_you_know as hwdyk

LLM = "app.services.games.how_well_do_you_know.call_llm_json"


@pytest.fixture(scope="module")
def engine():
    from app.core.config import settings

    return create_engine(settings.DATABASE_URL, echo=False)


@pytest.fixture(scope="module")
def tables(engine):
    Base.metadata.create_all(engine)
    yield


@pytest.fixture()
def db(engine, tables):
    conn = engine.connect()
    txn = conn.begin()
    session = sessionmaker(bind=conn, expire_on_commit=False)()
    yield session
    session.close()
    txn.rollback()
    conn.close()


def _fake_llm(**kwargs):
    return {"wrong_answers": ["Tacos", "Sushi", "Burgers"]}


def make_game(db, mode="default", num_questions=2, players=("Bea", "Cal")):
    """Create a HWDYK game with the host as main person, up to the review step
    (default mode) or fake-answer collection (party mode)."""
    created = hwdyk.create_game(db, None, "Quin", mode=mode, num_questions=num_questions)
    exp = db.get(hwdyk.ExperienceInstance, uuid.UUID(created["experience_instance_id"]))
    host_id = uuid.UUID(created["participant_id"])
    joined = [
        uuid.UUID(
            hwdyk.join_game(db, created["join_code"], name)["participant_id"]
        )
        for name in players
    ]
    hwdyk.select_main_person(db, exp, host_id, host_id)
    hwdyk.start_setup(db, exp, host_id)
    prompts = hwdyk.get_main_person_questions(db, exp.id)
    with patch(LLM, side_effect=_fake_llm):
        for i, q in enumerate(prompts):
            hwdyk.submit_main_person_answer(
                db, exp, uuid.UUID(q["id"]), host_id, f"Pizza {i}"
            )
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


def http_error(exc: HTTPException):
    d = exc.detail
    return exc.status_code, (d.get("code") if isinstance(d, dict) else d)


# ---------- generation ----------


def test_default_mode_reaches_review_with_unique_choices(db):
    exp, host, _ = make_game(db)
    assert exp.game_state == "main_person_reviewing_choices"
    for choices in wrong_choices(db, exp):
        assert len(choices) == 3


def test_duplicate_ai_answers_are_deduped_and_topped_up(db):
    created = hwdyk.create_game(db, None, "Quin", num_questions=1)
    exp = db.get(hwdyk.ExperienceInstance, uuid.UUID(created["experience_instance_id"]))
    host = uuid.UUID(created["participant_id"])
    hwdyk.join_game(db, created["join_code"], "Bea")
    hwdyk.select_main_person(db, exp, host, host)
    hwdyk.start_setup(db, exp, host)
    q = hwdyk.get_main_person_questions(db, exp.id)[0]
    # AI repeats itself and echoes the correct answer
    bad = {"wrong_answers": ["Tacos", "tacos ", "Pizza", "Pizza"]}
    with patch(LLM, return_value=bad):
        hwdyk.submit_main_person_answer(db, exp, uuid.UUID(q["id"]), host, "Pizza")
    texts = [c.choice_text for c in wrong_choices(db, exp)[0]]
    assert len(texts) == 3
    assert len({t.casefold() for t in texts}) == 3
    assert "pizza" not in {t.casefold() for t in texts}


def test_ai_failure_still_yields_playable_review(db):
    created = hwdyk.create_game(db, None, "Quin", num_questions=1)
    exp = db.get(hwdyk.ExperienceInstance, uuid.UUID(created["experience_instance_id"]))
    host = uuid.UUID(created["participant_id"])
    hwdyk.join_game(db, created["join_code"], "Bea")
    hwdyk.select_main_person(db, exp, host, host)
    hwdyk.start_setup(db, exp, host)
    q = hwdyk.get_main_person_questions(db, exp.id)[0]
    with patch(LLM, side_effect=RuntimeError("down")):
        hwdyk.submit_main_person_answer(db, exp, uuid.UUID(q["id"]), host, "Pizza")
    assert exp.game_state == "main_person_reviewing_choices"
    assert len(wrong_choices(db, exp)[0]) == 3


# ---------- editing ----------


def test_edit_persists_and_is_used_in_gameplay(db):
    exp, host, _ = make_game(db)
    target = wrong_choices(db, exp)[0][0]
    original = target.choice_text

    out = hwdyk.edit_choice(db, exp, target.id, host, "  Grandma's   lasagna ")
    assert out["text"] == "Grandma's lasagna"
    assert out["revision"] == 1

    db.expire_all()
    saved = db.get(GameChoice, target.id)
    assert saved.choice_text == "Grandma's lasagna"
    assert saved.source_type == "main_person_edited"
    assert saved.original_ai_text == original

    hwdyk.confirm_choices(db, exp, host)
    hwdyk.start_live_game(db, exp, host)
    state = hwdyk.get_round_state(db, exp)
    shown = [c["text"] for c in state["round"]["choices"]]
    assert "Grandma's lasagna" in shown
    assert original not in shown


def test_edit_review_payload_includes_revision(db):
    exp, host, _ = make_game(db)
    target = wrong_choices(db, exp)[0][0]
    hwdyk.edit_choice(db, exp, target.id, host, "Edited")
    rounds = hwdyk.get_review_data(db, exp.id, host)
    mine = [c for c in rounds[0]["choices"] if c["id"] == str(target.id)][0]
    assert mine["text"] == "Edited" and mine["revision"] == 1


@pytest.mark.parametrize("text", ["Sushi", " sushi ", "SUSHI", "Pizza 0", "pizza  0"])
def test_edit_to_duplicate_is_a_409_not_a_crash(db, text):
    exp, host, _ = make_game(db)
    first = wrong_choices(db, exp)[0]
    # make sure 'Sushi' is a sibling, edit the first wrong answer
    assert "Sushi" in [c.choice_text for c in first]
    target = [c for c in first if c.choice_text != "Sushi"][0]
    with pytest.raises(HTTPException) as e:
        hwdyk.edit_choice(db, exp, target.id, host, text)
    assert http_error(e.value) == (409, "duplicate_choice")


@pytest.mark.parametrize("text", ["", "   ", "\n\t"])
def test_edit_blank_rejected(db, text):
    exp, host, _ = make_game(db)
    target = wrong_choices(db, exp)[0][0]
    with pytest.raises(HTTPException) as e:
        hwdyk.edit_choice(db, exp, target.id, host, text)
    assert e.value.status_code == 400


def test_edit_too_long_rejected(db):
    exp, host, _ = make_game(db)
    target = wrong_choices(db, exp)[0][0]
    with pytest.raises(HTTPException) as e:
        hwdyk.edit_choice(db, exp, target.id, host, "x" * (hwdyk.MAX_CHOICE_LEN + 1))
    assert e.value.status_code == 400


def test_stale_edit_is_rejected_and_newer_text_kept(db):
    exp, host, _ = make_game(db)
    target = wrong_choices(db, exp)[0][0]
    hwdyk.edit_choice(db, exp, target.id, host, "First", expected_revision=0)
    # A delayed duplicate of the older save arrives (still thinks revision is 0)
    with pytest.raises(HTTPException) as e:
        hwdyk.edit_choice(db, exp, target.id, host, "Older", expected_revision=0)
    assert http_error(e.value) == (409, "stale_revision")
    db.expire_all()
    assert db.get(GameChoice, target.id).choice_text == "First"
    # In-order saves are fine
    hwdyk.edit_choice(db, exp, target.id, host, "Second", expected_revision=1)
    assert db.get(GameChoice, target.id).choice_text == "Second"


def test_repeating_same_save_is_idempotent(db):
    exp, host, _ = make_game(db)
    target = wrong_choices(db, exp)[0][0]
    a = hwdyk.edit_choice(db, exp, target.id, host, "Same")
    b = hwdyk.edit_choice(db, exp, target.id, host, "Same")
    assert a["revision"] == b["revision"] == 1


def test_only_main_person_can_edit(db):
    exp, host, others = make_game(db)
    target = wrong_choices(db, exp)[0][0]
    with pytest.raises(HTTPException) as e:
        hwdyk.edit_choice(db, exp, target.id, others[0], "Nope")
    assert e.value.status_code == 403


def test_cannot_edit_the_correct_answer(db):
    exp, host, _ = make_game(db)
    correct = (
        db.query(GameChoice).filter(GameChoice.is_correct.is_(True)).first()
    )
    with pytest.raises(HTTPException) as e:
        hwdyk.edit_choice(db, exp, correct.id, host, "Hack")
    assert e.value.status_code == 400


def test_cannot_edit_a_choice_from_another_game(db):
    exp, host, _ = make_game(db)
    other_exp, other_host, _ = make_game(db)
    foreign = wrong_choices(db, other_exp)[0][0]
    with pytest.raises(HTTPException) as e:
        hwdyk.edit_choice(db, exp, foreign.id, host, "Sneaky")
    assert e.value.status_code == 404
    db.expire_all()
    assert db.get(GameChoice, foreign.id).choice_text != "Sneaky"


def test_cannot_edit_after_confirm(db):
    exp, host, _ = make_game(db)
    target = wrong_choices(db, exp)[0][0]
    hwdyk.confirm_choices(db, exp, host)
    with pytest.raises(HTTPException) as e:
        hwdyk.edit_choice(db, exp, target.id, host, "Too late")
    assert http_error(e.value) == (409, "choices_locked")


# ---------- confirm ----------


def test_confirm_requires_revisions_to_match(db):
    exp, host, _ = make_game(db)
    target = wrong_choices(db, exp)[0][0]
    hwdyk.edit_choice(db, exp, target.id, host, "Edited")  # revision -> 1
    with pytest.raises(HTTPException) as e:
        hwdyk.confirm_choices(db, exp, host, expected_revisions={str(target.id): 0})
    assert http_error(e.value) == (409, "stale_revision")
    assert exp.game_state == "main_person_reviewing_choices"
    hwdyk.confirm_choices(db, exp, host, expected_revisions={str(target.id): 1})
    assert exp.game_state == "ready_to_start"


def test_confirm_is_idempotent(db):
    exp, host, _ = make_game(db)
    hwdyk.confirm_choices(db, exp, host)
    hwdyk.confirm_choices(db, exp, host)
    assert exp.game_state == "ready_to_start"


def test_confirm_assigns_a_display_order_to_every_choice(db):
    exp, host, _ = make_game(db)
    hwdyk.confirm_choices(db, exp, host)
    for r in db.query(GameRound).filter(GameRound.experience_instance_id == exp.id):
        orders = [
            c.display_order
            for c in db.query(GameChoice).filter(GameChoice.game_round_id == r.id)
        ]
        assert sorted(orders) == list(range(len(orders)))


def test_only_main_person_can_confirm(db):
    exp, host, others = make_game(db)
    with pytest.raises(HTTPException) as e:
        hwdyk.confirm_choices(db, exp, others[0])
    assert e.value.status_code == 403


# ---------- regenerate ----------


def test_regenerate_bumps_revision_and_counts(db):
    exp, host, _ = make_game(db)
    target = wrong_choices(db, exp)[0][0]
    with patch(LLM, return_value={"wrong_answers": ["Ramen"]}):
        out = hwdyk.regenerate_choice(db, exp, target.id, host)
    assert out["new_text"] == "Ramen"
    assert out["revision"] == 1
    assert out["regenerations_remaining"] == 2
    rounds = hwdyk.get_review_data(db, exp.id, host)
    mine = [c for c in rounds[0]["choices"] if c["id"] == str(target.id)][0]
    assert mine["text"] == "Ramen" and mine["regenerations_used"] == 1


def test_regenerate_limit(db):
    exp, host, _ = make_game(db)
    target = wrong_choices(db, exp)[0][0]
    for i in range(hwdyk.MAX_REGENERATIONS):
        with patch(LLM, return_value={"wrong_answers": [f"Fresh {i}"]}):
            hwdyk.regenerate_choice(db, exp, target.id, host)
    with patch(LLM, return_value={"wrong_answers": ["One more"]}):
        with pytest.raises(HTTPException) as e:
            hwdyk.regenerate_choice(db, exp, target.id, host)
    assert e.value.status_code == 429


def test_regenerate_does_not_clobber_an_edit_made_meanwhile(db):
    exp, host, _ = make_game(db)
    target = wrong_choices(db, exp)[0][0]

    def llm_while_user_edits(**kwargs):
        hwdyk.edit_choice(db, exp, target.id, host, "My own idea")
        return {"wrong_answers": ["AI idea"]}

    with patch(LLM, side_effect=llm_while_user_edits):
        with pytest.raises(HTTPException) as e:
            hwdyk.regenerate_choice(db, exp, target.id, host)
    assert http_error(e.value) == (409, "stale_revision")
    db.expire_all()
    assert db.get(GameChoice, target.id).choice_text == "My own idea"


def test_regenerate_rejects_suggestion_matching_a_sibling(db):
    exp, host, _ = make_game(db)
    target = wrong_choices(db, exp)[0][0]
    with patch(LLM, return_value={"wrong_answers": ["Pizza 0", "SUSHI", "Tacos", "Burgers"]}):
        with pytest.raises(HTTPException) as e:
            hwdyk.regenerate_choice(db, exp, target.id, host)
    assert e.value.status_code == 502


# ---------- party mode fake answers ----------


def test_party_fake_answers_reject_duplicates_and_correct_answer(db):
    exp, host, (bea, cal) = make_game(db, mode="party")
    assert exp.game_state == "players_submitting_fake_answers"
    r1 = (
        db.query(GameRound)
        .filter(GameRound.experience_instance_id == exp.id, GameRound.round_number == 1)
        .one()
    )
    hwdyk.submit_fake_answer(db, exp, r1.id, bea, "Salad")
    for who, text in [(cal, " salad "), (cal, "PIZZA 0")]:
        with pytest.raises(HTTPException) as e:
            hwdyk.submit_fake_answer(db, exp, r1.id, who, text)
        assert e.value.status_code in (400, 409)
    with pytest.raises(HTTPException) as e:
        hwdyk.submit_fake_answer(db, exp, r1.id, bea, "Another")
    assert e.value.status_code == 409
    hwdyk.submit_fake_answer(db, exp, r1.id, cal, "Soup")


def test_party_lock_is_idempotent_and_dedupes_fallbacks(db):
    exp, host, (bea, cal) = make_game(db, mode="party")
    r1 = (
        db.query(GameRound)
        .filter(GameRound.experience_instance_id == exp.id, GameRound.round_number == 1)
        .one()
    )
    hwdyk.submit_fake_answer(db, exp, r1.id, bea, "Tacos")
    with patch(LLM, return_value={"wrong_answers": ["tacos", "Soup", "Stew"]}):
        hwdyk.lock_party_mode(db, exp, host)
        hwdyk.lock_party_mode(db, exp, host)  # double click
    assert exp.game_state == "ready_to_start"


def test_host_of_another_game_cannot_lock_this_one(db):
    exp, host, _ = make_game(db, mode="party")
    other_exp, other_host, _ = make_game(db, mode="party")
    with pytest.raises(HTTPException) as e:
        hwdyk.lock_party_mode(db, exp, other_host)
    assert e.value.status_code == 403
