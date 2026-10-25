"""Signing in: where you land, your name, and feedback needing an account."""

import uuid
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.core.security import create_magic_link_token, verify_magic_link_token
from app.db.models.feedback import UserQuestionFeedback
from app.db.models.participant import Participant
from app.db.models.user import User
from app.db.session import get_db
from app.main import app
from app.services.redirects import clean_next
from app.tests.test_discussion_questions import (
    API,
    _feedback,
    _guest,
    _ready_session,
    _sign_in,
)


@pytest.fixture()
def client(db):
    app.dependency_overrides[get_db] = lambda: db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.pop(get_db, None)


def click(client, token):
    return client.get(f"{API}/auth/callback?token={token}", follow_redirects=False)


class TestWhereYouLand:
    def test_signing_in_from_the_sign_in_link_goes_to_the_home_page(self, client):
        r = click(client, create_magic_link_token("a@example.com"))
        assert r.headers["location"] == f"{settings.WEB_BASE_URL}/"

    def test_signing_in_mid_game_returns_to_that_page(self, client):
        path = "/session/abc/questions?r=eyJwIjoxfQ"
        r = click(client, create_magic_link_token("a@example.com", path))
        assert r.headers["location"] == f"{settings.WEB_BASE_URL}{path}"

    def test_the_path_travels_inside_the_signed_link(self, client):
        with patch("app.api.v1.routes.auth.send_magic_link", return_value=True) as send:
            client.post(f"{API}/auth/magic-link", json={"email": "a@example.com", "next": "/session/1/questions"})
        link = send.call_args.args[1]
        token = link.split("token=")[1]
        assert verify_magic_link_token(token) == ("a@example.com", verify_magic_link_token(token)[1], "/session/1/questions")

    @pytest.mark.parametrize(
        "bad",
        [
            "https://evil.example/x",
            "//evil.example/x",
            "/\\evil.example",
            "javascript:alert(1)",
            "/ok/%2F%2Fevil.example",
            "/with space",
            "x" * 2000,
            "relative/path",
            "",
        ],
    )
    def test_unsafe_destinations_are_dropped(self, bad):
        assert clean_next(bad) is None

    def test_a_forged_destination_still_lands_on_the_home_page(self, client):
        r = click(client, create_magic_link_token("a@example.com", "https://evil.example"))
        assert r.headers["location"] == f"{settings.WEB_BASE_URL}/"

    def test_a_link_to_the_game_in_progress_is_accepted(self):
        assert clean_next("/session/6f0c/questions") == "/session/6f0c/questions"
        assert clean_next("/games/the-hot-seat?code=ABC123") == "/games/the-hot-seat?code=ABC123"


class TestName:
    def test_a_new_account_is_asked_for_a_name(self, client):
        click(client, create_magic_link_token("new@example.com"))
        me = client.get(f"{API}/auth/me").json()
        assert me["name"] is None and me["needs_name"] is True

    def test_giving_a_name_is_remembered(self, client):
        click(client, create_magic_link_token("new@example.com"))
        r = client.patch(f"{API}/auth/me", json={"name": "  Quin   Daly "})
        assert r.status_code == 200 and r.json()["name"] == "Quin Daly"
        me = client.get(f"{API}/auth/me").json()
        assert me["name"] == "Quin Daly" and me["needs_name"] is False

    def test_skipping_stops_the_asking_and_leaves_no_name(self, client):
        click(client, create_magic_link_token("new@example.com"))
        assert client.patch(f"{API}/auth/me", json={"skip": True}).status_code == 200
        me = client.get(f"{API}/auth/me").json()
        assert me["name"] is None and me["needs_name"] is False
        # signing in again does not ask again
        click(client, create_magic_link_token("new@example.com"))
        assert client.get(f"{API}/auth/me").json()["needs_name"] is False

    def test_a_named_account_is_not_asked_again(self, client):
        click(client, create_magic_link_token("new@example.com"))
        client.patch(f"{API}/auth/me", json={"name": "Quin"})
        click(client, create_magic_link_token("new@example.com"))
        me = client.get(f"{API}/auth/me").json()
        assert me["name"] == "Quin" and me["needs_name"] is False

    def test_nothing_to_save_is_an_error(self, client):
        click(client, create_magic_link_token("new@example.com"))
        assert client.patch(f"{API}/auth/me", json={}).status_code == 422
        assert client.patch(f"{API}/auth/me", json={"name": "   "}).status_code == 422

    def test_a_very_long_name_is_rejected(self, client):
        click(client, create_magic_link_token("new@example.com"))
        assert client.patch(f"{API}/auth/me", json={"name": "x" * 41}).status_code == 422

    def test_guests_are_never_asked_and_cannot_set_one(self, client):
        _guest(client)
        me = client.get(f"{API}/auth/me").json()
        assert me["is_guest"] is True and me["needs_name"] is False
        assert client.patch(f"{API}/auth/me", json={"name": "Sneaky"}).status_code == 403

    def test_signed_out_cannot_set_a_name(self, client):
        assert client.patch(f"{API}/auth/me", json={"name": "Quin"}).status_code == 401


class TestGuestSessionKeepsYourLogin:
    def test_starting_a_session_while_signed_in_does_not_swap_the_login(self, client, db):
        click(client, create_magic_link_token("keeper@example.com"))
        client.patch(f"{API}/auth/me", json={"name": "Keeper"})
        before = client.get(f"{API}/auth/me").json()["id"]
        g = _guest(client)
        after = client.get(f"{API}/auth/me").json()
        assert after["id"] == before and after["is_guest"] is False
        assert g["user_id"] == before
        host = db.get(Participant, uuid.UUID(g["participant_id"]))
        assert host.user_id == uuid.UUID(before)
        assert host.display_name == "Keeper" and host.join_type == "authenticated"

    def test_a_signed_out_visitor_still_gets_a_throwaway_account(self, client):
        g = _guest(client)
        me = client.get(f"{API}/auth/me").json()
        assert me["is_guest"] is True and me["id"] == g["user_id"]


class TestFeedbackNeedsAnAccount:
    def item(self, client, exp):
        return client.post(f"{API}/experiences/{exp}/recommendations", json={}).json()["content_items"][0]

    def test_a_guest_cannot_love_or_block(self, client, db):
        g, exp, _ = _ready_session(client, db)
        item = self.item(client, exp)
        for value in ("like", "dislike"):
            r = _feedback(client, g, exp, item["id"], value)
            assert r.status_code == 401 and r.json()["detail"] == "Sign in to leave feedback."
        assert db.query(UserQuestionFeedback).count() == 0

    def test_nobody_signed_in_cannot_either(self, client, db):
        g, exp, _ = _ready_session(client, db)
        item = self.item(client, exp)
        client.post(f"{API}/auth/logout")
        assert _feedback(client, g, exp, item["id"], "like").status_code == 401

    def test_a_guest_can_still_skip(self, client, db):
        g, exp, _ = _ready_session(client, db)
        item = self.item(client, exp)
        assert _feedback(client, g, exp, item["id"], "skip").status_code == 200

    def test_signing_in_mid_session_lets_the_same_person_rate(self, client, db):
        g, exp, _ = _ready_session(client, db)
        item = self.item(client, exp)
        assert _feedback(client, g, exp, item["id"], "like").status_code == 401
        _sign_in(client, "back@example.com")
        r = _feedback(client, g, exp, item["id"], "like")
        assert r.status_code == 200, r.text
        row = db.query(UserQuestionFeedback).one()
        user = db.query(User).filter(User.email == "back@example.com").one()
        assert row.user_id == user.id and row.feedback == "like"
        # the account speaks through its own participant, which keeps the name used before
        mine = db.get(Participant, uuid.UUID(r.json()["participant_id"]))
        assert mine.user_id == user.id
        assert mine.display_name == db.get(Participant, uuid.UUID(g["participant_id"])).display_name

    def test_it_is_the_same_participant_every_time(self, client, db):
        g, exp, _ = _ready_session(client, db, n_questions=12)
        _sign_in(client)
        items = client.post(f"{API}/experiences/{exp}/recommendations", json={}).json()["content_items"]
        ids = {_feedback(client, g, exp, i["id"], "like").json()["participant_id"] for i in items[:3]}
        assert len(ids) == 1

    def test_someone_else_signed_in_cannot_use_a_real_accounts_participant(self, client, db):
        g, exp, _ = _ready_session(client, db)
        item = self.item(client, exp)
        _sign_in(client, "owner@example.com")
        mine = _feedback(client, g, exp, item["id"], "like").json()["participant_id"]
        client.post(f"{API}/auth/logout")
        _sign_in(client, "intruder@example.com")
        r = _feedback(client, g, exp, item["id"], "dislike", participant=mine)
        assert r.status_code == 403
        assert db.query(UserQuestionFeedback).one().feedback == "like"

    def test_name_is_used_for_the_accounts_place_in_the_session(self, client, db):
        g, exp, _ = _ready_session(client, db)
        item = self.item(client, exp)
        _sign_in(client, "named@example.com")
        client.patch(f"{API}/auth/me", json={"name": "Nova"})
        r = _feedback(client, g, exp, item["id"], "like")
        assert db.get(Participant, uuid.UUID(r.json()["participant_id"])).display_name == "Nova"
