#!/usr/bin/env python3
"""Offline AI labeling: assign content_categories, topics, audience_fit, depth to question_items.

Usage:
    python scripts/label_questions.py [--batch-size 20] [--limit 100]

Requires LLM_API_KEY.
"""

from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "apps", "api"))

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

DATABASE_URL = os.environ.get(
    "DATABASE_URL", "postgresql+psycopg://app:app@localhost:5432/app"
)


def main():
    parser = argparse.ArgumentParser(description="Label question items with AI")
    parser.add_argument("--batch-size", type=int, default=20)
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()

    from app.services.llm.client import call_llm_json
    from app.services.llm.schemas import offline_question_labeling_schema

    engine = create_engine(DATABASE_URL)
    Session = sessionmaker(bind=engine)
    db = Session()

    try:
        query = (
            "SELECT id, question_text FROM question_items "
            "WHERE content_categories IS NULL OR content_categories = '{}' "
            "ORDER BY created_at"
        )
        if args.limit:
            query += f" LIMIT {args.limit}"

        rows = db.execute(text(query)).fetchall()

        if not rows:
            print("✅ All questions already labeled")
            return

        print(f"📊 Found {len(rows)} unlabeled questions")
        schema = offline_question_labeling_schema()

        for qid, q_text in rows:
            try:
                result = call_llm_json(
                    "You are a content labeling assistant. Analyze each discussion question by considering its topic, intent "
                    "(reflection, storytelling, opinion, vulnerability, humor, debate), tone/emotional depth, and intended audience.\n\n"
                    "Output ONLY a flat JSON object with exactly these keys:\n"
                    "- content_categories: array of broad subject areas (e.g. 'Personal Growth', 'Relationships', 'Career')\n"
                    "- topics: array of granular topic tags (e.g. 'regret', 'fear', 'childhood', 'travel')\n"
                    "- audience_fit: array from ['friends', 'coworkers', 'family', 'couples', 'strangers', 'mixed']\n"
                    "- depth_level: integer 1-5 (1=lighthearted/icebreaker, 5=deeply personal/vulnerable)\n"
                    "- family_friendly_ok: boolean\n\n"
                    "Do NOT nest or wrap these fields. Return a single flat JSON object.",
                    f"Question: {q_text}",
                    schema,
                    temperature=0.3,
                )
                db.execute(
                    text(
                        "UPDATE question_items SET "
                        "content_categories = :cats, topics = :topics, "
                        "audience_fit = :audience, depth_level = :depth "
                        "WHERE id = :id"
                    ),
                    {
                        "cats": result.get("content_categories", []),
                        "topics": result.get("topics", []),
                        "audience": result.get("audience_fit", []),
                        "depth": result.get("depth_level", 3),
                        "id": qid,
                    },
                )
                db.commit()
                print(f"  ✅ Labeled: {q_text[:50]}...")
            except Exception as e:
                print(f"  ❌ Failed: {q_text[:50]}... ({e})")

        print(f"✅ Labeling complete")
    finally:
        db.close()


if __name__ == "__main__":
    main()
