"""Static bank of self-answer questions for Who Knows Who."""

from __future__ import annotations

import random

SELF_ANSWER_QUESTIONS: list[str] = [
    "What was your favorite subject in school?",
    "What is one food you could eat every week?",
    "What is a place you would love to visit?",
    "Are you more of a dog person or cat person?",
    "What is one hobby you wish you did more often?",
    "What is the most spontaneous thing you have ever done?",
    "If you could have any superpower, what would it be?",
    "What is your go-to comfort movie or TV show?",
    "What is a skill you would love to learn?",
    "What is your favorite way to spend a lazy Sunday?",
    "If you could live anywhere in the world, where would it be?",
    "What is a song that always puts you in a good mood?",
    "What is the best meal you have ever had?",
    "What is something most people do not know about you?",
    "If you could have dinner with anyone, living or dead, who would it be?",
    "What was your dream job as a kid?",
    "What is your biggest pet peeve?",
    "What is a book or podcast you would recommend to anyone?",
    "What is your guilty pleasure?",
    "What is the best piece of advice you have ever received?",
    "If you won the lottery, what is the first thing you would do?",
    "What is your favorite season and why?",
    "What is a tradition you love?",
    "What is a fear you would like to overcome?",
    "If you could learn any language instantly, which would it be?",
    "What is your favorite thing about your best friend?",
    "What is something you are proud of?",
    "What is the most adventurous thing on your bucket list?",
    "What would your perfect weekend look like?",
    "What is your go-to karaoke song?",
    "If you could time-travel, would you go to the past or the future?",
    "What is one thing you cannot leave the house without?",
    "What is a movie that made you cry?",
    "What is the weirdest food combination you enjoy?",
    "What is your favorite holiday?",
    "If you were a fictional character, who would you be?",
    "What is a small thing that makes your day better?",
    "What is your morning routine like?",
    "What is the last thing that made you laugh out loud?",
    "If you could master one instrument overnight, which would it be?",
]


def select_questions(count: int = 10) -> list[str]:
    """Return *count* random questions from the bank."""
    return random.sample(SELF_ANSWER_QUESTIONS, min(count, len(SELF_ANSWER_QUESTIONS)))
