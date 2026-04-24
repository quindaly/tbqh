"""OpenAI-compatible LLM client with strict JSON output + retry."""

from __future__ import annotations

import json
import logging
from typing import Any

import httpx
import jsonschema
from openai import OpenAI

from app.core.config import settings

logger = logging.getLogger(__name__)

_client: OpenAI | None = None


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        kwargs: dict[str, Any] = {"api_key": settings.LLM_API_KEY}
        if settings.LLM_BASE_URL:
            kwargs["base_url"] = settings.LLM_BASE_URL
        if not settings.SSL_VERIFY:
            kwargs["http_client"] = httpx.Client(verify=False)
        _client = OpenAI(**kwargs)
    return _client


def call_llm_json(
    system_prompt: str,
    user_prompt: str,
    json_schema: dict[str, Any],
    *,
    max_retries: int = 2,
    temperature: float = 0.7,
) -> dict[str, Any]:
    """Call LLM and enforce strict JSON output validated against *json_schema*.

    If the response fails validation, retry up to *max_retries* times.
    """
    client = _get_client()

    for attempt in range(1 + max_retries):
        try:
            response = client.chat.completions.create(
                model=settings.LLM_MODEL,
                temperature=temperature,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                response_format={"type": "json_object"},
            )
            raw = response.choices[0].message.content or "{}"
            parsed = json.loads(raw)
            jsonschema.validate(instance=parsed, schema=json_schema)
            logger.info("LLM call succeeded on attempt %d", attempt + 1)
            return parsed
        except (json.JSONDecodeError, jsonschema.ValidationError) as exc:
            logger.warning(
                "LLM JSON validation failed (attempt %d/%d): %s",
                attempt + 1,
                1 + max_retries,
                exc,
            )
            if attempt == max_retries:
                raise
        except Exception:
            logger.exception("LLM call error on attempt %d", attempt + 1)
            if attempt == max_retries:
                raise

    # Should never reach here
    raise RuntimeError("LLM call exhausted retries")
