"""Discussion Questions flow: describe group → follow-ups → profile → questions → feedback."""

from __future__ import annotations

import uuid
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.db.models.feedback import UserQuestionFeedback
from app.db.models.group_profile import GroupProfile
from app.db.models.question_item import QuestionItem
from app.db.session import get_db
from app.main import app
from app.services.intake.options import OTHER_OPTION, is_other_option, normalize_options

API = "/api/v1"
INTAKE_LLM = "app.services.intake.followups.call_llm_json"
SYNTH_LLM = "app.services.intake.synthesis.call_llm_json"
EMBED = "app.services.intake.synthesis.embed_text"


def _vec(i: int) -> list[float]:
    v = [0.0] * 1536
    v[0] = 1.0
    v[1 + (i % 1500)] = 0.01 * (i + 1)
    return v


def _extraction(*prompts: str) -> dict:
    return {
        "group_summary": "College friends",
        "audience_context": "friends",
        "desired_vibe": "playful",
        "depth_preference": 3,
        "language": "en",
        "followup_needed": True,
        "followup_question_specs": [
            {
                "prompt_text": p,
                "options": ["Weekend get-togethers", "Mother's side", "Other (type your own)"],
                "allow_other": True,
                "answer_type": "single_select",
                "why_needed": "to know",
            }
            for p in prompts
        ],
    }


SYNTHESIS = {
    "summary": "Playful college friends",
    "key_traits": ["playful"],
    "topics_of_interest": ["nostalgia"],
    "constraints": [],
    "vibe": "playful",
    "depth": 3,
    "audience_context": "friends",
    "language": "en",
    "safety_policy_name": "default",
}


@pytest.fixture()
def client(db):
    app.dependency_overrides[get_db] = lambda: db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.pop(get_db, None)


def _guest(client) -> dict:
    r = client.post(f"{API}/auth/guest")
    assert r.status_code == 200, r.text
    return r.json()


def _describe(client, g, *prompts, text="We are college friends"):
    with patch(INTAKE_LLM, return_value=_extraction(*prompts)):
        return client.post(
            f"{API}/sessions/{g['session_id']}/group-text",
            json={"text": text, "participant_id": g["participant_id"]},
        )


# ---- "Other" option handling --------------------------------------------------


def test_other_option_is_recognised_exactly():
    assert is_other_option("Other (type your own)")
    assert is_other_option("other")
    assert is_other_option(" Other (please specify) ")
    # Ordinary options that merely contain the letters must not count.
    assert not is_other_option("Weekend get-togethers")
    assert not is_other_option("Mother's side")
    assert not is_other_option("Other people's stories")


def test_normalize_options_keeps_real_options_and_ends_with_other():
    out = normalize_options(
        ["Weekend get-togethers", "weekend get-togethers", " ", "Other", "Mother's side"]
    )
    assert out == ["Weekend get-togethers", "Mother's side", OTHER_OPTION]


# ---- Describing the group ---------------------------------------------------------


def test_group_text_is_validated(client):
    g = _guest(client)
    for bad in ("", "   ", "x" * 2001):
        r = client.post(
            f"{API}/sessions/{g['session_id']}/group-text",
            json={"text": bad, "participant_id": g["participant_id"]},
        )
        assert r.status_code == 422, bad[:10]


def test_only_session_members_can_describe_the_group(client):
    g, other = _guest(client), _guest(client)
    r = _describe(client, {**g, "participant_id": other["participant_id"]}, "Q1")
    assert r.status_code == 403


def test_generation_failure_is_a_clean_502(client):
    g = _guest(client)
    with patch(INTAKE_LLM, side_effect=RuntimeError("boom")):
        r = client.post(
            f"{API}/sessions/{g['session_id']}/group-text",
            json={"text": "hi", "participant_id": g["participant_id"]},
        )
    assert r.status_code == 502
    assert "try again" in r.json()["detail"].lower()


def test_options_with_together_still_get_an_other_choice(client):
    g = _guest(client)
    assert _describe(client, g, "What do you do?").status_code == 200
    prompts = client.get(f"{API}/sessions/{g['session_id']}/followups").json()["prompts"]
    assert prompts[0]["options"] == ["Weekend get-togethers", "Mother's side", OTHER_OPTION]


def test_followups_keep_the_order_the_model_wrote_them(client):
    g = _guest(client)
    qs = [f"Question {i}" for i in range(6)]
    _describe(client, g, *qs)
    got = client.get(f"{API}/sessions/{g['session_id']}/followups").json()["prompts"]
    assert [p["prompt_text"] for p in got] == qs


def test_describing_the_group_again_replaces_the_old_followups(client):
    g = _guest(client)
    first = _describe(client, g, "Old 1", "Old 2").json()
    second = _describe(client, g, "New 1", "New 2", "New 3").json()
    got = client.get(f"{API}/sessions/{g['session_id']}/followups").json()
    assert [p["prompt_text"] for p in got["prompts"]] == ["New 1", "New 2", "New 3"]
    assert got["provisional_group_profile_id"] == second["provisional_group_profile_id"]
    assert got["provisional_group_profile_id"] != first["provisional_group_profile_id"]


# ---- Answering ------------------------------------------------------------------------


def _answer(client, g, prompt_id, **body):
    return client.post(
        f"{API}/sessions/{g['session_id']}/followups/answer",
        json={"prompt_instance_id": prompt_id, "participant_id": g["participant_id"], **body},
    )


def test_answers_are_validated(client):
    g = _guest(client)
    _describe(client, g, "Q1")
    pid = client.get(f"{API}/sessions/{g['session_id']}/followups").json()["prompts"][0]["id"]

    assert _answer(client, g, pid, selected_option="Not a choice").status_code == 400
    assert _answer(client, g, pid, selected_option=OTHER_OPTION).status_code == 400
    assert _answer(client, g, pid, other_text="   ").status_code == 400
    assert _answer(client, g, pid, other_text="y" * 201).status_code == 400
    assert _answer(client, g, pid, selected_option="Weekend get-togethers").status_code == 200
    assert _answer(client, g, pid, other_text="Road trips").status_code == 200


def test_outsiders_cannot_answer(client):
    g, other = _guest(client), _guest(client)
    _describe(client, g, "Q1")
    pid = client.get(f"{API}/sessions/{g['session_id']}/followups").json()["prompts"][0]["id"]
    r = _answer(client, {**g, "participant_id": other["participant_id"]}, pid, other_text="hi")
    assert r.status_code == 403


def test_answering_twice_keeps_one_answer_and_synthesis_sees_it_once(client, db):
    g = _guest(client)
    prof = _describe(client, g, "What do you do?").json()["provisional_group_profile_id"]
    pid = client.get(f"{API}/sessions/{g['session_id']}/followups").json()["prompts"][0]["id"]
    _answer(client, g, pid, selected_option="Mother's side")
    _answer(client, g, pid, selected_option="Weekend get-togethers")  # changed mind / reloaded

    with patch(SYNTH_LLM, return_value=SYNTHESIS) as llm, patch(EMBED, return_value=_vec(0)):
        r = client.post(
            f"{API}/sessions/{g['session_id']}/group-profile/commit",
            json={"provisional_group_profile_id": prof},
        )
    assert r.status_code == 200, r.text
    user_prompt = llm.call_args.args[1]
    assert user_prompt.count("Q: What do you do?") == 1
    assert "A: Weekend get-togethers" in user_prompt
    assert "Mother's side" not in user_prompt


def test_cannot_commit_another_groups_profile(client):
    g, other = _guest(client), _guest(client)
    prof = _describe(client, other, "Q1").json()["provisional_group_profile_id"]
    with patch(SYNTH_LLM, return_value=SYNTHESIS), patch(EMBED, return_value=_vec(0)):
        r = client.post(
            f"{API}/sessions/{g['session_id']}/group-profile/commit",
            json={"provisional_group_profile_id": prof},
        )
    assert r.status_code == 404


def test_synthesis_failure_is_a_clean_502(client):
    g = _guest(client)
    prof = _describe(client, g, "Q1").json()["provisional_group_profile_id"]
    with patch(SYNTH_LLM, side_effect=RuntimeError("boom")):
        r = client.post(
            f"{API}/sessions/{g['session_id']}/group-profile/commit",
            json={"provisional_group_profile_id": prof},
        )
    assert r.status_code == 502


# ---- Recommendations and feedback ---------------------------------------------------


def _ready_session(client, db, n_questions=25):
    """A guest session with a committed profile and a bank of embedded questions."""
    for i in range(n_questions):
        db.add(
            QuestionItem(
                question_text=f"Question number {i}?",
                embedding=_vec(i),
                topics=[f"topic{i}"],
                content_categories=["life"],
            )
        )
    db.flush()
    g = _guest(client)
    prof = _describe(client, g, "Q1").json()["provisional_group_profile_id"]
    with patch(SYNTH_LLM, return_value=SYNTHESIS), patch(EMBED, return_value=_vec(3)):
        committed = client.post(
            f"{API}/sessions/{g['session_id']}/group-profile/commit",
            json={"provisional_group_profile_id": prof},
        ).json()
    exp = client.post(
        f"{API}/sessions/{g['session_id']}/experiences",
        json={"group_profile_id": committed["group_profile_id"]},
    )
    assert exp.status_code == 200, exp.text
    return g, exp.json()["experience_instance_id"], committed["group_profile_id"]


def test_cannot_start_an_experience_from_another_groups_profile(client, db):
    _, _, profile_id = _ready_session(client, db, n_questions=3)
    other = _guest(client)
    r = client.post(
        f"{API}/sessions/{other['session_id']}/experiences",
        json={"group_profile_id": profile_id},
    )
    assert r.status_code == 400


def test_a_batch_has_the_requested_size_and_never_repeats(client, db):
    g, exp, _ = _ready_session(client, db, n_questions=25)
    seen: list[str] = []
    for want, expect in ((10, 10), (10, 10), (10, 5)):
        r = client.post(f"{API}/experiences/{exp}/recommendations", json={"batch_size": want})
        items = r.json()["content_items"]
        assert len(items) == expect
        assert r.json()["exhausted"] is False
        seen += [i["text"] for i in items]
    assert len(set(seen)) == 25

    done = client.post(f"{API}/experiences/{exp}/more", json={}).json()
    assert done["content_items"] == [] and done["exhausted"] is True


def test_a_bigger_batch_is_really_bigger(client, db):
    g, exp, _ = _ready_session(client, db, n_questions=40)
    r = client.post(f"{API}/experiences/{exp}/recommendations", json={"batch_size": 20})
    assert len(r.json()["content_items"]) == 20


def test_batch_size_is_bounded(client, db):
    g, exp, _ = _ready_session(client, db, n_questions=3)
    for bad in (0, 31, -4):
        r = client.post(f"{API}/experiences/{exp}/recommendations", json={"batch_size": bad})
        assert r.status_code == 422


def _feedback(client, g, exp, item_id, value, participant=None):
    return client.post(
        f"{API}/content/{item_id}/feedback",
        json={
            "experience_instance_id": exp,
            "participant_id": participant or g["participant_id"],
            "feedback": value,
        },
    )


def test_changing_your_mind_replaces_the_rating(client, db):
    g, exp, _ = _ready_session(client, db)
    item = client.post(f"{API}/experiences/{exp}/recommendations", json={}).json()["content_items"][0]
    assert _feedback(client, g, exp, item["id"], "like").status_code == 200
    assert _feedback(client, g, exp, item["id"], "dislike").status_code == 200
    rows = db.query(UserQuestionFeedback).all()
    assert len(rows) == 1 and rows[0].feedback == "dislike"


def test_only_people_in_the_session_can_rate(client, db):
    g, exp, _ = _ready_session(client, db)
    item = client.post(f"{API}/experiences/{exp}/recommendations", json={}).json()["content_items"][0]
    stranger = _guest(client)
    r = _feedback(client, g, exp, item["id"], "like", participant=stranger["participant_id"])
    assert r.status_code == 403
    assert db.query(UserQuestionFeedback).count() == 0


def test_unknown_feedback_value_and_unshown_item_are_rejected(client, db):
    g, exp, _ = _ready_session(client, db)
    item = client.post(f"{API}/experiences/{exp}/recommendations", json={}).json()["content_items"][0]
    assert _feedback(client, g, exp, item["id"], "love").status_code == 400
    assert _feedback(client, g, exp, str(uuid.uuid4()), "like").status_code == 404


def test_disliked_questions_do_not_come_back(client, db):
    g, exp, _ = _ready_session(client, db, n_questions=12)
    first = client.post(f"{API}/experiences/{exp}/recommendations", json={}).json()["content_items"]
    _feedback(client, g, exp, first[0]["id"], "dislike")
    nxt = client.post(f"{API}/experiences/{exp}/more", json={}).json()["content_items"]
    assert first[0]["text"] not in [i["text"] for i in nxt]


# ---- Joining -----------------------------------------------------------------------------


def test_join_code_is_case_insensitive_and_name_is_required(client):
    g = _guest(client)
    assert g["join_code"] == g["join_code"].upper()
    ok = client.post(
        f"{API}/sessions/{g['session_id']}/join",
        json={"join_code": g["join_code"].lower() + " ", "display_name": "  Bea  ", "join_mode": "anonymous"},
    )
    assert ok.status_code == 200, ok.text
    blank = client.post(
        f"{API}/sessions/{g['session_id']}/join",
        json={"join_code": g["join_code"], "display_name": "   ", "join_mode": "anonymous"},
    )
    assert blank.status_code == 422
    view = client.get(f"{API}/sessions/{g['session_id']}").json()
    assert "Bea" in [p["display_name"] for p in view["participants"]]


def test_guest_sessions_use_the_family_friendly_policy_when_it_exists(client, db):
    from app.db.models.policy import PolicyProfile

    db.add(PolicyProfile(name="zzz-other", excluded_categories=[]))
    db.add(PolicyProfile(name="family_friendly", excluded_categories=["sexual"]))
    db.flush()
    g = _guest(client)
    view = client.get(f"{API}/sessions/{g['session_id']}").json()
    assert view["policy_profile"]["name"] == "family_friendly"
