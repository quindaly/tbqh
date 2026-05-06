"""JSON schema loaders for LLM strict output validation."""

from __future__ import annotations

import json
from pathlib import Path
from functools import lru_cache


# In Docker container, schemas are at /schemas
# Locally, they're at the workspace root (variable depth)
def _build_schema_dirs() -> list[Path]:
    dirs = [Path("/schemas")]
    p = Path(__file__).resolve()
    for i in range(len(p.parents)):
        candidate = p.parents[i] / "schemas"
        if candidate.is_dir():
            dirs.append(candidate)
    return dirs


_SCHEMA_DIRS = _build_schema_dirs()


@lru_cache(maxsize=16)
def _load(filename: str) -> dict:
    for d in _SCHEMA_DIRS:
        path = d / filename
        if path.exists():
            with open(path) as f:
                return json.load(f)
    raise FileNotFoundError(f"Schema {filename} not found in {_SCHEMA_DIRS}")


def intake_extraction_schema() -> dict:
    return _load("intake_extraction_output.json")


def followup_generation_schema() -> dict:
    return _load("follow_up_generation_output.json")


def group_profile_synthesis_schema() -> dict:
    return _load("group_profile_synthesis_outupt.json")


def constrained_rewording_schema() -> dict:
    return _load("constrained_rewording_output.json")


def offline_question_labeling_schema() -> dict:
    return _load("offline_question_labeling.json")


def distractor_generation_schema() -> dict:
    return _load("distractor_generation_output.json")
