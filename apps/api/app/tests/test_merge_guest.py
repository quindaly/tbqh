"""Signing in from a browser that was working as a guest brings that work along."""

import uuid
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.core.security import create_magic_link_token
from app.db.models.feedback import UserQuestionFeedback
from app.db.models.group import Group
from app.db.models.participant import Participant
from app.db.models.user import User
from app.db.session import get_db
from app.main import app
from app.services import accounts
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


def sign_in(client, email):
    r = client.get(
        f"{API}/auth/callback?token={create_magic_link_token(email)}", follow_redirects=False
    )
    assert r.status_code == 302
    return client.get(f"{API}/auth/me").json()


class TestSignInBringsTheGuestSessionAlong:
    def test_the_session_and_the_seat_in_it_belong_to_the_account(self, client, db):
        g = _guest(client)
        me = sign_in(client, "merge@example.com")
        assert me["id"] != g["user_id"]
        assert db.get(Group, uuid.UUID(g["group_id"])).created_by_user_id == uuid.UUID(me["id"])
        seat = db.get(Participant, uuid.UUID(g["participant_id"]))
        assert seat.user_id == uuid.UUID(me["id"]) and seat.join_type == "authenticated"
        assert db.query(Group).filter(Group.created_by_user_id == uuid.UUID(g["user_id"])).count() == 0

    def test_rating_afterwards_uses_the_same_seat_and_keeps_earlier_skips(self, client, db):
        g, exp, _ = _ready_session(client, db, n_questions=12)
        items = client.post(f"{API}/experiences/{exp}/recommendations", json={}).json()["content_items"]
        assert _feedback(client, g, exp, items[0]["id"], "skip").status_code == 200
        _sign_in(client, "merge@example.com")
        r = _feedback(client, g, exp, items[1]["id"], "like")
        assert r.status_code == 200
        assert r.json()["participant_id"] == g["participant_id"]  # no second seat
        shown = client.get(
            f"{API}/experiences/{exp}/items", params={"participant_id": g["participant_id"]}
        ).json()["content_items"]
        assert [i["feedback"] for i in shown[:2]] == ["skip", "like"]
        user = db.query(User).filter(User.email == "merge@example.com").one()
        assert {f.user_id for f in db.query(UserQuestionFeedback).all()} == {user.id}

    def test_a_guest_seat_takes_the_accounts_name(self, client, db):
        g = _guest(client)
        sign_in(client, "named@example.com")
        client.patch(f"{API}/auth/me", json={"name": "Nova"})
        assert db.get(Participant, uuid.UUID(g["participant_id"])).display_name == "Nova"

    def test_an_account_that_already_has_a_name_uses_it_straight_away(self, client, db):
        sign_in(client, "named@example.com")
        client.patch(f"{API}/auth/me", json={"name": "Nova"})
        client.post(f"{API}/auth/logout")
        g = _guest(client)
        assert db.get(Participant, uuid.UUID(g["participant_id"])).display_name == "Guest"
        sign_in(client, "named@example.com")
        assert db.get(Participant, uuid.UUID(g["participant_id"])).display_name == "Nova"

    def test_names_people_chose_for_themselves_are_left_alone(self, client, db):
        g = _guest(client)
        joiner = client.post(
            f"{API}/sessions/{g['session_id']}/join",
            json={"join_code": g["join_code"], "display_name": "Sam", "join_mode": "authenticated"},
        ).json()
        sign_in(client, "named@example.com")
        client.patch(f"{API}/auth/me", json={"name": "Nova"})
        assert db.get(Participant, uuid.UUID(joiner["participant_id"])).display_name == "Sam"

    def test_an_existing_account_gains_the_guest_session_too(self, client, db):
        sign_in(client, "again@example.com")
        mine = client.get(f"{API}/auth/me").json()["id"]
        client.post(f"{API}/auth/logout")
        g = _guest(client)
        me = sign_in(client, "again@example.com")
        assert me["id"] == mine
        assert db.get(Group, uuid.UUID(g["group_id"])).created_by_user_id == uuid.UUID(mine)


class TestOnlyTheGuestsOwnBrowserBringsItAlong:
    def test_a_link_opened_in_another_browser_leaves_the_guest_session_alone(self, client, db):
        g = _guest(client)
        client.cookies.clear()  # the email opens somewhere with no guest cookie
        sign_in(client, "elsewhere@example.com")
        assert db.get(Group, uuid.UUID(g["group_id"])).created_by_user_id == uuid.UUID(g["user_id"])

    def test_signing_in_to_a_second_account_does_not_move_the_first_ones_things(self, client, db):
        first = sign_in(client, "first@example.com")
        g = _guest(client)  # signed in, so this keeps the first account (no throwaway)
        assert g["user_id"] == first["id"]
        second = sign_in(client, "second@example.com")
        assert second["id"] != first["id"]
        assert db.get(Group, uuid.UUID(g["group_id"])).created_by_user_id == uuid.UUID(first["id"])

    def test_signing_in_does_not_depend_on_the_merge_working(self, client, db):
        g = _guest(client)
        with patch("app.api.v1.routes.auth.merge_guest_into_user", side_effect=RuntimeError("boom")):
            me = sign_in(client, "resilient@example.com")
        assert me["email"] == "resilient@example.com"
        # nothing was half-moved
        assert db.get(Group, uuid.UUID(g["group_id"])).created_by_user_id == uuid.UUID(g["user_id"])


class TestMergeGuardrails:
    def test_two_real_accounts_are_never_merged(self, db):
        a, b = User(email="a@example.com"), User(email="b@example.com")
        db.add_all([a, b])
        db.flush()
        g = Group(created_by_user_id=a.id, name="a's")
        db.add(g)
        db.flush()
        assert accounts.merge_guest_into_user(db, a, b) == {"groups": 0, "participants": 0, "feedback": 0}
        assert g.created_by_user_id == a.id

    def test_a_guest_is_never_the_destination(self, db):
        a, b = User(email="guest-1@guest.local"), User(email="guest-2@guest.local")
        db.add_all([a, b])
        db.flush()
        assert accounts.merge_guest_into_user(db, a, b)["groups"] == 0

    def test_merging_an_account_into_itself_does_nothing(self, db):
        a = User(email="guest-1@guest.local")
        db.add(a)
        db.flush()
        assert accounts.merge_guest_into_user(db, a, a)["participants"] == 0

    def test_anonymous_game_hosts_count_as_stand_in_accounts(self, db):
        host = User(email="anon-ab12@game.local")
        real = User(email="real@example.com")
        db.add_all([host, real])
        db.flush()
        g = Group(created_by_user_id=host.id, name="game")
        db.add(g)
        db.flush()
        assert accounts.merge_guest_into_user(db, host, real)["groups"] == 1
        assert g.created_by_user_id == real.id
