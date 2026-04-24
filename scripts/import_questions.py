#!/usr/bin/env python3
"""Import discussion questions from a JSON/CSV file into question_items table.

Usage:
    python scripts/import_questions.py [--file questions.json] [--format json|csv]

If no file is specified, seeds a default set of discussion questions.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys

# Add the api app to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "apps", "api"))

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

DATABASE_URL = os.environ.get(
    "DATABASE_URL", "postgresql+psycopg://app:app@localhost:5432/app"
)

# Default seed questions (a curated starter set)
DEFAULT_QUESTIONS = [
    "What's the most spontaneous thing you've ever done?",
    "If you could have dinner with anyone, living or dead, who would it be and why?",
    "What's a skill you'd love to learn but haven't had the chance to?",
    "What's the best piece of advice you've ever received?",
    "If you could travel anywhere tomorrow, where would you go?",
    "What's something you believed as a child that you later found out wasn't true?",
    "What's a book, movie, or show that changed your perspective on something?",
    "If you could switch lives with someone for a day, who would it be?",
    "What's a tradition or ritual that's important to you?",
    "What's the most interesting thing you've learned recently?",
    "If you had an extra hour every day, how would you spend it?",
    "What's a challenge you've overcome that you're proud of?",
    "What does your ideal weekend look like?",
    "If you could instantly become an expert in something, what would it be?",
    "What's a small thing that makes your day better?",
    "What's the most memorable meal you've ever had?",
    "If you could change one thing about the world, what would it be?",
    "What's something you've done that scared you at first but turned out great?",
    "What's a question you wish people would ask you more often?",
    "If you could relive one day of your life, which day would you choose?",
    "What's something you're looking forward to?",
    "What's a hobby you've picked up recently or want to pick up?",
    "If your life had a theme song, what would it be?",
    "What's the kindest thing someone has done for you?",
    "What's a place that feels like home to you, other than your actual home?",
    "If you could start a business, what would it be?",
    "What's a movie or show you can watch over and over?",
    "What's the most beautiful place you've ever been?",
    "What's something that always makes you laugh?",
    "If you could have any superpower, what would you choose and why?",
    "What's a goal you're currently working toward?",
    "What's the best trip you've ever taken?",
    "If you could master any musical instrument overnight, which one?",
    "What's a lesson you learned the hard way?",
    "What's something about you that surprises people?",
    "If you could have coffee with your future self, what would you ask?",
    "What's a cause or issue you care deeply about?",
    "What's the most interesting job you've ever had or heard of?",
    "If you could live in any era, which would you choose?",
    "What's a food you could eat every day and never get tired of?",
    "What's the best gift you've ever given or received?",
    "If you had to teach a class on anything, what would it be?",
    "What's something you've always wanted to try but haven't yet?",
    "What's a quality you admire in other people?",
    "If you could solve one global problem, which would it be?",
    "What's the most fun you've had at work?",
    "What's a memory that always makes you smile?",
    "If you could design your dream house, what's one must-have feature?",
    "What's something that's overrated? What's something that's underrated?",
    "What's a conversation topic you never get tired of discussing?",
]


def import_from_json(filepath: str, db_session):
    with open(filepath) as f:
        data = json.load(f)

    questions = data if isinstance(data, list) else data.get("questions", [])
    _insert_questions(db_session, questions)


def import_from_csv(filepath: str, db_session):
    with open(filepath) as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    count = 0
    for row in rows:
        q_text = (row.get("question_text") or row.get("question") or "").strip()
        if not q_text:
            continue

        # Check for duplicate
        exists = db_session.execute(
            text("SELECT 1 FROM question_items WHERE question_text = :t"),
            {"t": q_text},
        ).first()
        if exists:
            print(f"  ⏭  Skipping duplicate: {q_text[:60]}...")
            continue

        db_session.execute(
            text(
                "INSERT INTO question_items (id, question_text, status) "
                "VALUES (gen_random_uuid(), :text, 'active')"
            ),
            {"text": q_text},
        )
        count += 1

    db_session.commit()
    print(
        f"✅ Imported {count} questions from CSV ({len(rows)} total, {len(rows)-count} duplicates/empty skipped)"
    )


def _insert_questions(db_session, questions: list[str]):
    count = 0
    for q_text in questions:
        q_text = q_text.strip()
        if not q_text:
            continue
        # Check for duplicate
        exists = db_session.execute(
            text("SELECT 1 FROM question_items WHERE question_text = :t"),
            {"t": q_text},
        ).first()
        if exists:
            print(f"  ⏭  Skipping duplicate: {q_text[:60]}...")
            continue

        db_session.execute(
            text(
                "INSERT INTO question_items (id, question_text, status) "
                "VALUES (gen_random_uuid(), :text, 'active')"
            ),
            {"text": q_text},
        )
        count += 1
    db_session.commit()
    print(
        f"✅ Imported {count} questions ({len(questions)} total, {len(questions)-count} duplicates skipped)"
    )


def main():
    parser = argparse.ArgumentParser(description="Import discussion questions")
    parser.add_argument("--file", type=str, help="Path to questions file")
    parser.add_argument(
        "--format",
        type=str,
        choices=["json", "csv"],
        default="json",
        help="File format (default: json)",
    )
    args = parser.parse_args()

    engine = create_engine(DATABASE_URL)
    Session = sessionmaker(bind=engine)
    db = Session()

    try:
        if args.file:
            if args.format == "csv":
                import_from_csv(args.file, db)
            else:
                import_from_json(args.file, db)
        else:
            print("No file specified — seeding default questions...")
            _insert_questions(db, DEFAULT_QUESTIONS)
    finally:
        db.close()


if __name__ == "__main__":
    main()
