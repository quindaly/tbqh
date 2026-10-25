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


def after_all_questions(db, exp):
    """A moment when every remaining question's 20 seconds has passed."""
    left = len(phases.question_ids(db, exp)) - phases.answer_cursor(exp)
    return (
        exp.phase_deadline_at
        + timedelta(seconds=phases.answer_seconds(exp) * left)
        + GRACE
    )


def rounds(db, exp):
    return (
        db.query(GameRound)
        .filter(GameRound.experience_instance_id == exp.id)
        .order_by(GameRound.round_number)
        .all()
    )


# ---------- the answering clock ----------


def test_setup_starts_a_20_second_clock_for_the_first_question(db):
    exp, host, _ = new_game(db)
    assert exp.game_state == "main_person_answering"
    info = phases.phase_info(exp)
    assert info["name"] == "main_person_answering"
    assert info["duration_seconds"] == 20
    assert 18 <= info["seconds_remaining"] <= 20
    assert phases.answer_cursor(exp) == 0
    questions = hwdyk.get_main_person_questions(db, exp.id)
    assert [q["current"] for q in questions] == [True, False]


def test_each_answer_starts_a_fresh_20_seconds_for_the_next_question(db):
    exp, host, _ = new_game(db, num_questions=3)
    # Pretend the first question has only 5 seconds left.
    exp.phase_deadline_at = datetime.now(timezone.utc) + timedelta(seconds=5)
    exp.phase_started_at = exp.phase_deadline_at - timedelta(seconds=20)
    q1 = hwdyk.get_main_person_questions(db, exp.id)[0]
    out = hwdyk.submit_main_person_answer(db, exp, uuid.UUID(q1["id"]), host, "Pizza")
    assert not out["all_answered"] and out["current_index"] == 1
    assert out["phase"]["duration_seconds"] == 20
    assert out["phase"]["seconds_remaining"] > 18  # not the 5 that were left
    assert phases.answer_cursor(exp) == 1
    assert [q["current"] for q in hwdyk.get_main_person_questions(db, exp.id)] == [
        False,
        True,
        False,
    ]


def test_clock_length_comes_from_config(db):
    created = hwdyk.create_game(db, None, "Quin", num_questions=2)
    exp = db.get(hwdyk.ExperienceInstance, uuid.UUID(created["experience_instance_id"]))
    exp.game_config = {**exp.game_config, "answer_seconds": 15}
    host = uuid.UUID(created["participant_id"])
    hwdyk.join_game(db, created["join_code"], "Bea")
    hwdyk.select_main_person(db, exp, host, host)
    hwdyk.start_setup(db, exp, host)
    assert phases.phase_info(exp)["duration_seconds"] == 15


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


def test_an_unanswered_question_is_skipped_and_the_next_one_starts(db):
    exp, host, _ = new_game(db, num_questions=3)
    first_deadline = exp.phase_deadline_at
    moment = after_deadline(exp)
    assert phases.advance_if_expired(db, exp.id, now=moment) is None
    db.refresh(exp)
    assert exp.game_state == "main_person_answering"
    assert phases.answer_cursor(exp) == 1
    # The next question's 20 seconds start where the last one's ended.
    assert exp.phase_deadline_at == first_deadline + timedelta(seconds=20)
    questions = hwdyk.get_main_person_questions(db, exp.id)
    assert [(q["skipped"], q["current"]) for q in questions] == [
        (True, False),
        (False, True),
        (False, False),
    ]
    # Skipping again at the same moment changes nothing.
    assert phases.advance_if_expired(db, exp.id, now=moment) is None
    assert phases.answer_cursor(exp) == 1


def test_a_long_absence_skips_every_question_whose_time_passed(db):
    exp, host, _ = new_game(db, num_questions=4)
    start = exp.phase_deadline_at
    # Question deadlines fall at start, +20s, +40s and +60s. At +45s the first
    # three are over and the fourth is open with 15 seconds left.
    assert phases.advance_if_expired(
        db, exp.id, now=start + timedelta(seconds=45)
    ) is None
    db.refresh(exp)
    assert phases.answer_cursor(exp) == 3
    assert exp.phase_deadline_at == start + timedelta(seconds=60)
    assert phases.phase_info(exp, now=start + timedelta(seconds=45))[
        "seconds_remaining"
    ] == 15.0


def test_a_skipped_question_cannot_be_answered_afterwards(db):
    exp, host, _ = new_game(db, num_questions=3)
    skipped = hwdyk.get_main_person_questions(db, exp.id)[0]
    phases.advance_if_expired(db, exp.id, now=after_deadline(exp))
    db.refresh(exp)
    with pytest.raises(HTTPException) as e:
        hwdyk.submit_main_person_answer(db, exp, uuid.UUID(skipped["id"]), host, "Late")
    assert err(e.value) == (409, "question_skipped")
    assert rounds(db, exp) == []


def test_questions_cannot_be_answered_ahead_of_time(db):
    exp, host, _ = new_game(db, num_questions=3)
    second = hwdyk.get_main_person_questions(db, exp.id)[1]
    with pytest.raises(HTTPException) as e:
        hwdyk.submit_main_person_answer(db, exp, uuid.UUID(second["id"]), host, "Early")
    assert err(e.value) == (409, "wrong_question")


def test_skipping_the_last_question_ends_answering(db):
    exp, host, _ = new_game(db, num_questions=3)
    answer(db, exp, host, count=2)
    assert phases.answer_cursor(exp) == 2
    assert phases.advance_if_expired(db, exp.id, now=after_deadline(exp)) == "generate"
    db.refresh(exp)
    assert exp.game_state == "ai_generating_choices"
    assert exp.max_rounds == 2
    assert "answer_cursor" not in exp.game_config


def test_skipped_questions_are_not_played_and_rounds_are_renumbered(db):
    exp, host, _ = new_game(db, num_questions=4)
    qs = hwdyk.get_main_person_questions(db, exp.id)
    hwdyk.submit_main_person_answer(db, exp, uuid.UUID(qs[0]["id"]), host, "First")
    # Q2 is skipped...
    phases.advance_if_expired(db, exp.id, now=after_deadline(exp))
    db.refresh(exp)
    # ...Q3 is answered, Q4 skipped.
    hwdyk.submit_main_person_answer(db, exp, uuid.UUID(qs[2]["id"]), host, "Third")
    phases.advance_if_expired(db, exp.id, now=after_deadline(exp))
    db.refresh(exp)
    assert exp.game_state == "ai_generating_choices"
    played = rounds(db, exp)
    assert [r.round_number for r in played] == [1, 2]
    assert [r.source_prompt_instance_id for r in played] == [
        uuid.UUID(qs[0]["id"]),
        uuid.UUID(qs[2]["id"]),
    ]


def test_timeout_with_no_answers_returns_to_a_recoverable_lobby(db):
    exp, host, _ = new_game(db)
    assert phases.advance_if_expired(db, exp.id, now=after_all_questions(db, exp)) is None
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
    assert (
        phases.advance_if_expired(db, exp.id, now=after_all_questions(db, exp))
        == "generate"
    )
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
    assert phases.advance_if_expired(db, exp.id, now=after_all_questions(db, exp)) is None
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
    phases.advance_if_expired(db, exp.id, now=after_all_questions(db, exp))
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
    now = after_all_questions(db, exp)
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
    assert lobby["progress"] == {"answered": 1, "total": 4, "current_index": 1}
    assert lobby["phase"]["duration_seconds"] == 20
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


# ---------- editing time depends on how many questions are played ----------


@pytest.mark.parametrize(
    "questions, seconds",
    [(1, 60), (3, 60), (5, 60), (6, 90), (8, 90), (10, 90)],
)
def test_editing_time_is_60_seconds_up_to_5_questions_and_90_for_6_to_10(
    db, questions, seconds
):
    exp, host, _ = make_game(db, num_questions=questions)
    assert exp.game_state == "main_person_reviewing_choices"
    assert phases.phase_info(exp)["duration_seconds"] == seconds


def test_editing_time_follows_the_questions_actually_played(db):
    """Time ran out after 5 of 8 questions were answered: 5 are played, so 60s."""
    exp, host, _ = new_game(db, num_questions=8)
    answer(db, exp, host, count=5)
    phases.advance_if_expired(db, exp.id, now=after_all_questions(db, exp))
    db.refresh(exp)
    generate(db, exp)
    db.refresh(exp)
    assert exp.max_rounds == 5
    assert phases.phase_info(exp)["duration_seconds"] == 60


def test_editing_time_can_still_be_overridden_by_config(db):
    exp, host, _ = new_game(db, num_questions=3)
    exp.game_config = {**exp.game_config, "edit_seconds": 45}
    answer(db, exp, host)
    generate(db, exp)
    db.refresh(exp)
    assert phases.phase_info(exp)["duration_seconds"] == 45
