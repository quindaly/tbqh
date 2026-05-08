"""Question bank for How Well Do You Know [Person]? game.

Questions use template placeholders for personalization:
  {poss}  — possessive: "your" (self) / "John's" (others)
  {subj}  — subject:    "you"  (self) / "John"   (others)
  {obj}   — object:     "you"  (self) / "John"   (others)
  {their} — possessive after name already used: "your" (self) / "their" (others)
"""

from __future__ import annotations

import random

QUESTIONS = [
    "What is {poss} favorite food?",
    "What is {poss} favorite restaurant?",
    "What is {poss} go-to karaoke song?",
    "What is {poss} favorite movie of all time?",
    "What food could {subj} eat every day?",
    "What is {poss} favorite holiday destination?",
    "What is {poss} hidden talent?",
    "What is {poss} most-used emoji?",
    "What is {poss} comfort TV show?",
    "What is {poss} dream vacation?",
    "What is {poss} biggest pet peeve?",
    "What is {poss} favorite season?",
    "What was {poss} first job?",
    "What is {poss} go-to coffee order?",
    "What is {poss} favorite board game?",
    "What would {poss} superpower be?",
    "What is {poss} favorite snack?",
    "What is {poss} favorite song right now?",
    "What is {poss} favorite app on {their} phone?",
    "What is {poss} go-to takeout order?",
    "What is {poss} favorite way to spend a weekend?",
    "What is {poss} favorite book?",
    "What is {poss} favorite ice cream flavor?",
    "What is {poss} favorite way to relax?",
    "What was {poss} favorite subject in school?",
    "What is {poss} current job title?",
    "Who was {poss} best friend growing up?",
    "What is {poss} biggest fear?",
    "What is {poss} love language?",
    "What is {poss} best piece of advice ever received?",
    "What is {poss} guilty pleasure?",
    "What was {poss} childhood dream job?",
    "What is {poss} favorite gift ever received?",
    "What is {poss} most spontaneous moment?",
    "What skill would {subj} most love to have?",
    "What is {poss} most-watched movie or show?",
    "What is {poss} worst habit?",
    "What is {poss} favorite compliment ever received?",
    "Where did {subj} have {their} first kiss?",
    "At what age did {subj} have {their} first kiss?",
    "What is {poss} most embarrassing moment?",
    "What is {poss} favorite place ever visited?",
    "What is {poss} most important quality in a friendship?",
]


def format_question_self(template: str) -> str:
    """Format a question template for the main person (second person)."""
    return template.format(poss="your", subj="you", obj="you", their="your")


def format_question_other(template: str, name: str) -> str:
    """Format a question template for guessers (third person with name)."""
    return template.format(poss=f"{name}'s", subj=name, obj=name, their="their")


def select_questions(count: int) -> list[str]:
    """Select *count* random questions from the pool."""
    return random.sample(QUESTIONS, min(count, len(QUESTIONS)))
