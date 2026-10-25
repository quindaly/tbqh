"""People type join codes in any case and paste them with spaces."""

import pytest
from fastapi.testclient import TestClient

from app.db.session import get_db
from app.main import app
from app.services.join_codes import normalize_join_code

API = "/api/v1"


@pytest.fixture()
def client(db):
    app.dependency_overrides[get_db] = lambda: db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.pop(get_db, None)


def test_normalize():
    assert normalize_join_code(" d7f ba6\n") == "D7FBA6"
    assert normalize_join_code("286 094") == "286094"


@pytest.mark.parametrize("mangle", [str.lower, lambda c: f"  {c} ", lambda c: c[:3] + " " + c[3:]])
def test_who_knows_who_join_tolerates_typing(client, mangle):
    created = client.post(f"{API}/games/who-knows-who/create", json={"display_name": "Host"}).json()
    r = client.post(
        f"{API}/games/who-knows-who/join",
        json={"join_code": mangle(created["join_code"]), "display_name": "Bea"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["experience_instance_id"] == created["experience_instance_id"]


@pytest.mark.parametrize("mangle", [str.lower, lambda c: f"  {c} ", lambda c: c[:3] + " " + c[3:]])
def test_hot_seat_join_tolerates_typing(client, mangle):
    created = client.post(
        f"{API}/games/how-well-do-you-know/create", json={"display_name": "Host"}
    ).json()
    r = client.post(
        f"{API}/games/how-well-do-you-know/join",
        json={"join_code": mangle(created["join_code"]), "display_name": "Bea"},
    )
    assert r.status_code == 200, r.text


def test_wrong_code_is_still_a_clean_404(client):
    r = client.post(f"{API}/games/who-knows-who/join", json={"join_code": "ZZZZZZ", "display_name": "Bea"})
    assert r.status_code == 404
