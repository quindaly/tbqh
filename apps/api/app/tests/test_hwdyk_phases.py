"""How Well Do You Know: timed preparation phases (server-authoritative clock)."""

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from fastapi import HTTPException

from app.db.models.game_choice import GameChoice
from app.db.models.game_round import GameRound
from app.db.models.prompt import PromptInstance
from app.services.games import how_well_do_you_know as hwdyk
from app.services.games import hwdyk_phases as phases
from app.tests.hwdyk_testkit import (
    GEN_LLM,
    answer,
    fake_llm,
    generate,
    make_game,
    new_game,
    wrong_choices,
)

GRACE = timedelta(seconds=phases.PHASE_GRACE_SECONDS)


def err(exc: HTTPException):
    d = exc.detail
    return exc.status_code, (d.get("code") if isinstance(d, dict) else d)


def after_deadline(exp, extra=0.0):
    return exp.phase_deadline_at + GRACE + timedelta(seconds=extra)


def rounds(db, exp):
    return (
        db.query(GameRound)
        .filter(GameRound.experience_instance_id == exp.id)
        .order_by(GameRound.round_number)
        .all()
    )


# ---------- the answering clock ----------


def test_setup_starts_a_60_second_answering_clock(db):
    exp, host, _ = new_game(db)
    assert exp.game_state == "main_person_answering"
    info = phases.phase_info(exp)
    assert info["name"] == "main_person_answering"
    assert info["duration_seconds"] == 60
    assert 58 <= info["seconds_remaining"] <= 60


def test_clock_length_comes_from_config(db):
    created = hwdyk.create_game(db, None, "Quin", num_questions=2)
    exp = db.get(hwdyk.ExperienceInstance, uuid.UUID(created["experience_instance_id"]))
    exp.game_config = {**exp.game_config, "answer_seconds": 20}
    host = uuid.UUID(created["participant_id"])
    hwdyk.select_main_person(db, exp, host, host)
    hwdyk.start_setup(db, exp, host)
    assert phases.phase_info(exp)["duration_seconds"] == 20


def test_nothing_happens_before_the_deadline(db):
    exp, host, _ = new_game(db)
    assert phases.advance_if_expired(db, exp.id) is None
    # inside the grace window the phase is still open
    assert phases.advance_if_expired(db, exp.id, now=exp.phase_deadline_at + GRACE / 2) is None
    assert exp.game_state == "main_person_answering"


def test_answer_inside_grace_window_is_accepted(db):
    exp, host, _ = new_game(db)
    q = hwdyk.get_main_person_questions(db, exp.id)[0]
    # (no advance has run, as when a save arrives at 0:01 after the deadline)
    out = hwdyk.submit_main_person_answer(db, exp, uuid.UUID(q["id"]), host, "Pizza")
    assert out["ok"]


def test_timeout_with_no_answers_returns_to_a_recoverable_lobby(db):
    exp, host, _ = new_game(db)
    assert phases.advance_if_expired(db, exp.id, now=after_deadline(exp)) is None
    db.refresh(exp)
    assert exp.game_state == "lobby"
    assert exp.phase_deadline_at is None
    notice = hwdyk.get_lobby_payload(db, exp)["notice"]
    assert notice["code"] == "no_answers" and "Quin" in notice["message"]
    assert rounds(db, exp) == []
    assert db.query(PromptInstance).filter(
        PromptInstance.experience_instance_id == exp.id
    ).count() == 0
    # main person kept; host can simply start again, which clears the notice
    assert exp.main_person_participant_id == host
    hwdyk.start_setup(db, exp, host)
    assert exp.game_state == "main_person_answering"
    assert hwdyk.get_lobby_payload(db, exp)["notice"] is None
    assert len(hwdyk.get_main_person_questions(db, exp.id)) == 2


def test_timeout_with_some_answers_plays_with_those_default_mode(db):
    exp, host, _ = new_game(db, num_questions=4)
    answer(db, exp, host, count=2)
    assert phases.advance_if_expired(db, exp.id, now=after_deadline(exp)) == "generate"
    db.refresh(exp)
    assert exp.game_state == "ai_generating_choices"
    assert exp.max_rounds == 2
    assert [r.round_number for r in rounds(db, exp)] == [1, 2]
    assert generate(db, exp) is True
    db.refresh(exp)
    assert exp.game_state == "main_person_reviewing_choices"
    assert all(len(w) == 3 for w in wrong_choices(db, exp))


def test_timeout_with_some_answers_party_mode_goes_to_fake_answers(db):
    exp, host, _ = new_game(db, mode="party", num_questions=4)
    answer(db, exp, host, count=3)
    assert phases.advance_if_expired(db, exp.id, now=after_deadline(exp)) is None
    db.refresh(exp)
    assert exp.game_state == "players_submitting_fake_answers"
    assert exp.max_rounds == 3


def test_answering_all_questions_early_ends_the_phase(db):
    exp, host, _ = new_game(db)
    out = answer(db, exp, host)
    assert out["all_answered"] and out["needs_generation"]
    assert exp.game_state == "ai_generating_choices"
    assert exp.phase_deadline_at is None  # AI step is untimed


def test_late_answer_after_phase_ended_is_rejected(db):
    exp, host, _ = new_game(db, num_questions=3)
    answer(db, exp, host, count=1)
    phases.advance_if_expired(db, exp.id, now=after_deadline(exp))
    db.refresh(exp)
    q = hwdyk.get_main_person_questions(db, exp.id)[1]
    with pytest.raises(HTTPException) as e:
        hwdyk.submit_main_person_answer(db, exp, uuid.UUID(q["id"]), host, "Too late")
    assert err(e.value) == (409, "answering_closed")
    assert len(rounds(db, exp)) == 1


def test_resubmitting_an_answered_question_is_a_clean_409(db):
    exp, host, _ = new_game(db, num_questions=3)
    answer(db, exp, host, count=1)
    questions = hwdyk.get_main_person_questions(db, exp.id)
    assert [q["answered"] for q in questions] == [True, False, False]
    with pytest.raises(HTTPException) as e:
        hwdyk.submit_main_person_answer(db, exp, uuid.UUID(questions[0]["id"]), host, "Again")
    assert err(e.value) == (409, "already_answered")


def test_advancing_twice_is_harmless(db):
    exp, host, _ = new_game(db, num_questions=3)
    answer(db, exp, host, count=1)
    now = after_deadline(exp)
    assert phases.advance_if_expired(db, exp.id, now=now) == "generate"
    assert phases.advance_if_expired(db, exp.id, now=now) is None  # not due any more
    db.refresh(exp)
    assert exp.game_state == "ai_generating_choices"


# ---------- AI step and the editing clock ----------


def test_editing_clock_starts_only_after_ai_choices_are_ready(db):
    exp, host, _ = new_game(db)
    answer(db, exp, host)
    assert exp.game_state == "ai_generating_choices"
    assert phases.phase_info(exp) is None  # nothing ticking while the AI works

    def slow_ai(**kwargs):
        # Pretend generation took ages: the answering deadline is long past.
        exp.phase_started_at = datetime.now(timezone.utc) - timedelta(seconds=90)
        return fake_llm()

    before = datetime.now(timezone.utc)
    generate(db, exp, llm=slow_ai)
    db.refresh(exp)
    assert exp.game_state == "main_person_reviewing_choices"
    info = phases.phase_info(exp)
    assert info["duration_seconds"] == 60
    assert info["seconds_remaining"] > 55
    assert exp.phase_deadline_at >= before + timedelta(seconds=59)


def test_generation_is_idempotent(db):
    exp, host, _ = new_game(db)
    answer(db, exp, host)
    assert generate(db, exp) is True
    assert generate(db, exp) is False  # already moved on
    assert all(len(w) == 3 for w in wrong_choices(db, exp))


def test_stalled_generation_is_taken_over_without_duplicates(db):
    exp, host, _ = new_game(db)
    answer(db, exp, host)
    assert phases.advance_if_expired(db, exp.id) is None  # fresh: leave it alone
    stale = datetime.now(timezone.utc) + timedelta(seconds=phases.GENERATION_STALE_SECONDS + 1)
    assert phases.advance_if_expired(db, exp.id, now=stale) == "generate"
    assert generate(db, exp) is True
    assert generate(db, exp) is False
    assert all(len(w) == 3 for w in wrong_choices(db, exp))


def test_lobby_payload_reports_phase_and_progress(db):
    exp, host, _ = new_game(db, num_questions=4)
    answer(db, exp, host, count=1)
    lobby = hwdyk.get_lobby_payload(db, exp)
    assert lobby["game_state"] == "main_person_answering"
    assert lobby["progress"] == {"answered": 1, "total": 4}
    assert lobby["phase"]["duration_seconds"] == 60
    assert lobby["state_version"] == exp.state_version


def test_state_version_increases_with_each_transition(db):
    exp, host, _ = new_game(db)
    v0 = exp.state_version
    answer(db, exp, host)
    generate(db, exp)
    db.refresh(exp)
    assert exp.state_version >= v0 + 2


# ---------- the editing clock ----------


def reviewing_game(db):
    exp, host, others = make_game(db)
    assert exp.game_state == "main_person_reviewing_choices"
    return exp, host, others


def test_editing_timeout_keeps_saved_edits_and_original_ai_answers(db):
    exp, host, _ = reviewing_game(db)
    first, second = wrong_choices(db, exp)
    hwdyk.edit_choice(db, exp, first[0].id, host, "Grandma's lasagna")

    assert phases.advance_if_expired(db, exp.id, now=after_deadline(exp)) is None
    db.refresh(exp)
    assert exp.game_state == "ready_to_start"

    hwdyk.start_live_game(db, exp, host)
    state = hwdyk.get_round_state(db, exp)
    shown = {c["text"] for c in state["round"]["choices"]}
    assert "Grandma's lasagna" in shown
    # unedited AI answers in round 1 are still there, exactly as the AI wrote them
    for c in first[1:]:
        assert c.choice_text in shown
    assert all(c.display_order is not None for w in (first, second) for c in w)


def test_edit_after_editing_timeout_is_rejected(db):
    exp, host, _ = reviewing_game(db)
    target = wrong_choices(db, exp)[0][0]
    phases.advance_if_expired(db, exp.id, now=after_deadline(exp))
    db.refresh(exp)
    with pytest.raises(HTTPException) as e:
        hwdyk.edit_choice(db, exp, target.id, host, "Too late")
    assert err(e.value) == (409, "choices_locked")


def test_edit_inside_grace_window_is_saved(db):
    exp, host, _ = reviewing_game(db)
    target = wrong_choices(db, exp)[0][0]
    out = hwdyk.edit_choice(db, exp, target.id, host, "Just in time")
    assert out["text"] == "Just in time"


def test_unusable_choices_at_timeout_return_to_lobby_with_notice(db):
    exp, host, _ = reviewing_game(db)
    # Corrupt a round so it can't be played (only one wrong answer left)
    for victim in wrong_choices(db, exp)[0][:2]:
        db.delete(victim)
    db.flush()
    phases.advance_if_expired(db, exp.id, now=after_deadline(exp))
    db.refresh(exp)
    assert exp.game_state == "lobby"
    assert hwdyk.get_lobby_payload(db, exp)["notice"]["code"] == "invalid_choices"
    assert rounds(db, exp) == []


def test_confirm_before_deadline_ends_the_clock(db):
    exp, host, _ = reviewing_game(db)
    late = after_deadline(exp, 600)
    hwdyk.confirm_choices(db, exp, host)
    assert exp.game_state == "ready_to_start"
    assert exp.phase_deadline_at is None
    assert phases.phase_info(exp) is None
    assert phases.advance_if_expired(db, exp.id, now=late) is None


def test_party_mode_has_no_editing_phase(db):
    exp, host, _ = make_game(db, mode="party")
    assert exp.game_state == "players_submitting_fake_answers"
    assert phases.phase_info(exp) is None
