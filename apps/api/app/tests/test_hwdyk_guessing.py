"""How Well Do You Know: the 30-second guessing round and its single, safe reveal."""

from datetime import timedelta

import pytest
from fastapi import HTTPException

from app.db.models.game_mc_guess import GameMCGuess
from app.db.models.game_round import GameRound
from app.db.models.participant import Participant
from app.db.models.session import SessionParticipant
from app.services.games import how_well_do_you_know as hwdyk
from app.tests.hwdyk_testkit import choice_ids, go_live


def err(exc: HTTPException):
    d = exc.detail
    return exc.status_code, (d.get("code") if isinstance(d, dict) else d)


GRACE = timedelta(seconds=hwdyk.GUESS_GRACE_SECONDS)


def n_guesses(db, game_round):
    return db.query(GameMCGuess).filter(GameMCGuess.game_round_id == game_round.id).count()


# ---------- the round clock ----------


def test_round_starts_with_a_30_second_server_deadline_and_frozen_roster(db):
    exp, host, (bea, cal), r1 = go_live(db)
    assert exp.game_state == "round_active"
    assert r1.timer_duration == 30
    assert r1.guess_deadline_at == r1.started_at + timedelta(seconds=30)
    assert sorted(r1.eligible_participant_ids) == sorted([str(bea), str(cal)])
    assert str(host) not in r1.eligible_participant_ids

    rnd = hwdyk.get_round_state(db, exp)["round"]
    assert rnd["duration_seconds"] == 30
    assert 28 <= rnd["seconds_remaining"] <= 30
    assert rnd["total_guessers"] == 2
    assert rnd["guessed_participant_ids"] == []


def test_starting_twice_does_not_restart_the_round(db):
    exp, host, _, r1 = go_live(db)
    deadline = r1.guess_deadline_at
    hwdyk.start_live_game(db, exp, host)
    db.refresh(r1)
    assert r1.guess_deadline_at == deadline


def test_polling_state_never_changes_anything(db):
    exp, host, _, r1 = go_live(db)
    r1.guess_deadline_at = r1.guess_deadline_at - timedelta(seconds=600)
    db.flush()
    before = exp.state_version
    rnd = hwdyk.get_round_state(db, exp)["round"]
    assert rnd["seconds_remaining"] == 0
    assert exp.game_state == "round_active" and exp.state_version == before


# ---------- guessing ----------


def test_guess_is_recorded_and_visible_in_progress(db):
    exp, host, (bea, cal), r1 = go_live(db)
    correct, wrong = choice_ids(db, r1)
    out = hwdyk.submit_mc_guess(db, exp, r1.id, bea, correct)
    assert out == {"ok": True, "is_correct": True, "all_guessed": False}
    rnd = hwdyk.get_round_state(db, exp)["round"]
    assert rnd["guessed_participant_ids"] == [str(bea)]
    assert rnd["guesses_submitted"] == 1
    assert "is_correct" not in rnd["choices"][0]  # answer stays hidden


def test_everyone_guessing_ends_the_round_early_and_reveals_once(db):
    exp, host, (bea, cal), r1 = go_live(db)
    correct, wrong = choice_ids(db, r1)
    hwdyk.submit_mc_guess(db, exp, r1.id, bea, wrong[0])
    version = exp.state_version
    out = hwdyk.submit_mc_guess(db, exp, r1.id, cal, correct)
    assert out["all_guessed"] is True
    db.refresh(exp)
    db.refresh(r1)
    assert exp.game_state == "round_reveal"
    assert r1.status == "revealed" and r1.revealed_at is not None
    assert exp.state_version == version + 1
    rnd = hwdyk.get_round_state(db, exp)["round"]
    assert any(c["is_correct"] for c in rnd["choices"])


def test_repeating_the_same_guess_is_idempotent_a_different_one_conflicts(db):
    exp, host, (bea, cal), r1 = go_live(db)
    correct, wrong = choice_ids(db, r1)
    first = hwdyk.submit_mc_guess(db, exp, r1.id, bea, wrong[0])
    again = hwdyk.submit_mc_guess(db, exp, r1.id, bea, wrong[0])
    assert again["is_correct"] == first["is_correct"] is False
    with pytest.raises(HTTPException) as e:
        hwdyk.submit_mc_guess(db, exp, r1.id, bea, correct)
    assert err(e.value) == (409, "already_guessed")
    assert n_guesses(db, r1) == 1


def test_main_person_and_outsiders_cannot_guess(db):
    exp, host, (bea, cal), r1 = go_live(db)
    other_exp, other_host, (other_player, _), _ = go_live(db)
    correct, _ = choice_ids(db, r1)
    with pytest.raises(HTTPException) as e:
        hwdyk.submit_mc_guess(db, exp, r1.id, host, correct)
    assert e.value.status_code == 403
    with pytest.raises(HTTPException) as e:
        hwdyk.submit_mc_guess(db, exp, r1.id, other_player, correct)
    assert e.value.status_code == 403
    assert n_guesses(db, r1) == 0


def test_card_from_another_round_is_rejected(db):
    exp, host, (bea, cal), r1 = go_live(db)
    r2 = db.query(GameRound).filter_by(experience_instance_id=exp.id, round_number=2).one()
    other_card, _ = choice_ids(db, r2)
    with pytest.raises(HTTPException) as e:
        hwdyk.submit_mc_guess(db, exp, r1.id, bea, other_card)
    assert e.value.status_code == 400


# ---------- the deadline ----------


def test_guess_just_inside_the_grace_window_counts(db):
    exp, host, (bea, cal), r1 = go_live(db)
    correct, _ = choice_ids(db, r1)
    r1.guess_deadline_at = hwdyk._now() - GRACE / 2
    db.flush()
    assert hwdyk.submit_mc_guess(db, exp, r1.id, bea, correct)["ok"]


def test_late_guess_is_rejected_and_closes_the_round(db):
    exp, host, (bea, cal), r1 = go_live(db)
    correct, _ = choice_ids(db, r1)
    hwdyk.submit_mc_guess(db, exp, r1.id, bea, correct)
    r1.guess_deadline_at = hwdyk._now() - timedelta(seconds=5)
    db.flush()
    with pytest.raises(HTTPException) as e:
        hwdyk.submit_mc_guess(db, exp, r1.id, cal, correct)
    assert err(e.value) == (409, "round_closed")
    db.refresh(exp)
    db.refresh(r1)
    assert r1.status == "revealed" and exp.game_state == "round_reveal"
    assert n_guesses(db, r1) == 1  # only Bea's, on time


def test_guess_after_the_round_was_revealed_is_rejected(db):
    exp, host, (bea, cal), r1 = go_live(db)
    correct, wrong = choice_ids(db, r1)
    hwdyk.submit_mc_guess(db, exp, r1.id, bea, correct)
    hwdyk.close_round_if_due(
        db, exp.id, now=r1.guess_deadline_at + GRACE + timedelta(seconds=1)
    )
    db.refresh(exp)
    assert exp.game_state == "round_reveal"
    with pytest.raises(HTTPException) as e:
        hwdyk.submit_mc_guess(db, exp, r1.id, cal, wrong[0])
    assert err(e.value) == (409, "round_closed")
    assert n_guesses(db, r1) == 1


def test_timeout_reveals_once_even_if_called_repeatedly(db):
    exp, host, (bea, cal), r1 = go_live(db)
    now = r1.guess_deadline_at
    assert hwdyk.close_round_if_due(db, exp.id, now=now) is False  # inside grace
    late = now + GRACE + timedelta(seconds=0.1)
    assert hwdyk.close_round_if_due(db, exp.id, now=late) is True
    version = exp.state_version
    assert hwdyk.close_round_if_due(db, exp.id, now=late) is False
    assert hwdyk.close_round_if_due(db, exp.id, now=late) is False
    db.refresh(exp)
    assert exp.game_state == "round_reveal" and exp.state_version == version


def test_timeout_with_partial_guesses_scores_only_those_who_guessed(db):
    exp, host, (bea, cal), r1 = go_live(db)
    correct, wrong = choice_ids(db, r1)
    hwdyk.submit_mc_guess(db, exp, r1.id, bea, correct)
    hwdyk.close_round_if_due(db, exp.id, now=r1.guess_deadline_at + GRACE + timedelta(seconds=1))
    scores = {s["participant_id"]: s["score"] for s in hwdyk.get_round_state(db, exp)["scores"]}
    assert scores[str(bea)] == 100 and scores[str(cal)] == 0


def test_advance_helper_ends_an_overdue_round(db):
    exp, host, _, r1 = go_live(db)
    r1.guess_deadline_at = hwdyk._now() - timedelta(seconds=60)
    db.flush()
    assert hwdyk.advance(db, exp.id) is None
    db.refresh(exp)
    assert exp.game_state == "round_reveal"


# ---------- manual reveal ----------


def test_manual_reveal_cannot_cut_guessing_short(db):
    exp, host, (bea, cal), r1 = go_live(db)
    with pytest.raises(HTTPException) as e:
        hwdyk.reveal_round(db, exp, r1.id)
    assert err(e.value) == (409, "round_in_progress")
    assert exp.game_state == "round_active"


def test_manual_reveal_after_time_up_is_idempotent(db):
    exp, host, (bea, cal), r1 = go_live(db)
    r1.guess_deadline_at = hwdyk._now() - timedelta(seconds=1)
    db.flush()
    assert hwdyk.reveal_round(db, exp, r1.id) == {"ok": True, "revealed": True}
    version = exp.state_version
    assert hwdyk.reveal_round(db, exp, r1.id) == {"ok": True, "revealed": False}
    assert exp.state_version == version


# ---------- scoring is derived, so a repeated reveal can't double-award ----------


def test_party_fool_points_are_not_doubled_by_repeated_reveals(db):
    exp, host, (bea, cal), r1 = go_live(db, mode="party")
    cards = {
        c.choice_text: c
        for c in db.query(hwdyk.GameChoice).filter(
            hwdyk.GameChoice.game_round_id == r1.id,
            hwdyk.GameChoice.display_order.isnot(None),
        )
    }
    bea_fake = [c for c in cards.values() if c.created_by_participant_id == bea][0]
    correct, _ = choice_ids(db, r1)
    hwdyk.submit_mc_guess(db, exp, r1.id, bea, correct)  # Bea right (+100)
    hwdyk.submit_mc_guess(db, exp, r1.id, cal, bea_fake.id)  # Cal fooled by Bea (+50 to Bea)
    for _ in range(3):
        hwdyk.reveal_round(db, exp, r1.id)
    scores = {s["participant_id"]: s for s in hwdyk.compute_hwdyk_scores(db, exp.id)}
    assert scores[str(bea)]["score"] == 150
    assert scores[str(bea)]["fool_count"] == 1
    assert scores[str(cal)]["score"] == 0


def test_fooling_points_do_not_require_the_author_to_have_guessed(db):
    exp, host, (bea, cal), r1 = go_live(db, mode="party")
    bea_fake = (
        db.query(hwdyk.GameChoice)
        .filter(
            hwdyk.GameChoice.game_round_id == r1.id,
            hwdyk.GameChoice.created_by_participant_id == bea,
        )
        .one()
    )
    hwdyk.submit_mc_guess(db, exp, r1.id, cal, bea_fake.id)
    hwdyk.close_round_if_due(db, exp.id, now=r1.guess_deadline_at + GRACE + timedelta(seconds=1))
    scores = {s["participant_id"]: s["score"] for s in hwdyk.compute_hwdyk_scores(db, exp.id)}
    assert scores[str(bea)] == 50  # Bea timed out but still fooled Cal


# ---------- advancing ----------


def test_advance_round_is_idempotent_and_gives_the_next_round_a_fresh_clock(db):
    exp, host, (bea, cal), r1 = go_live(db)
    correct, _ = choice_ids(db, r1)
    hwdyk.submit_mc_guess(db, exp, r1.id, bea, correct)
    hwdyk.submit_mc_guess(db, exp, r1.id, cal, correct)

    first = hwdyk.advance_round(db, exp, r1.id)
    assert first == {"ok": True, "is_last": False, "advanced": True}
    r2 = db.query(GameRound).filter_by(experience_instance_id=exp.id, round_number=2).one()
    deadline = r2.guess_deadline_at
    assert exp.game_state == "round_active" and exp.current_round == 2
    assert deadline > r1.guess_deadline_at
    assert sorted(r2.eligible_participant_ids) == sorted(r1.eligible_participant_ids)

    second = hwdyk.advance_round(db, exp, r1.id)  # double click
    assert second["advanced"] is False
    db.refresh(r2)
    assert r2.guess_deadline_at == deadline and exp.current_round == 2


def test_last_round_completes_the_game(db):
    exp, host, (bea, cal), r1 = go_live(db, num_questions=1)
    correct, _ = choice_ids(db, r1)
    hwdyk.submit_mc_guess(db, exp, r1.id, bea, correct)
    hwdyk.submit_mc_guess(db, exp, r1.id, cal, correct)
    out = hwdyk.advance_round(db, exp, r1.id)
    assert out["is_last"] and out["advanced"]
    assert exp.game_state == "completed"
    assert hwdyk.advance_round(db, exp, r1.id)["advanced"] is False


# ---------- roster freeze ----------


def test_late_arrival_in_the_session_does_not_change_who_must_guess(db):
    exp, host, (bea, cal), r1 = go_live(db)
    stranger = Participant(
        group_id=db.get(Participant, host).group_id,
        display_name="Dee",
        role="guest",
        join_type="anonymous",
    )
    db.add(stranger)
    db.flush()
    db.add(SessionParticipant(session_id=exp.session_id, participant_id=stranger.id))
    db.flush()
    correct, _ = choice_ids(db, r1)
    with pytest.raises(HTTPException) as e:
        hwdyk.submit_mc_guess(db, exp, r1.id, stranger.id, correct)
    assert e.value.status_code == 403
    hwdyk.submit_mc_guess(db, exp, r1.id, bea, correct)
    out = hwdyk.submit_mc_guess(db, exp, r1.id, cal, correct)
    assert out["all_guessed"] is True  # waited for the two frozen guessers, not Dee


def test_round_with_no_guessers_waits_for_the_deadline(db):
    exp, host, joined, r1 = go_live(db, players=())
    assert r1.eligible_participant_ids == []
    assert hwdyk.close_round_if_due(db, exp.id) is False
    assert hwdyk.close_round_if_due(db, exp.id, now=r1.guess_deadline_at + GRACE + timedelta(seconds=1))
    assert exp.game_state == "round_reveal"
