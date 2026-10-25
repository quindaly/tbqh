"""Sign in: email handling, the magic-link round trip, cookies, throttling."""

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError

from app.core.config import settings
from app.core.security import create_magic_link_token
from app.db.models.user import User
from app.db.session import get_db
from app.main import app
from app.services import accounts, email as mailer
from app.services.throttle import Throttle, sign_in_throttle


@pytest.fixture()
def client(db):
    app.dependency_overrides[get_db] = lambda: db
    sign_in_throttle.clear()
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.pop(get_db, None)
    sign_in_throttle.clear()


def sign_in(client, email):
    token = create_magic_link_token(email)
    return client.get(f"/api/v1/auth/callback?token={token}", follow_redirects=False)


class TestEmailsAreStoredOnce:
    def test_normalize(self):
        assert accounts.normalize_email("  Quin.Daly35@Gmail.COM ") == "quin.daly35@gmail.com"

    def test_any_spelling_is_the_same_account(self, client, db):
        first = sign_in(client, "Quin.Daly35@gmail.com")
        second = sign_in(client, "quin.daly35@GMAIL.com")
        assert first.status_code == second.status_code == 302
        rows = db.query(User).filter(User.email.ilike("quin.daly35@gmail.com")).all()
        assert len(rows) == 1
        assert rows[0].email == "quin.daly35@gmail.com"

    def test_an_older_mixed_case_row_is_still_found(self, client, db):
        db.add(User(email="Maya@Example.com"))
        db.flush()
        sign_in(client, "maya@example.com")
        assert db.query(User).filter(User.email.ilike("maya@example.com")).count() == 1

    def test_two_sign_ins_racing_for_a_new_address_use_one_user(self):
        winner = User(email="new@example.com")
        db = MagicMock()
        db.commit.side_effect = IntegrityError("insert", {}, Exception("duplicate"))
        with patch.object(accounts, "find_user_by_email", side_effect=[None, winner]):
            assert accounts.get_or_create_user(db, "New@example.com") is winner
        db.rollback.assert_called_once()

    def test_placeholder_addresses(self):
        assert accounts.is_placeholder_email("guest-ab12@guest.local")
        assert accounts.is_placeholder_email("ANON-ab12@game.local")
        assert not accounts.is_placeholder_email("quin@gmail.com")


class TestRoundTrip:
    def test_callback_sets_the_cookie_and_me_works(self, client):
        resp = sign_in(client, "friend@example.com")
        assert resp.status_code == 302
        assert resp.headers["location"].endswith("/dashboard")
        assert f"{settings.SESSION_COOKIE_NAME}=" in resp.headers["set-cookie"]
        assert "HttpOnly" in resp.headers["set-cookie"]
        me = client.get("/api/v1/auth/me").json()
        assert me["email"] == "friend@example.com"
        assert me["is_guest"] is False

    def test_guest_is_flagged(self, client):
        client.post("/api/v1/auth/guest")
        me = client.get("/api/v1/auth/me").json()
        assert me["is_guest"] is True

    def test_cookie_name_comes_from_settings(self, client, monkeypatch):
        monkeypatch.setattr(settings, "SESSION_COOKIE_NAME", "tbqh_session")
        sign_in(client, "named@example.com")
        assert "tbqh_session" in client.cookies
        assert client.get("/api/v1/auth/me").status_code == 200

    def test_logout_clears_the_cookie(self, client):
        sign_in(client, "bye@example.com")
        client.post("/api/v1/auth/logout")
        assert client.get("/api/v1/auth/me").status_code == 401

    def test_expired_or_bad_link_goes_to_the_login_page(self, client):
        resp = client.get("/api/v1/auth/callback?token=nope", follow_redirects=False)
        assert resp.status_code == 302
        assert resp.headers["location"] == f"{settings.WEB_BASE_URL}/login?error=expired"

    def test_requesting_a_link_emails_it(self, client):
        with patch("app.api.v1.routes.auth.send_magic_link", return_value=True) as send:
            r = client.post("/api/v1/auth/magic-link", json={"email": " Quin@Gmail.com "})
        assert r.status_code == 200
        to, link = send.call_args.args
        assert to == "quin@gmail.com"
        assert "/api/v1/auth/callback?token=" in link

    def test_a_failed_send_is_reported_not_hidden(self, client):
        with patch("app.api.v1.routes.auth.send_magic_link", return_value=False):
            r = client.post("/api/v1/auth/magic-link", json={"email": "a@example.com"})
        assert r.status_code == 503
        assert "couldn't send" in r.json()["detail"]

    def test_garbage_email_is_rejected(self, client):
        assert client.post("/api/v1/auth/magic-link", json={"email": "nope"}).status_code == 422


class TestThrottle:
    def test_sliding_window(self):
        t = Throttle()
        assert all(t.allow("k", 3, 10, now=n) for n in (0, 1, 2))
        assert not t.allow("k", 3, 10, now=3)
        assert t.allow("k", 3, 10, now=11)  # the first hit has aged out
        assert t.allow("other", 3, 10, now=3)

    def test_too_many_requests_for_one_address(self, client):
        with patch("app.api.v1.routes.auth.send_magic_link", return_value=True):
            codes = [
                client.post("/api/v1/auth/magic-link", json={"email": "spam@example.com"}).status_code
                for _ in range(7)
            ]
        assert codes[:5] == [200] * 5
        assert codes[5:] == [429, 429]


class TestEmailProviders:
    LINK = "https://api.tbqh.app/api/v1/auth/callback?token=abc"

    def test_message_has_link_and_no_em_dash(self):
        subject, text, html = mailer.magic_link_message(self.LINK)
        assert self.LINK in text and self.LINK in html
        assert "—" not in subject + text + html

    def test_resend_sends_the_expected_request(self, monkeypatch):
        monkeypatch.setattr(settings, "EMAIL_PROVIDER", "resend")
        monkeypatch.setattr(settings, "RESEND_API_KEY", "re_test")
        monkeypatch.setattr(settings, "EMAIL_FROM", "tbqh <login@tbqh.app>")
        with patch.object(mailer.httpx, "post", return_value=MagicMock(status_code=200)) as post:
            assert mailer.send_magic_link("q@example.com", self.LINK) is True
        args, kwargs = post.call_args
        assert args[0] == "https://api.resend.com/emails"
        assert kwargs["headers"]["Authorization"] == "Bearer re_test"
        assert kwargs["json"]["to"] == ["q@example.com"]
        assert kwargs["json"]["from"] == "tbqh <login@tbqh.app>"
        assert self.LINK in kwargs["json"]["text"]

    def test_resend_rejection_is_a_failure_and_never_logs_the_link(self, monkeypatch, caplog):
        monkeypatch.setattr(settings, "EMAIL_PROVIDER", "resend")
        monkeypatch.setattr(settings, "RESEND_API_KEY", "re_test")
        bad = MagicMock(status_code=403, text="domain not verified")
        with patch.object(mailer.httpx, "post", return_value=bad):
            assert mailer.send_magic_link("q@example.com", self.LINK) is False
        assert "token=abc" not in caplog.text

    def test_resend_without_a_key_fails(self, monkeypatch):
        monkeypatch.setattr(settings, "EMAIL_PROVIDER", "resend")
        monkeypatch.setattr(settings, "RESEND_API_KEY", "")
        assert mailer.send_magic_link("q@example.com", self.LINK) is False

    def test_network_errors_are_a_failure_not_a_crash(self, monkeypatch):
        monkeypatch.setattr(settings, "EMAIL_PROVIDER", "resend")
        monkeypatch.setattr(settings, "RESEND_API_KEY", "re_test")
        with patch.object(mailer.httpx, "post", side_effect=OSError("down")):
            assert mailer.send_magic_link("q@example.com", self.LINK) is False

    def test_smtp(self, monkeypatch):
        monkeypatch.setattr(settings, "EMAIL_PROVIDER", "smtp")
        monkeypatch.setattr(settings, "SMTP_HOST", "smtp.example.com")
        monkeypatch.setattr(settings, "SMTP_USER", "u")
        monkeypatch.setattr(settings, "SMTP_PASSWORD", "p")
        with patch.object(mailer.smtplib, "SMTP") as smtp_cls:
            smtp = smtp_cls.return_value.__enter__.return_value
            assert mailer.send_magic_link("q@example.com", self.LINK) is True
        smtp.starttls.assert_called_once()
        smtp.login.assert_called_once_with("u", "p")
        sent = smtp.send_message.call_args.args[0]
        assert sent["To"] == "q@example.com"

    def test_console_in_production_warns_that_nothing_was_emailed(self, monkeypatch, caplog):
        monkeypatch.setattr(settings, "EMAIL_PROVIDER", "console")
        monkeypatch.setattr(settings, "API_BASE_URL", "https://api.tbqh.app")
        with caplog.at_level("WARNING"):
            assert mailer.send_magic_link("q@example.com", self.LINK) is True
        assert "NOT sent" in caplog.text

    def test_unknown_provider_fails(self, monkeypatch):
        monkeypatch.setattr(settings, "EMAIL_PROVIDER", "carrier-pigeon")
        assert mailer.send_magic_link("q@example.com", self.LINK) is False
