"""Return to lobby / play again for Hot Seat (phase 4).

The session and join code stay the same; every game is its own experience, so
each replay starts with no rounds, guesses, scores or timers from the last one.
"""

import uuid
from datetime import datetime, timezone
from unittest.mock import patch

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.db.models.experience import ExperienceInstance
from app.db.models.game_mc_guess import GameMCGuess
from app.db.models.game_round import GameRound
from app.db.models.participant import Participant
from app.db.models.prompt import PromptInstance
from app.db.session import get_db
from app.main import app
from app.services.games import hwdyk_phases as phases
from app.services.games import how_well_do_you_know as hwdyk
from app.tests.hwdyk_testkit import (
    GEN_LLM,
    answer,
    choice_ids,
    fake_llm,
    go_live,
)


def finish(db, exp, r1, guessers):
    """Everyone guesses the first round (the only one) and the game ends."""
    correct, _ = choice_ids(db, r1)
    for g in guessers:
        hwdyk.submit_mc_guess(db, exp, r1.id, g, correct)
    hwdyk.advance_round(db, exp, r1.id, hwdyk._effective_host(db, exp).id)
    assert exp.game_state == "completed"


def finished_game(db, players=("Bea", "Cal")):
    exp, host, joined, r1 = go_live(db, num_questions=1, players=players)
    finish(db, exp, r1, joined)
    return exp, host, joined


def play_to_live(db, exp, host, main):
    """Run a replay lobby through prep and start round 1."""
    hwdyk.select_main_person(db, exp, host, main)
    hwdyk.start_setup(db, exp, host)
    answer(db, exp, main)
    if exp.game_state == phases.GENERATING:
        with patch(GEN_LLM, side_effect=fake_llm):
            phases.run_generation(db, exp.id)
        db.refresh(exp)
    hwdyk.confirm_choices(db, exp, main)
    hwdyk.start_live_game(db, exp, host)
    db.refresh(exp)
    return (
        db.query(GameRound)
        .filter_by(experience_instance_id=exp.id, round_number=1)
        .one()
    )


def ids(exp):
    return set(exp.present_participant_ids)


def get_exp(db, out):
    return db.get(ExperienceInstance, uuid.UUID(out["experience_instance_id"]))


# ---------- returning ----------


def test_first_return_opens_the_next_lobby_in_the_same_session(db):
    exp, host, (bea, cal) = finished_game(db)
    out = hwdyk.enter_lobby(db, exp, bea)
    nxt = get_exp(db, out)

    assert nxt.id != exp.id and nxt.session_id == exp.session_id
    assert nxt.parent_experience_instance_id == exp.id
    assert nxt.game_state == "lobby"
    assert ids(nxt) == {str(bea)}
    # Same join code as before: nothing new to share.
    assert out["join_code"] == hwdyk.get_lobby_payload(db, exp)["join_code"]


def test_everyone_returning_ends_up_in_one_lobby_without_duplicates(db):
    exp, host, (bea, cal) = finished_game(db)
    first = hwdyk.enter_lobby(db, exp, bea)
    for who in (host, cal, bea, bea):  # bea refreshes / double-clicks
        again = hwdyk.enter_lobby(db, exp, who)
        assert again["experience_instance_id"] == first["experience_instance_id"]
    nxt = get_exp(db, first)
    assert sorted(nxt.present_participant_ids) == sorted(map(str, (host, bea, cal)))
    assert db.query(ExperienceInstance).filter_by(parent_experience_instance_id=exp.id).count() == 1


def test_players_who_do_not_return_are_not_in_the_next_game(db):
    exp, host, (bea, cal) = finished_game(db)
    nxt = get_exp(db, hwdyk.enter_lobby(db, exp, host))
    hwdyk.enter_lobby(db, exp, bea)

    lobby = hwdyk.get_lobby_payload(db, nxt)
    assert {p["id"] for p in lobby["participants"]} == {str(host), str(bea)}
    assert [p["id"] for p in lobby["absent_participants"]] == [str(cal)]
    assert lobby["is_replay"] is True

    # Cal can't be put in the hot seat while away...
    with pytest.raises(HTTPException) as e:
        hwdyk.select_main_person(db, nxt, host, cal)
    assert e.value.status_code == 400

    # ...and doesn't count as a guesser, so can't hold the round up or guess.
    r1 = play_to_live(db, nxt, host, bea)
    assert r1.eligible_participant_ids == [str(host)]
    correct, _ = choice_ids(db, r1)
    with pytest.raises(HTTPException):
        hwdyk.submit_mc_guess(db, nxt, r1.id, cal, correct)


def test_someone_who_missed_the_start_can_still_enter_the_open_lobby(db):
    exp, host, (bea, cal) = finished_game(db)
    nxt = get_exp(db, hwdyk.enter_lobby(db, exp, host))
    assert str(cal) not in ids(nxt)
    # Cal opens the (old) results link late, or the new lobby link directly.
    out = hwdyk.enter_lobby(db, nxt, cal)
    assert out["experience_instance_id"] == str(nxt.id)
    assert str(cal) in ids(nxt)


def test_new_people_joining_by_code_land_in_the_replay_lobby(db):
    exp, host, _ = finished_game(db)
    nxt = get_exp(db, hwdyk.enter_lobby(db, exp, host))
    code = hwdyk.get_lobby_payload(db, nxt)["join_code"]
    joined = hwdyk.join_game(db, code, "Dee")
    assert joined["experience_instance_id"] == str(nxt.id)
    assert joined["participant_id"] in ids(nxt)


def test_cannot_enter_a_game_that_is_already_under_way(db):
    exp, host, (bea, cal) = finished_game(db)
    nxt = get_exp(db, hwdyk.enter_lobby(db, exp, host))
    hwdyk.enter_lobby(db, exp, bea)
    play_to_live(db, nxt, host, bea)

    with pytest.raises(HTTPException) as e:
        hwdyk.enter_lobby(db, exp, cal)  # via the old results page
    assert e.value.detail["code"] == "game_in_progress"
    assert str(cal) not in ids(nxt)

    code = hwdyk.get_lobby_payload(db, nxt)["join_code"]
    with pytest.raises(HTTPException) as e:
        hwdyk.join_game(db, code, "Late Larry")
    assert e.value.status_code == 409


def test_strangers_cannot_return(db):
    exp, host, _ = finished_game(db)
    with pytest.raises(HTTPException) as e:
        hwdyk.enter_lobby(db, exp, uuid.uuid4())
    assert e.value.status_code == 403


def test_older_clients_replay_with_everyone(db):
    exp, host, (bea, cal) = finished_game(db)
    nxt = get_exp(db, hwdyk.enter_lobby(db, exp, None, everyone=True))
    assert ids(nxt) == {str(host), str(bea), str(cal)}


# ---------- nothing leaks between games ----------


def test_the_new_game_starts_clean_and_the_old_one_is_kept(db):
    exp, host, (bea, cal) = finished_game(db)
    old_scores = hwdyk.compute_hwdyk_scores(db, exp.id)
    assert old_scores and any(s["score"] > 0 for s in old_scores)
    exp.game_config = {**exp.game_config, "regenerate_counts": {"x": 2}, "notice": {"code": "old", "message": "old"}}
    db.flush()

    nxt = get_exp(db, hwdyk.enter_lobby(db, exp, host))
    hwdyk.enter_lobby(db, exp, bea)

    assert nxt.game_state == "lobby" and nxt.current_round == 0
    assert nxt.main_person_participant_id is None
    assert nxt.phase_deadline_at is None and nxt.completed_at is None
    assert "regenerate_counts" not in nxt.game_config and "notice" not in nxt.game_config
    assert nxt.game_config["num_questions"] == exp.game_config["num_questions"]
    for model, col in (
        (GameRound, GameRound.experience_instance_id),
        (PromptInstance, PromptInstance.experience_instance_id),
    ):
        assert db.query(model).filter(col == nxt.id).count() == 0
    assert all(s["score"] == 0 for s in hwdyk.compute_hwdyk_scores(db, nxt.id))

    # The finished game is untouched.
    assert exp.game_state == "completed"
    assert hwdyk.compute_hwdyk_scores(db, exp.id) == old_scores


def test_scores_are_per_game_not_cumulative(db):
    exp, host, (bea, cal) = finished_game(db)
    nxt = get_exp(db, hwdyk.enter_lobby(db, exp, host))
    for who in (bea, cal):
        hwdyk.enter_lobby(db, exp, who)
    r1 = play_to_live(db, nxt, host, bea)
    correct, _ = choice_ids(db, r1)
    hwdyk.submit_mc_guess(db, nxt, r1.id, host, correct)
    guesses = db.query(GameMCGuess).filter(GameMCGuess.game_round_id == r1.id).all()
    assert len(guesses) == 1  # none of the old game's guesses are in this round
    by_id = {s["participant_id"]: s for s in hwdyk.compute_hwdyk_scores(db, nxt.id)}
    assert by_id[str(host)]["correct_count"] == 1
    assert by_id[str(cal)]["correct_count"] == 0


# ---------- repeated replays and stale links ----------


def test_repeated_replays_keep_working_and_stale_links_find_the_latest(db):
    g1, host, (bea, cal) = finished_game(db)
    everyone = (host, bea, cal)

    g2 = get_exp(db, hwdyk.enter_lobby(db, g1, host))
    for who in everyone:
        hwdyk.enter_lobby(db, g1, who)
    r = play_to_live(db, g2, host, bea)
    finish(db, g2, r, [host, cal])

    g3 = get_exp(db, hwdyk.enter_lobby(db, g2, cal))
    assert g3.id not in (g1.id, g2.id) and g3.parent_experience_instance_id == g2.id
    assert ids(g3) == {str(cal)}

    # Somebody still has game 1's results page open.
    stale = hwdyk.enter_lobby(db, g1, bea)
    assert stale["experience_instance_id"] == str(g3.id)
    assert ids(g3) == {str(cal), str(bea)}
    assert hwdyk.replay_status(db, g1)["next_experience_id"] == str(g2.id)


def test_hot_seat_can_rotate_but_the_last_main_person_is_flagged(db):
    g1, host, (bea, cal) = finished_game(db)
    g2 = get_exp(db, hwdyk.enter_lobby(db, g1, host))
    hwdyk.enter_lobby(db, g1, bea)
    lobby = hwdyk.get_lobby_payload(db, g2)
    assert lobby["previous_main_person_id"] == str(host)  # host was in the hot seat
    hwdyk.select_main_person(db, g2, host, host)  # allowed again if the group wants


# ---------- host and roster edge cases ----------


def test_if_the_host_does_not_return_the_longest_standing_player_hosts(db):
    exp, host, (bea, cal) = finished_game(db)
    # (a test runs in one transaction, so give the join times explicitly)
    db.get(Participant, bea).created_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
    db.get(Participant, cal).created_at = datetime(2026, 1, 2, tzinfo=timezone.utc)
    db.flush()
    nxt = get_exp(db, hwdyk.enter_lobby(db, exp, cal))
    hwdyk.enter_lobby(db, exp, bea)

    lobby = hwdyk.get_lobby_payload(db, nxt)
    assert lobby["host_id"] == str(bea)  # joined before Cal
    assert [p["role"] for p in lobby["participants"]] == ["host", "guest"]
    with pytest.raises(HTTPException) as e:
        hwdyk.select_main_person(db, nxt, host, cal)  # absent original host
    assert e.value.status_code == 403
    hwdyk.select_main_person(db, nxt, bea, cal)

    # The original host coming back takes the role back.
    hwdyk.enter_lobby(db, exp, host)
    assert hwdyk.get_lobby_payload(db, nxt)["host_id"] == str(host)


def test_a_lone_returner_cannot_start_a_game(db):
    exp, host, _ = finished_game(db)
    nxt = get_exp(db, hwdyk.enter_lobby(db, exp, host))
    hwdyk.select_main_person(db, nxt, host, host)
    with pytest.raises(HTTPException) as e:
        hwdyk.start_setup(db, nxt, host)
    assert e.value.detail["code"] == "not_enough_players"
    assert nxt.game_state == "lobby"
    # once a second person is in, it goes
    hwdyk.enter_lobby(db, exp, uuid.UUID(sorted(hwdyk.get_lobby_payload(db, nxt)["absent_participants"], key=lambda p: p["display_name"])[0]["id"]))
    hwdyk.start_setup(db, nxt, host)
    assert nxt.game_state == "main_person_answering"


def test_main_person_cannot_be_swapped_once_setup_has_started(db):
    exp, host, (bea, cal) = finished_game(db)
    nxt = get_exp(db, hwdyk.enter_lobby(db, exp, host))
    hwdyk.enter_lobby(db, exp, bea)
    hwdyk.select_main_person(db, nxt, host, bea)
    hwdyk.start_setup(db, nxt, host)
    with pytest.raises(HTTPException) as e:
        hwdyk.select_main_person(db, nxt, host, host)
    assert e.value.detail["code"] == "setup_in_progress"
    assert nxt.main_person_participant_id == bea


def test_first_games_are_unaffected(db):
    """No roster set => everyone in the session, as before replays existed."""
    exp, host, joined, _ = go_live(db)
    assert exp.present_participant_ids is None
    lobby = hwdyk.get_lobby_payload(db, exp)
    assert lobby["is_replay"] is False and lobby["absent_participants"] == []
    assert len(lobby["participants"]) == 3


# ---------- over HTTP ----------


@pytest.fixture()
def client(db):
    app.dependency_overrides[get_db] = lambda: db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.pop(get_db, None)


def test_http_flow_results_screen_to_lobby(client, db):
    exp, host, (bea, cal) = finished_game(db)

    board = client.get(f"/api/v1/experiences/{exp.id}/hwdyk/leaderboard").json()
    assert board["next_experience_id"] is None and board["returned_ids"] == []
    assert board["participant_count"] == 3

    r = client.post(
        f"/api/v1/experiences/{exp.id}/hwdyk/return",
        json={"participant_id": str(bea)},
    )
    assert r.status_code == 200
    new_id = r.json()["experience_instance_id"]

    board = client.get(f"/api/v1/experiences/{exp.id}/hwdyk/leaderboard").json()
    assert board["next_experience_id"] == new_id
    assert board["next_game_state"] == "lobby"
    assert board["returned_ids"] == [str(bea)]

    lobby = client.get(f"/api/v1/experiences/{new_id}/hwdyk/lobby").json()
    assert [p["id"] for p in lobby["participants"]] == [str(bea)]
    assert len(lobby["absent_participants"]) == 2

    bad = client.post(
        f"/api/v1/experiences/{exp.id}/hwdyk/return",
        json={"participant_id": "nope"},
    )
    assert bad.status_code in (400, 404, 422)
    stranger = client.post(
        f"/api/v1/experiences/{exp.id}/hwdyk/return",
        json={"participant_id": str(uuid.uuid4())},
    )
    assert stranger.status_code == 403


def test_http_old_replay_endpoint_still_works(client, db):
    exp, host, _ = finished_game(db)
    r = client.post(f"/api/v1/experiences/{exp.id}/hwdyk/replay")
    assert r.status_code == 200
    body = r.json()
    assert body["experience_instance_id"] and body["join_code"] and body["share_url"]
    nxt = db.get(ExperienceInstance, uuid.UUID(body["experience_instance_id"]))
    assert len(nxt.present_participant_ids) == 3
