"""Who is here, host handover, removing players who left, and starting Who Knows
Who without the people still answering."""

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app.db.models.experience import ExperienceInstance
from app.db.models.participant import Participant
from app.db.session import get_db
from app.main import app
from app.services.games import catalog
from app.services.games.roster import (
    AWAY_AFTER_SECONDS,
    HOST_HANDOVER_SECONDS,
    host_of,
    is_away,
)
from app.services.games.sharing import generate_share_url

API = "/api/v1"


@pytest.fixture()
def client(db):
    app.dependency_overrides[get_db] = lambda: db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.pop(get_db, None)


def ago(seconds):
    return datetime.now(timezone.utc) - timedelta(seconds=seconds)


def set_seen(db, participant_id, seconds_ago):
    p = db.get(Participant, uuid.UUID(participant_id))
    p.last_seen_at = ago(seconds_ago)
    db.flush()


def in_join_order(db, *participant_ids):
    """Inside one test transaction every row gets the same created_at, so say
    who joined first explicitly (in production each join is its own request)."""
    start = datetime.now(timezone.utc) - timedelta(hours=1)
    for i, pid in enumerate(participant_ids):
        db.get(Participant, uuid.UUID(pid)).created_at = start + timedelta(seconds=i)
    db.flush()


def player(role="guest", seen=0):
    return Participant(id=uuid.uuid4(), role=role, last_seen_at=ago(seen), display_name="x")


class TestHostOf:
    def test_the_host_is_the_host_while_here(self):
        host, a, b = player("host"), player(), player()
        assert host_of([host, a, b], False) is host

    def test_a_short_blip_keeps_the_host(self):
        host, a = player("host", seen=HOST_HANDOVER_SECONDS - 10), player()
        assert host_of([host, a], False) is host

    def test_a_silent_host_hands_over_to_the_longest_standing_player_who_is_here(self):
        host = player("host", seen=HOST_HANDOVER_SECONDS + 5)
        gone = player(seen=AWAY_AFTER_SECONDS + 20)
        first, second = player(), player()
        assert host_of([host, gone, first, second], False) is first

    def test_the_host_gets_the_controls_back_when_they_return(self):
        host, a = player("host", seen=0), player()
        assert host_of([host, a], False) is host

    def test_nobody_else_here_means_the_host_stays(self):
        host = player("host", seen=500)
        other = player(seen=500)
        assert host_of([host, other], False) is host

    def test_is_away(self):
        assert is_away(player(seen=AWAY_AFTER_SECONDS + 1))
        assert not is_away(player(seen=AWAY_AFTER_SECONDS - 5))

    def test_replay_without_the_host_prefers_someone_here(self):
        gone, here = player(seen=500), player()
        assert host_of([gone, here], True) is here


class TestHotSeatSlug:
    def test_catalog_uses_the_new_slug_and_still_answers_to_the_old_one(self):
        slugs = [g["slug"] for g in catalog.list_games()]
        assert "the-hot-seat" in slugs and "how-well-do-you-know" not in slugs
        assert catalog.get_game("how-well-do-you-know")["display_name"] == "The Hot Seat"
        assert catalog.get_game("the-hot-seat")["display_name"] == "The Hot Seat"

    def test_invite_links_point_at_the_new_address(self):
        for slug in ("how-well-do-you-know", "the-hot-seat"):
            url = generate_share_url(uuid.uuid4(), "ABC123", game_slug=slug)
            assert url.endswith("/games/the-hot-seat?code=ABC123")

    def test_generic_create_for_the_hot_seat_points_to_the_real_route(self, client, db):
        r = client.post(f"{API}/games/the-hot-seat/create", json={"display_name": "Q"})
        assert r.status_code == 400


def make_hot_seat(client, db, names=("Bea", "Cal")):
    created = client.post(
        f"{API}/games/how-well-do-you-know/create", json={"display_name": "Quin"}
    ).json()
    exp, host, code = created["experience_instance_id"], created["participant_id"], created["join_code"]
    ids = [
        client.post(
            f"{API}/games/how-well-do-you-know/join",
            json={"join_code": code, "display_name": n},
        ).json()["participant_id"]
        for n in names
    ]
    in_join_order(db, host, *ids)
    return exp, host, ids


class TestPresence:
    def test_check_in_marks_someone_here(self, client, db):
        exp, host, (bea, _) = make_hot_seat(client, db)
        set_seen(db, bea, 120)
        r = client.post(f"{API}/experiences/{exp}/presence", json={"participant_id": bea}).json()
        assert r["member"] is True and r["removed"] is False
        assert not is_away(db.get(Participant, uuid.UUID(bea)))

    def test_lobby_shows_who_is_away(self, client, db):
        exp, host, (bea, cal) = make_hot_seat(client, db)
        set_seen(db, bea, 120)
        lobby = client.get(f"{API}/experiences/{exp}/hwdyk/lobby").json()
        away = {p["display_name"]: p["away"] for p in lobby["participants"]}
        assert away == {"Quin": False, "Bea": True, "Cal": False}

    def test_a_stranger_is_not_a_member(self, client, db):
        exp, *_ = make_hot_seat(client, db)
        r = client.post(f"{API}/experiences/{exp}/presence", json={"participant_id": str(uuid.uuid4())}).json()
        assert r == {"member": False, "removed": False, "left_out": False, "host_id": None}

    def test_the_host_role_passes_on_after_a_minute_and_comes_back(self, client, db):
        exp, host, (bea, cal) = make_hot_seat(client, db)
        assert client.get(f"{API}/experiences/{exp}/hwdyk/lobby").json()["host_id"] == host
        set_seen(db, host, HOST_HANDOVER_SECONDS + 10)
        lobby = client.get(f"{API}/experiences/{exp}/hwdyk/lobby").json()
        assert lobby["host_id"] == bea  # joined first among those still here
        assert [p["role"] for p in lobby["participants"]].count("host") == 1
        # the original host returns and checks in
        r = client.post(f"{API}/experiences/{exp}/presence", json={"participant_id": host}).json()
        assert r["host_id"] == host

    def test_a_stand_in_host_can_act_as_host(self, client, db):
        exp, host, (bea, cal) = make_hot_seat(client, db)
        set_seen(db, host, HOST_HANDOVER_SECONDS + 10)
        r = client.post(
            f"{API}/experiences/{exp}/select-main-person",
            json={"host_participant_id": bea, "main_person_participant_id": cal},
        )
        assert r.status_code == 200, r.text


class TestRemovePlayer:
    def remove(self, client, exp, host, target):
        return client.post(
            f"{API}/experiences/{exp}/remove-player",
            json={"host_participant_id": host, "participant_id": target},
        )

    def test_host_removes_someone_who_left(self, client, db):
        exp, host, (bea, cal) = make_hot_seat(client, db)
        set_seen(db, bea, 120)
        r = self.remove(client, exp, host, bea)
        assert r.status_code == 200, r.text
        names = [p["display_name"] for p in r.json()["participants"]]
        assert names == ["Quin", "Cal"]

    def test_the_removed_person_is_told_when_they_check_in(self, client, db):
        exp, host, (bea, cal) = make_hot_seat(client, db)
        set_seen(db, bea, 120)
        self.remove(client, exp, host, bea)
        r = client.post(f"{API}/experiences/{exp}/presence", json={"participant_id": bea}).json()
        assert r["member"] is False and r["removed"] is True

    def test_someone_who_is_still_here_cannot_be_removed(self, client, db):
        exp, host, (bea, cal) = make_hot_seat(client, db)
        r = self.remove(client, exp, host, bea)
        assert r.status_code == 409 and "still here" in r.json()["detail"]

    def test_only_the_host_can_remove(self, client, db):
        exp, host, (bea, cal) = make_hot_seat(client, db)
        set_seen(db, cal, 120)
        assert self.remove(client, exp, bea, cal).status_code == 403

    def test_cannot_remove_yourself(self, client, db):
        exp, host, _ = make_hot_seat(client, db)
        assert self.remove(client, exp, host, host).status_code == 400

    def test_removing_the_person_in_the_hot_seat_clears_the_choice(self, client, db):
        exp, host, (bea, cal) = make_hot_seat(client, db)
        client.post(
            f"{API}/experiences/{exp}/select-main-person",
            json={"host_participant_id": host, "main_person_participant_id": bea},
        )
        set_seen(db, bea, 120)
        r = self.remove(client, exp, host, bea).json()
        assert r["main_person_participant_id"] is None

    def test_not_after_setup_has_started(self, client, db):
        exp, host, (bea, cal) = make_hot_seat(client, db)
        row = db.get(ExperienceInstance, uuid.UUID(exp))
        row.game_state = "main_person_answering"
        db.flush()
        set_seen(db, bea, 120)
        assert self.remove(client, exp, host, bea).status_code == 409

    def test_a_stand_in_host_removing_the_original_keeps_the_room_hosted(self, client, db):
        exp, host, (bea, cal) = make_hot_seat(client, db)
        set_seen(db, host, HOST_HANDOVER_SECONDS + 10)
        assert client.get(f"{API}/experiences/{exp}/hwdyk/lobby").json()["host_id"] == bea
        r = self.remove(client, exp, bea, host)
        assert r.status_code == 200, r.text
        lobby = r.json()
        assert lobby["host_id"] == bea
        assert [p["display_name"] for p in lobby["participants"]] == ["Bea", "Cal"]
        assert [p["role"] for p in lobby["participants"]] == ["host", "guest"]

    def test_unknown_player(self, client, db):
        exp, host, _ = make_hot_seat(client, db)
        assert self.remove(client, exp, host, str(uuid.uuid4())).status_code == 404


def make_wkw(client, db, names=("Bea", "Cal", "Dee")):
    created = client.post(f"{API}/games/who-knows-who/create", json={"display_name": "Quin"}).json()
    exp, host, code = created["experience_instance_id"], created["participant_id"], created["join_code"]
    ids = [
        client.post(
            f"{API}/games/who-knows-who/join", json={"join_code": code, "display_name": n}
        ).json()["participant_id"]
        for n in names
    ]
    in_join_order(db, host, *ids)
    base = f"{API}/experiences/{exp}"
    assert client.post(f"{base}/start", json={"participant_id": host}).status_code == 200
    prompts = client.get(f"{base}/prompts", params={"participant_id": host}).json()["prompts"]
    return base, host, ids, prompts


def answer_all(client, base, pid, prompts, upto=None):
    for i, p in enumerate(prompts[:upto]):
        r = client.post(
            f"{base}/prompts/answer",
            json={"prompt_instance_id": p["id"], "participant_id": pid, "answer_text": f"answer {i}"},
        )
        assert r.status_code == 200, r.text


class TestStartWithFinished:
    def test_progress_lists_who_has_finished(self, client, db):
        base, host, (bea, cal, dee), prompts = make_wkw(client, db)
        answer_all(client, base, host, prompts)
        answer_all(client, base, bea, prompts)
        answer_all(client, base, cal, prompts)
        answer_all(client, base, dee, prompts, upto=4)
        pr = client.get(f"{base}/answer-progress", params={"participant_id": host}).json()
        assert pr["finished_count"] == 3 and pr["total_questions"] == 10
        by_name = {p["display_name"]: p for p in pr["players"]}
        assert by_name["Dee"]["answered"] == 4 and by_name["Dee"]["finished"] is False
        assert pr["can_start_now"] is True
        # only the host is offered the button
        other = client.get(f"{base}/answer-progress", params={"participant_id": bea}).json()
        assert other["can_start_now"] is False

    def test_host_starts_with_whoever_finished(self, client, db):
        base, host, (bea, cal, dee), prompts = make_wkw(client, db)
        for pid in (host, bea, cal):
            answer_all(client, base, pid, prompts)
        answer_all(client, base, dee, prompts, upto=2)
        r = client.post(f"{base}/start-with-finished", json={"participant_id": host})
        assert r.status_code == 200 and r.json() == {"ok": True, "players": 3, "left_out": 1}

        state = client.get(f"{base}/state", params={"participant_id": host}).json()
        assert state["game_state"] == "round_active"
        assert {p["display_name"] for p in state["participants"]} == {"Quin", "Bea", "Cal"}
        # nobody is asked to guess about Dee, and Dee's answers are not used
        for _ in range(state["max_rounds"]):
            round_ = client.get(f"{base}/state", params={"participant_id": host}).json()["round"]
            assert round_["guesser_count"] == 2
            break

        # Dee is told she was left out and cannot act in the game
        me = client.post(f"{base}/presence", json={"participant_id": dee}).json()
        assert me["left_out"] is True
        late = client.post(
            f"{base}/prompts/answer",
            json={"prompt_instance_id": prompts[9]["id"], "participant_id": dee, "answer_text": "late"},
        )
        assert late.status_code in (403, 409)

    def test_needs_three_finished(self, client, db):
        base, host, (bea, cal, dee), prompts = make_wkw(client, db)
        for pid in (host, bea):
            answer_all(client, base, pid, prompts)
        r = client.post(f"{base}/start-with-finished", json={"participant_id": host})
        assert r.status_code == 409 and "at least 3" in r.json()["detail"]
        pr = client.get(f"{base}/answer-progress", params={"participant_id": host}).json()
        assert pr["can_start_now"] is False

    def test_only_the_host_and_only_once_they_have_finished(self, client, db):
        base, host, (bea, cal, dee), prompts = make_wkw(client, db)
        for pid in (bea, cal, dee):
            answer_all(client, base, pid, prompts)
        assert client.post(f"{base}/start-with-finished", json={"participant_id": bea}).status_code == 403
        r = client.post(f"{base}/start-with-finished", json={"participant_id": host})
        assert r.status_code == 409 and "own answers" in r.json()["detail"]

    def test_nothing_to_skip_when_everyone_finished(self, client, db):
        base, host, ids, prompts = make_wkw(client, db)
        for pid in (host, *ids):
            answer_all(client, base, pid, prompts)
        # the game already started on its own
        r = client.post(f"{base}/start-with-finished", json={"participant_id": host})
        assert r.status_code == 409

    def test_left_out_player_can_come_back_for_the_replay(self, client, db):
        base, host, (bea, cal, dee), prompts = make_wkw(client, db)
        for pid in (host, bea, cal):
            answer_all(client, base, pid, prompts)
        client.post(f"{base}/start-with-finished", json={"participant_id": host})
        exp = db.get(ExperienceInstance, uuid.UUID(base.rsplit("/", 1)[1]))
        assert exp.excluded_participant_ids == [dee]

    def test_a_stand_in_host_can_advance_when_the_host_closed_their_tab(self, client, db):
        base, host, (bea, cal), prompts = make_wkw(client, db, names=("Bea", "Cal"))
        for pid in (host, bea, cal):
            answer_all(client, base, pid, prompts)
        state = client.get(f"{base}/state", params={"participant_id": host}).json()
        rid = state["round"]["round_id"]
        owner_views = {
            pid: client.get(f"{base}/state", params={"participant_id": pid}).json()["round"]["is_yours"]
            for pid in (host, bea, cal)
        }
        owner = next(pid for pid, mine in owner_views.items() if mine)
        for pid in (host, bea, cal):
            if pid != owner:
                client.post(
                    f"{base}/rounds/{rid}/guess",
                    json={"guessing_participant_id": pid, "guessed_participant_id": owner},
                )
        # the host closes their tab; revealing is allowed to anyone once all have guessed,
        # but moving on needs a host
        client.post(f"{base}/rounds/{rid}/reveal", json={"participant_id": bea})
        assert client.post(f"{base}/rounds/{rid}/advance", json={"participant_id": bea}).status_code == 403
        set_seen(db, host, HOST_HANDOVER_SECONDS + 10)
        lobby = client.get(f"{base}/lobby").json()
        assert lobby["host_id"] == bea
        r = client.post(f"{base}/rounds/{rid}/advance", json={"participant_id": bea})
        assert r.status_code == 200, r.text
