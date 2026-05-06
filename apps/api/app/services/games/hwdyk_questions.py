"""Question bank for How Well Do You Know [Person]? game."""

from __future__ import annotations

import random
from typing import Literal

QUESTIONS_LIGHT = [
    "What is your favorite food?",
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
]

QUESTIONS_PERSONAL = [
    "What was your favorite subject in school?",
    "What is your current job title?",
    "Who was your best friend growing up?",
    "What is one thing most people here don't know about you?",
    "What is your proudest accomplishment?",
    "What is your biggest fear?",
    "What is your most embarrassing moment you can laugh about now?",
    "What is your love language?",
    "What is the best advice you've ever received?",
    "What is your guilty pleasure?",
    "What was your childhood dream job?",
    "What is the best gift you've ever received?",
    "What is the most spontaneous thing you've ever done?",
    "What is a skill you wish you had?",
    "What is your favorite family tradition?",
    "What is your go-to dance move?",
    "What is the weirdest food combination you enjoy?",
    "What is your most-watched movie or show?",
    "What is one habit you're trying to break?",
    "What is the best compliment you've ever received?",
]

QUESTIONS_DEEP = [
    "Where did you have your first kiss?",
    "What is one childhood memory you still think about?",
    "What is the best place you've ever visited?",
    "What is something you've never told anyone in this group?",
    "What was the hardest decision you've ever made?",
    "What is the biggest risk you've ever taken?",
    "What is your biggest regret?",
    "If you could relive one day of your life, which would it be?",
    "What was your most transformative life experience?",
    "What do you value most in a friendship?",
    "What is the most important lesson you've learned the hard way?",
    "What are you most grateful for right now?",
    "What would you change about your past if you could?",
    "What is your definition of success?",
    "What keeps you up at night?",
    "What is a belief you held strongly but changed your mind about?",
    "What moment in your life shaped who you are today?",
    "What is one thing you wish you could tell your younger self?",
    "What is the kindest thing someone has ever done for you?",
    "What legacy do you want to leave behind?",
]

IntimacyLevel = Literal["light", "personal", "deep"]

QUESTIONS_BY_LEVEL: dict[IntimacyLevel, list[str]] = {
    "light": QUESTIONS_LIGHT,
    "personal": QUESTIONS_PERSONAL,
    "deep": QUESTIONS_DEEP,
}


def select_questions(
    count: int, intimacy_level: IntimacyLevel = "personal"
) -> list[str]:
    """Select random questions from the bank filtered by intimacy level.

    If count exceeds the pool for a single level, pulls from adjacent levels.
    """
    pool = list(QUESTIONS_BY_LEVEL[intimacy_level])

    if len(pool) < count:
        if intimacy_level == "light":
            pool += QUESTIONS_PERSONAL
        elif intimacy_level == "deep":
            pool += QUESTIONS_PERSONAL
        else:
            pool += QUESTIONS_LIGHT + QUESTIONS_DEEP

    return random.sample(pool, min(count, len(pool)))
