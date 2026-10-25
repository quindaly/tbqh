"""Game catalog – lists available games."""

from __future__ import annotations

GAMES = [
    {
        "id": "who-knows-who",
        "slug": "who-knows-who",
        "display_name": "Who Knows Who",
        "description": "Answer questions about yourself, then guess which friend gave each answer.",
        "min_players": 3,
        "max_players": 20,
        "status": "active",
    },
    {
        "id": "how-well-do-you-know",
        "slug": "the-hot-seat",
        "display_name": "The Hot Seat",
        "description": "One person answers personal questions. Everyone else guesses the correct answer from multiple choices.",
        "min_players": 3,
        "max_players": 20,
        "modes": ["default", "party"],
        "status": "active",
    },
]

_BY_SLUG = {g["slug"]: g for g in GAMES}
# The Hot Seat used to live at /games/how-well-do-you-know. Old links and
# older cached pages still send that name, so it keeps resolving.
_ALIASES = {"how-well-do-you-know": "the-hot-seat"}


def list_games() -> list[dict]:
    return [g for g in GAMES if g["status"] == "active"]


def get_game(slug: str) -> dict | None:
    return _BY_SLUG.get(_ALIASES.get(slug, slug))
