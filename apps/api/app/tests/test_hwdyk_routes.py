"""HTTP-level checks for the Hot Seat prep endpoints (wiring, status codes)."""

from datetime import timedelta
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.db.session import get_db
from app.main import app
from app.services.games import hwdyk_phases as phases
from app.tests.hwdyk_testkit import GEN_LLM, fake_llm, new_game, wrong_choices


@pytest.fixture()
def client(db):
    app.dependency_overrides[get_db] = lambda: db
    # Background generation normally opens its own session; run it on the test one.
    with patch(
        "app.api.v1.routes.games._run_generation_task",
        side_effect=lambda eid: _gen(db, eid),
    ), TestClient(app) as c:
        yield c
    app.dependency_overrides.pop(get_db, None)


def _gen(db, eid):
    with patch(GEN_LLM, side_effect=fake_llm):
        phases.run_generation(db, eid)


def test_lobby_reports_clock_and_progress(client, db):
    exp, host, _ = new_game(db, num_questions=3)
    r = client.get(f"/api/v1/experiences/{exp.id}/hwdyk/lobby")
    assert r.status_code == 200
    body = r.json()
    assert body["game_state"] == "main_person_answering"
    assert body["phase"]["duration_seconds"] == 20  # per question
    assert body["progress"] == {"answered": 0, "total": 3, "current_index": 0}
    assert body["notice"] is None


def test_a_lobby_poll_after_the_deadline_ends_the_phase(client, db):
    exp, host, _ = new_game(db)
    exp.phase_deadline_at = exp.phase_deadline_at - timedelta(seconds=120)
    db.flush()
    body = client.get(f"/api/v1/experiences/{exp.id}/hwdyk/lobby").json()
    assert body["game_state"] == "lobby"
    assert body["notice"]["code"] == "no_answers"


def test_full_prep_flow_over_http(client, db):
    exp, host, _ = new_game(db, num_questions=2)
    base = f"/api/v1/experiences/{exp.id}"

    qs = client.get(f"{base}/main-person-questions").json()
    assert qs["phase"]["name"] == "main_person_answering"
    assert [q["answered"] for q in qs["questions"]] == [False, False]
    assert qs["current_index"] == 0

    last = None
    for i, q in enumerate(qs["questions"]):
        last = client.post(
            f"{base}/main-person-answer",
            json={
                "prompt_instance_id": q["id"],
                "participant_id": str(host),
                "answer_text": f"Pizza {i}",
            },
        )
        assert last.status_code == 200
    assert last.json() == {
        "ok": True,
        "all_answered": True,
        "phase": None,  # the AI takes over; nothing is ticking
        "current_index": None,
    }  # (the internal needs_generation flag is not leaked)

    review = client.get(f"{base}/review-choices", params={"participant_id": str(host)}).json()
    assert review["game_state"] == "main_person_reviewing_choices"
    assert review["phase"]["duration_seconds"] == 60  # up to 5 questions
    wrong = [c for c in review["rounds"][0]["choices"] if not c["is_correct"]]
    target = wrong[0]
    assert target["revision"] == 0

    edit = client.post(
        f"{base}/choices/{target['id']}/edit",
        json={"participant_id": str(host), "new_text": "Mom's casserole", "expected_revision": 0},
    )
    assert edit.status_code == 200 and edit.json()["revision"] == 1

    stale = client.post(
        f"{base}/choices/{target['id']}/edit",
        json={"participant_id": str(host), "new_text": "Old", "expected_revision": 0},
    )
    assert stale.status_code == 409
    assert stale.json()["detail"]["code"] == "stale_revision"

    dup = client.post(
        f"{base}/choices/{wrong[1]['id']}/edit",
        json={"participant_id": str(host), "new_text": "mom's  CASSEROLE"},
    )
    assert dup.status_code == 409 and dup.json()["detail"]["code"] == "duplicate_choice"

    bad_confirm = client.post(
        f"{base}/confirm-choices",
        json={"participant_id": str(host), "revisions": {target["id"]: 0}},
    )
    assert bad_confirm.status_code == 409

    ok = client.post(
        f"{base}/confirm-choices",
        json={"participant_id": str(host), "revisions": {target["id"]: 1}},
    )
    assert ok.status_code == 200
    assert client.get(f"{base}/hwdyk/lobby").json()["game_state"] == "ready_to_start"


def test_malformed_ids_are_clean_errors(client, db):
    exp, host, _ = new_game(db)
    assert client.get("/api/v1/experiences/not-a-uuid/hwdyk/lobby").status_code == 404
    r = client.get(
        f"/api/v1/experiences/{exp.id}/review-choices", params={"participant_id": "nope"}
    )
    assert r.status_code == 400


def test_a_slow_question_is_skipped_over_http(client, db):
    exp, host, _ = new_game(db, num_questions=3)
    base = f"/api/v1/experiences/{exp.id}"
    exp.phase_deadline_at = exp.phase_deadline_at - timedelta(seconds=25)
    exp.phase_started_at = exp.phase_started_at - timedelta(seconds=25)
    db.flush()
    qs = client.get(f"{base}/main-person-questions").json()  # the poll skips Q1
    assert qs["current_index"] == 1
    assert [(q["skipped"], q["current"]) for q in qs["questions"]] == [
        (True, False),
        (False, True),
        (False, False),
    ]
    assert 10 < qs["phase"]["seconds_remaining"] <= 20
    late = client.post(
        f"{base}/main-person-answer",
        json={
            "prompt_instance_id": qs["questions"][0]["id"],
            "participant_id": str(host),
            "answer_text": "Too slow",
        },
    )
    assert late.status_code == 409
    assert late.json()["detail"]["code"] == "question_skipped"
