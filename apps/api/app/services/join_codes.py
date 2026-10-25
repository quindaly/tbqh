"""Join codes for sessions: short, easy to read out loud, case-insensitive."""

from __future__ import annotations

import secrets

# No 0/O or 1/I/L, so a code read across a room is hard to get wrong.
_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"


def new_join_code(length: int = 6) -> str:
    return "".join(secrets.choice(_ALPHABET) for _ in range(length))


def normalize_join_code(code: str) -> str:
    """What people actually type: any case, with stray or pasted spaces."""
    return "".join(code.split()).upper()
