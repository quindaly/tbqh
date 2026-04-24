#!/usr/bin/env python3
"""Compute and store embeddings for all question_items that lack one.

Usage:
    python scripts/embed_questions.py [--batch-size 100]

Requires LLM_API_KEY env var (or it will use settings).
"""

from __future__ import annotations

import argparse
import os
import sys

# Add the api app to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "apps", "api"))

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

DATABASE_URL = os.environ.get(
    "DATABASE_URL", "postgresql+psycopg://app:app@localhost:5432/app"
)

DEPTH_LABELS = {
    1: "lighthearted",
    2: "casual",
    3: "moderate",
    4: "deep",
    5: "vulnerable",
}


def _build_embed_text(row) -> str:
    """Build a rich text string from question + labels for embedding."""
    _, question_text, categories, topics, audience, depth = row
    parts = [question_text]
    if categories:
        parts.append(f"[categories: {', '.join(categories)}]")
    if topics:
        parts.append(f"[topics: {', '.join(topics)}]")
    if audience:
        parts.append(f"[audience: {', '.join(audience)}]")
    if depth:
        parts.append(f"[depth: {DEPTH_LABELS.get(depth, str(depth))}]")
    return " ".join(parts)


def main():
    parser = argparse.ArgumentParser(description="Embed question items")
    parser.add_argument("--batch-size", type=int, default=100)
    args = parser.parse_args()

    # Import after path setup
    from app.services.embeddings.embedder import embed_texts

    engine = create_engine(DATABASE_URL)
    Session = sessionmaker(bind=engine)
    db = Session()

    try:
        # Get all questions without embeddings
        rows = db.execute(
            text(
                "SELECT id, question_text, content_categories, topics, audience_fit, depth_level "
                "FROM question_items "
                "WHERE embedding IS NULL AND status = 'active' "
                "ORDER BY created_at"
            )
        ).fetchall()

        if not rows:
            print("✅ All questions already have embeddings")
            return

        print(f"📊 Found {len(rows)} questions without embeddings")

        ids = [r[0] for r in rows]
        texts = [_build_embed_text(r) for r in rows]

        # Embed in batches
        embeddings = embed_texts(texts, batch_size=args.batch_size)

        # Update rows
        for qid, emb in zip(ids, embeddings):
            vec_str = "[" + ",".join(str(v) for v in emb) + "]"
            db.execute(
                text(
                    "UPDATE question_items SET embedding = CAST(:emb AS vector) "
                    "WHERE id = :id"
                ),
                {"emb": vec_str, "id": qid},
            )

        db.commit()
        print(f"✅ Embedded {len(ids)} questions")

    finally:
        db.close()


if __name__ == "__main__":
    main()
