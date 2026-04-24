"""Game catalog – lists available games."""

from __future__ import annotations

GAMES = [
    {
        "id": "who-knows-who",
        "slug": "who-knows-who",
        "display_name": "Who Knows Who",
        "description": "Answer questions about yourself, then guess which friend gave each answer.",
        "status": "active",
    },
]

_BY_SLUG = {g["slug"]: g for g in GAMES}


def list_games() -> list[dict]:
    return [g for g in GAMES if g["status"] == "active"]


def get_game(slug: str) -> dict | None:
    return _BY_SLUG.get(slug)
