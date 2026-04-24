"""Embedding client using OpenAI embeddings API."""

from __future__ import annotations

import logging
from typing import Any

import httpx
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


def embed_text(text: str) -> list[float]:
    """Embed a single text and return the vector."""
    client = _get_client()
    resp = client.embeddings.create(
        model=settings.EMBEDDINGS_MODEL,
        input=text,
    )
    return resp.data[0].embedding


def embed_texts(texts: list[str], batch_size: int = 100) -> list[list[float]]:
    """Embed multiple texts in batches."""
    client = _get_client()
    all_embeddings: list[list[float]] = []
    for i in range(0, len(texts), batch_size):
        batch = texts[i : i + batch_size]
        resp = client.embeddings.create(
            model=settings.EMBEDDINGS_MODEL,
            input=batch,
        )
        # Sort by index to maintain order
        sorted_data = sorted(resp.data, key=lambda x: x.index)
        all_embeddings.extend([d.embedding for d in sorted_data])
        logger.info("Embedded batch %d-%d of %d", i, i + len(batch), len(texts))
    return all_embeddings
