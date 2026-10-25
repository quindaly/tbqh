"""Display-name rules shared by the games."""

from __future__ import annotations

from fastapi import HTTPException, status

MAX_NAME_LEN = 40


def clean_display_name(raw: str | None) -> str:
    """Trim and tidy a name; reject empty or very long ones."""
    name = " ".join((raw or "").split())
    if not name:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Enter your name.",
        )
    if len(name) > MAX_NAME_LEN:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Names can be up to {MAX_NAME_LEN} characters.",
        )
    return name


def ensure_name_free(name: str, existing: list[str]) -> None:
    """Two players with the same name make a guessing game unplayable."""
    taken = {n.casefold() for n in existing}
    if name.casefold() in taken:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Someone in this game already has that name. Try another.",
        )
