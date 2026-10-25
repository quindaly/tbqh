"""Helpers for the "Other (type your own)" choice on follow-up questions."""

from __future__ import annotations

import re

OTHER_OPTION = "Other (type your own)"

# Matches "Other", "other", "Other (type your own)", "Other (please specify)".
# Deliberately does NOT match "Together", "Mother's side" or "Other people's stories".
_OTHER_RE = re.compile(r"other(\s*\(.*\))?", re.IGNORECASE)


def is_other_option(option: str | None) -> bool:
    return bool(option) and _OTHER_RE.fullmatch(option.strip()) is not None


def normalize_options(options: list[str]) -> list[str]:
    """Trim, drop blanks and duplicates, and make "Other (type your own)" the last option."""
    seen: set[str] = set()
    cleaned: list[str] = []
    for raw in options:
        opt = str(raw).strip()
        if not opt or is_other_option(opt) or opt.lower() in seen:
            continue
        seen.add(opt.lower())
        cleaned.append(opt)
    cleaned.append(OTHER_OPTION)
    return cleaned
