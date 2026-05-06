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
    {
        "id": "how-well-do-you-know",
        "slug": "how-well-do-you-know",
        "display_name": "How Well Do You Know [Person]?",
        "description": "One person answers personal questions. Everyone else guesses the correct answer from multiple choices.",
        "min_players": 3,
        "max_players": 20,
        "modes": ["default", "party"],
        "status": "active",
    },
]

_BY_SLUG = {g["slug"]: g for g in GAMES}


def list_games() -> list[dict]:
    return [g for g in GAMES if g["status"] == "active"]


def get_game(slug: str) -> dict | None:
    return _BY_SLUG.get(slug)
