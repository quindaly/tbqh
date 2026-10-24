"""Malformed IDs in game URLs must produce a clean 404, never an unhandled 500.

An unhandled error is returned without CORS headers, so the browser reports it
as a network failure and the lobby page cannot tell the player what went wrong.
These tests never touch the database: the ID is parsed before any query runs.
"""

import uuid

import pytest
from fastapi import HTTPException

from app.api.v1.routes import games
from app.services.games.sharing import generate_share_url

BAD_IDS = ["test", "", "123", "not-a-uuid", "7e50d9f2-d825-4d5a-bd89"]


@pytest.mark.parametrize("bad_id", BAD_IDS)
def test_uuid_or_404_rejects_malformed_ids(bad_id):
    with pytest.raises(HTTPException) as exc:
        games._uuid_or_404(bad_id)
    assert exc.value.status_code == 404


def test_uuid_or_404_accepts_valid_id():
    value = uuid.uuid4()
    assert games._uuid_or_404(str(value)) == value


@pytest.mark.parametrize(
    "lookup",
    [games._get_experience, games._get_hwdyk_experience, games._get_any_experience],
)
@pytest.mark.parametrize("bad_id", BAD_IDS)
def test_experience_lookups_404_before_touching_the_db(lookup, bad_id):
    # db=None proves the ID is validated first: any query would raise
    # AttributeError instead of the expected HTTPException.
    with pytest.raises(HTTPException) as exc:
        lookup(None, bad_id)
    assert exc.value.status_code == 404
    assert exc.value.detail == "Experience not found"


def test_who_knows_who_share_url_points_at_join_page():
    url = generate_share_url(uuid.uuid4(), "ABC123")
    assert "/games/who-knows-who?code=ABC123" in url
    assert "/lobby" not in url
