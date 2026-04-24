"""Smoke tests for the main API flow."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client():
    return TestClient(app)


def test_health(client: TestClient):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_magic_link_request(client: TestClient):
    resp = client.post(
        "/api/v1/auth/magic-link",
        json={"email": "test@example.com"},
    )
    assert resp.status_code == 200
    assert resp.json()["ok"] is True


def test_auth_callback_invalid_token(client: TestClient):
    resp = client.get("/api/v1/auth/callback?token=invalid", follow_redirects=False)
    assert resp.status_code == 400


def test_me_unauthenticated(client: TestClient):
    resp = client.get("/api/v1/auth/me")
    assert resp.status_code == 401


def test_create_group_unauthenticated(client: TestClient):
    resp = client.post("/api/v1/groups", json={"name": "Test Group"})
    assert resp.status_code == 401


def test_list_policies(client: TestClient):
    resp = client.get("/api/v1/policies")
    assert resp.status_code == 200
    data = resp.json()
    assert "policies" in data


def test_full_flow_smoke(client: TestClient):
    """Test the basic authenticated flow: login → create group → create session → get session."""
    from app.core.security import create_session_token, create_magic_link_token
    from app.core.config import settings

    # 1. Request magic link
    resp = client.post(
        "/api/v1/auth/magic-link",
        json={"email": "smoketest@example.com"},
    )
    assert resp.status_code == 200

    # 2. Use magic link callback to sign in
    token = create_magic_link_token("smoketest@example.com")
    resp = client.get(
        f"/api/v1/auth/callback?token={token}",
        follow_redirects=False,
    )
    assert resp.status_code in (302, 307)
    # Extract session cookie
    session_cookie = resp.cookies.get(settings.SESSION_COOKIE_NAME)
    assert session_cookie is not None

    # 3. Get me
    resp = client.get(
        "/api/v1/auth/me",
        cookies={settings.SESSION_COOKIE_NAME: session_cookie},
    )
    assert resp.status_code == 200
    user = resp.json()
    assert user["email"] == "smoketest@example.com"

    # 4. Create group
    resp = client.post(
        "/api/v1/groups",
        json={"name": "Smoke Test Group"},
        cookies={settings.SESSION_COOKIE_NAME: session_cookie},
    )
    assert resp.status_code == 200
    group_data = resp.json()
    group_id = group_data["group_id"]
    host_participant_id = group_data["host_participant_id"]

    # 5. Get policies and create session
    resp = client.get("/api/v1/policies")
    policies = resp.json()["policies"]
    assert len(policies) > 0
    policy_id = policies[0]["id"]

    resp = client.post(
        "/api/v1/sessions",
        json={"group_id": group_id, "policy_profile_id": policy_id},
        cookies={settings.SESSION_COOKIE_NAME: session_cookie},
    )
    assert resp.status_code == 200
    session_data = resp.json()
    session_id = session_data["session_id"]
    join_code = session_data["join_code"]

    # 6. Get session details
    resp = client.get(f"/api/v1/sessions/{session_id}")
    assert resp.status_code == 200
    sess = resp.json()
    assert sess["status"] == "active"
    assert len(sess["participants"]) >= 1

    # 7. Join as guest
    resp = client.post(
        f"/api/v1/sessions/{session_id}/join",
        json={
            "join_code": join_code,
            "display_name": "Guest Player",
            "join_mode": "anonymous",
        },
    )
    assert resp.status_code == 200
    guest = resp.json()
    assert guest["session_id"] == session_id
