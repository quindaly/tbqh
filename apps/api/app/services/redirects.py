"""Where to send someone after they sign in."""

from __future__ import annotations

import re

MAX_NEXT_LEN = 1500
# A path on this site, with an optional query. No scheme, no host, no backslash:
# nothing that could send a signed-in person somewhere else.
_SAFE_PATH = re.compile(r"^/(?!/)[A-Za-z0-9._~!$&'()*+,;=:@%/?#\-]*$")


def clean_next(value: str | None) -> str | None:
    """Return ``value`` if it is a safe path on this site, otherwise None."""
    if not value or len(value) > MAX_NEXT_LEN:
        return None
    if not _SAFE_PATH.match(value):
        return None
    if "%2f%2f" in value.lower() or "%5c" in value.lower():
        return None
    return value
