"""Question bank for How Well Do You Know [Person]? game."""

from __future__ import annotations

import random

QUESTIONS = [
    "What is your favorite food?",
    "What is your favorite restaurant?",
    "What is your go-to karaoke song?",
    "What is your favorite movie of all time?",
    "What food could you eat every day?",
    "What is your favorite holiday destination?",
    "What is your hidden talent?",
    "What is your most-used emoji?",
    "What is your comfort TV show?",
    "What is your dream vacation?",
    "What is your biggest pet peeve?",
    "What is your favorite season?",
    "What was your first job?",
    "What is your go-to coffee order?",
    "What is your favorite board game?",
    "What would your superpower be?",
    "What is your favorite snack?",
    "What is your favorite song right now?",
    "What is your favorite app on your phone?",
    "What is your go-to takeout order?",
    "What is your favorite way to spend a weekend?",
    "What is your favorite book?",
    "What is your favorite ice cream flavor?",
    "What is your favorite way to relax?",
    "What was your favorite subject in school?",
    "What is your current job title?",
    "Who was your best friend growing up?",
    "What is your biggest fear?",
    "What is your love language?",
    "What is the best advice you've ever received?",
    "What is your guilty pleasure?",
    "What was your childhood dream job?",
    "What is the best gift you've ever received?",
    "What is the most spontaneous thing you've ever done?",
    "What is a skill you wish you had?",
    "What is your most-watched movie or show?",
    "What is one habit you're trying to break?",
    "What is the best compliment you've ever received?",
    "Where did you have your first kiss?",
    "How old were you when you had your first kiss?",
    "What is your most embarrassing moment?",
    "What is the best place you've ever visited?",
    "What do you value most in a friendship?",
]


def select_questions(count: int) -> list[str]:
    """Select *count* random questions from the pool."""
    return random.sample(QUESTIONS, min(count, len(QUESTIONS)))
