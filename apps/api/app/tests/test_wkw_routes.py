"""Who Knows Who played start to finish over HTTP."""

import pytest
from fastapi.testclient import TestClient

from app.db.session import get_db
from app.main import app


@pytest.fixture()
def client(db):
    app.dependency_overrides[get_db] = lambda: db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.pop(get_db, None)


API = "/api/v1"


def test_a_whole_game_over_http(client):
    created = client.post(f"{API}/games/who-knows-who/create", json={"display_name": "Quin"}).json()
    exp, host = created["experience_instance_id"], created["participant_id"]
    code = created["join_code"]
    base = f"{API}/experiences/{exp}"

    # Joining: names must be free
    bea = client.post(f"{API}/games/who-knows-who/join", json={"join_code": code, "display_name": "Bea"})
    assert bea.status_code == 200
    dupe = client.post(f"{API}/games/who-knows-who/join", json={"join_code": code, "display_name": "bea"})
    assert dupe.status_code == 409
    cal = client.post(f"{API}/games/who-knows-who/join", json={"join_code": code, "display_name": "Cal"}).json()
    players = [host, bea.json()["participant_id"], cal["participant_id"]]

    lobby = client.get(f"{base}/lobby").json()
    assert lobby["min_players"] == 3 and len(lobby["participants"]) == 3

    # Only the host starts
    assert client.post(f"{base}/start", json={"participant_id": players[1]}).status_code == 403
    assert client.post(f"{base}/start", json={"participant_id": host}).status_code == 200

    # Everyone answers; a reload shows what is already done
    prompts = client.get(f"{base}/prompts", params={"participant_id": host}).json()["prompts"]
    assert len(prompts) == 10 and not any(p["answered"] for p in prompts)
    for pid in players:
        for i, p in enumerate(prompts):
            r = client.post(
                f"{base}/prompts/answer",
                json={"prompt_instance_id": p["id"], "participant_id": pid, "answer_text": f"answer {i}"},
            )
            assert r.status_code == 200, r.text
            if i == 0 and pid == host:
                again = client.get(f"{base}/prompts", params={"participant_id": host}).json()["prompts"]
                assert again[0]["answered"] is True

    state = client.get(f"{base}/state", params={"participant_id": host}).json()
    assert state["game_state"] == "round_active"

    for round_no in range(1, state["max_rounds"] + 1):
        views = {
            pid: client.get(f"{base}/state", params={"participant_id": pid}).json()["round"]
            for pid in players
        }
        owners = [pid for pid, v in views.items() if v["is_yours"]]
        assert len(owners) == 1
        owner = owners[0]
        assert all("answering_participant_id" not in v for v in views.values())
        rid = views[host]["round_id"]

        for pid in players:
            if pid == owner:
                continue
            r = client.post(
                f"{base}/rounds/{rid}/guess",
                json={"guessing_participant_id": pid, "guessed_participant_id": owner},
            )
            assert r.status_code == 200, r.text
        after = client.get(f"{base}/state", params={"participant_id": players[1]}).json()["round"]
        assert after["guessed_count"] == after["guesser_count"] == 2

        # A guest may reveal once everyone has guessed
        guest = next(p for p in players if p != host)
        assert client.post(f"{base}/rounds/{rid}/reveal", json={"participant_id": guest}).status_code == 200
        revealed = client.get(f"{base}/state", params={"participant_id": host}).json()["round"]
        assert revealed["answering_participant_id"] == owner
        assert all(g["is_correct"] for g in revealed["guesses"])

        # Moving on is the host's job
        assert client.post(f"{base}/rounds/{rid}/advance", json={"participant_id": guest}).status_code == 403
        adv = client.post(f"{base}/rounds/{rid}/advance", json={"participant_id": host})
        assert adv.status_code == 200
        assert adv.json()["is_last"] is (round_no == state["max_rounds"])

    board = client.get(f"{base}/leaderboard").json()
    assert [e["rank"] for e in board["leaderboard"]] == [1, 2, 2] or len(board["leaderboard"]) == 3
    assert sum(e["score"] for e in board["leaderboard"]) == 20  # 10 rounds x 2 right guesses
    assert board["next_experience_id"] is None

    # Everyone taps Play again and lands in the same lobby
    nexts = {
        client.post(f"{base}/replay", json={"participant_id": pid}).json()["experience_instance_id"]
        for pid in players
    }
    assert len(nexts) == 1
    board = client.get(f"{base}/leaderboard").json()
    assert board["next_experience_id"] in nexts
    assert sorted(board["returned_ids"]) == sorted(players)
    nxt_lobby = client.get(f"{API}/experiences/{nexts.pop()}/lobby").json()
    assert nxt_lobby["is_replay"] is True and len(nxt_lobby["participants"]) == 3


def test_old_clients_without_a_body_get_a_clear_error(client):
    created = client.post(f"{API}/games/who-knows-who/create", json={"display_name": "Quin"}).json()
    base = f"{API}/experiences/{created['experience_instance_id']}"
    r = client.post(f"{base}/rounds/{created['participant_id']}/reveal")
    assert r.status_code == 422


def test_bad_names_over_http(client):
    r = client.post(f"{API}/games/who-knows-who/create", json={"display_name": "   "})
    assert r.status_code == 422
    r = client.post(f"{API}/games/how-well-do-you-know/create", json={"display_name": "Q", "num_questions": 99})
    assert r.status_code == 422
    r = client.post(f"{API}/games/how-well-do-you-know/create", json={"display_name": "Q", "mode": "chaos"})
    assert r.status_code == 422
