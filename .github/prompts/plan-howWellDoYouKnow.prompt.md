# Plan: "How Well Do You Know [Person]?" Social Game

Build a new multiplayer social game with two modes (Default Mode with AI-generated distractors, Party Mode with player-submitted fake answers) following the exact patterns established by "Who Knows Who." Extends the existing `ExperienceInstance` state machine, adds new DB tables for multiple-choice answers, an LLM distractor generation service, and new frontend pages for setup/review/play flows.

---

## Phase 1-2: Database Schema & Models *(do first, blocks everything)*

**New Alembic migration** (`003_how_well_do_you_know.py`):

1. Extend `ck_experience_type` to include `'how_well_do_you_know'`
2. Extend `ck_experience_game_state` with: `ai_generating_choices`, `main_person_reviewing_choices`, `players_submitting_fake_answers`
3. Add `main_person_participant_id` (UUID FK → participants) to `experience_instances`
4. Add columns to `game_rounds`: `question_text` (TEXT), `correct_choice_id` (UUID FK), `timer_duration` (INT default 60), `round_locked_at` (DATETIME)
5. Create `game_choices` table — stores correct answer + distractors/fakes per round with `source_type` enum (`main_person`, `ai_generated`, `main_person_edited`, `player_fake`, `ai_fallback`)
6. Create `game_mc_guesses` table — stores each player's selected choice per round with `points_awarded`

**New model files:**

### `apps/api/app/db/models/game_choice.py`

```python
"""GameChoice model — stores answer options for How Well Do You Know rounds."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    Text,
    CheckConstraint,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, UUIDPKMixin


class GameChoice(Base, UUIDPKMixin):
    __tablename__ = "game_choices"

    game_round_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("game_rounds.id"), nullable=False
    )
    choice_text: Mapped[str] = mapped_column(Text, nullable=False)
    is_correct: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    source_type: Mapped[str] = mapped_column(Text, nullable=False)
    created_by_participant_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("participants.id"), nullable=True
    )
    original_ai_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    display_order: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    __table_args__ = (
        CheckConstraint(
            "source_type IN ('main_person', 'ai_generated', 'main_person_edited', 'player_fake', 'ai_fallback')",
            name="ck_game_choice_source_type",
        ),
        UniqueConstraint("game_round_id", "choice_text", name="uq_round_choice_text"),
    )

    game_round = relationship("GameRound", back_populates="choices")
    created_by = relationship("Participant")
```

### `apps/api/app/db/models/game_mc_guess.py`

```python
"""GameMCGuess model — stores multiple-choice guesses for How Well Do You Know rounds."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, UUIDPKMixin


class GameMCGuess(Base, UUIDPKMixin):
    __tablename__ = "game_mc_guesses"

    game_round_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("game_rounds.id"), nullable=False
    )
    participant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("participants.id"), nullable=False
    )
    selected_choice_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("game_choices.id"), nullable=False
    )
    is_correct: Mapped[bool] = mapped_column(Boolean, nullable=False)
    points_awarded: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    submitted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    __table_args__ = (
        UniqueConstraint("game_round_id", "participant_id", name="uq_mc_guess_round_participant"),
    )

    game_round = relationship("GameRound", back_populates="mc_guesses")
    participant = relationship("Participant")
    selected_choice = relationship("GameChoice")
```

### Extend `apps/api/app/db/models/game_round.py`

Add columns:
- `question_text: Mapped[str | None]` (TEXT, nullable)
- `correct_choice_id: Mapped[uuid.UUID | None]` (UUID FK → game_choices.id, nullable)
- `timer_duration: Mapped[int | None]` (INTEGER, default 60)
- `round_locked_at: Mapped[datetime | None]` (DATETIME(tz), nullable)

Add relationships:
- `choices = relationship("GameChoice", back_populates="game_round")`
- `mc_guesses = relationship("GameMCGuess", back_populates="game_round")`

### Extend `apps/api/app/db/models/experience.py`

Add column:
- `main_person_participant_id: Mapped[uuid.UUID | None]` (UUID FK → participants.id, nullable)

Update CHECK constraints:
- `ck_experience_type`: add `'how_well_do_you_know'`
- `ck_experience_game_state`: add `'ai_generating_choices'`, `'main_person_reviewing_choices'`, `'players_submitting_fake_answers'`

---

## Phase 3: LLM Distractor Generation *(parallel with Phase 4)*

### 3.1 New JSON schema: `schemas/distractor_generation_output.json`

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://example.com/schemas/distractor_generation.json",
  "type": "object",
  "additionalProperties": false,
  "properties": {
    "wrong_answers": {
      "type": "array",
      "minItems": 3,
      "maxItems": 5,
      "items": { "type": "string", "minLength": 1, "maxLength": 120 }
    }
  },
  "required": ["wrong_answers"]
}
```

### 3.2 New prompt templates — add to `apps/api/app/services/llm/prompts.py`

```python
DISTRACTOR_GENERATION_SYSTEM = """You generate plausible wrong answers for a social trivia game called "How Well Do You Know [Person]?"

Given a personal question and the correct answer about someone, generate believable but incorrect alternative answers.

You MUST respond with valid JSON containing EXACTLY this structure (no other keys):
{
  "wrong_answers": ["<string>", "<string>", "<string>"]
}

Rules:
- Generate exactly {num_distractors} wrong answers.
- Wrong answers must be plausible for the person and question context.
- Match the length, specificity, and tone of the correct answer.
- Do NOT include the correct answer or near-duplicates of it.
- Do NOT include offensive, sexual, cruel, or embarrassing content.
- Do NOT include obviously fake or joke answers.
- Each wrong answer should be distinct from the others.
- Keep answers concise (under 80 characters each).
- Consider the intimacy level: {intimacy_level}."""

DISTRACTOR_GENERATION_USER = """Question: {question_text}
Correct answer: {correct_answer}
Number of wrong answers needed: {num_distractors}
Intimacy level: {intimacy_level}
Context about the person (if available): {person_context}

Generate plausible wrong answers. Respond with EXACTLY the JSON structure: {{"wrong_answers": [...]}}"""
```

### 3.3 Add schema loader to `apps/api/app/services/llm/schemas.py`

```python
def distractor_generation_schema() -> dict:
    return _load("distractor_generation_output.json")
```

---

## Phase 4-5: Backend Game Service & State Machine *(depends on Phase 1-2)*

### 4.1 New orchestrator: `apps/api/app/services/games/how_well_do_you_know.py`

**Game Lifecycle Functions:**

```python
async def create_game(
    db: Session,
    user_id: UUID | None,
    display_name: str,
    mode: str,  # "default" | "party"
    num_questions: int = 5,
    intimacy_level: str = "personal",
) -> dict:
    """Create a new HWDYK game session.
    
    Returns: {group_id, session_id, experience_instance_id, participant_id, join_code, share_url}
    """
    # 1. Create Group
    # 2. Create host Participant (role="host")
    # 3. Create PolicyProfile (default)
    # 4. Create Session with join_code
    # 5. Create SessionParticipant link
    # 6. Create ExperienceInstance:
    #    - experience_type="how_well_do_you_know"
    #    - game_state="lobby"
    #    - game_config={"mode": mode, "num_questions": num_questions, "intimacy_level": intimacy_level}
    #    - max_rounds=num_questions
    # 7. Return identifiers + share_url
    ...


async def join_game(
    db: Session,
    join_code: str,
    display_name: str,
    user_id: UUID | None,
    join_mode: str,
) -> dict:
    """Join an existing HWDYK game by code. Validates state == lobby."""
    ...


async def select_main_person(
    db: Session,
    exp: ExperienceInstance,
    host_participant_id: UUID,
    main_person_participant_id: UUID,
) -> None:
    """Host selects the main person. Validates caller is host."""
    # Set exp.main_person_participant_id
    ...


async def start_setup(
    db: Session,
    exp: ExperienceInstance,
    host_participant_id: UUID,
) -> dict:
    """Host starts the game — transitions lobby → main_person_answering.
    
    Validates: host role, main_person is set, min 2 participants.
    Creates question PromptInstances from question bank.
    Returns: {prompts_created: int}
    """
    ...
```

**Main Person Answer Collection:**

```python
async def get_main_person_questions(db: Session, exp_id: UUID) -> list[dict]:
    """Returns questions for the main person to answer."""
    ...


async def submit_main_person_answer(
    db: Session,
    exp: ExperienceInstance,
    prompt_instance_id: UUID,
    participant_id: UUID,
    answer_text: str,
) -> dict:
    """Main person submits an answer.
    
    Validates: caller is main person, min length 3 chars.
    Creates GameRound with question_text, status="setup".
    Creates correct GameChoice (source_type="main_person", is_correct=True).
    Checks if all questions answered → triggers next phase.
    Returns: {ok: True, all_answered: bool}
    """
    ...
```

**Default Mode — AI Distractor Generation:**

```python
async def generate_distractors(db: Session, exp: ExperienceInstance) -> None:
    """For each round, call LLM to generate 3 plausible wrong answers.
    
    Transitions: main_person_answering → ai_generating_choices → main_person_reviewing_choices.
    Creates GameChoice entries with source_type="ai_generated".
    """
    ...


async def get_review_data(db: Session, exp_id: UUID, participant_id: UUID) -> list[dict]:
    """Returns all rounds with choices for main person review.
    
    Validates: caller is main person.
    Returns: [{round_id, question_text, correct_answer, choices: [{id, text, source_type}]}]
    """
    ...


async def edit_choice(
    db: Session,
    exp: ExperienceInstance,
    choice_id: UUID,
    participant_id: UUID,
    new_text: str,
) -> None:
    """Main person edits an AI-generated choice.
    
    Validates: caller is main person, choice is not correct answer.
    Stores original_ai_text, updates choice_text, sets source_type="main_person_edited".
    """
    ...


async def regenerate_choice(
    db: Session,
    exp: ExperienceInstance,
    choice_id: UUID,
    participant_id: UUID,
) -> dict:
    """Regenerate a single distractor via LLM.
    
    Returns: {new_text: str}
    """
    ...


async def confirm_choices(
    db: Session,
    exp: ExperienceInstance,
    participant_id: UUID,
) -> None:
    """Main person locks all rounds — validates each has 1 correct + 3 wrong.
    
    Shuffles display_order per round.
    Transitions: main_person_reviewing_choices → ready_to_start.
    """
    ...
```

**Party Mode — Fake Answer Collection:**

```python
async def get_fake_answer_questions(
    db: Session, exp_id: UUID, participant_id: UUID
) -> list[dict]:
    """Returns questions for non-main-person players to submit fakes.
    
    Validates: caller is not main person.
    Returns: [{round_id, question_text, already_submitted: bool}]
    """
    ...


async def submit_fake_answer(
    db: Session,
    exp: ExperienceInstance,
    round_id: UUID,
    participant_id: UUID,
    fake_text: str,
) -> dict:
    """Player submits a fake answer.
    
    Validates:
    - Caller is not main person
    - Not blank, max 80 chars
    - Does not match correct answer (case-insensitive)
    - No exact duplicate for this round
    Creates GameChoice with source_type="player_fake".
    Returns: {ok: True}
    """
    ...


async def get_fake_answer_progress(db: Session, exp_id: UUID) -> dict:
    """Returns submission progress per round and per player.
    
    Returns: {rounds: [{round_id, fake_count}], players: [{participant_id, submitted_count, total}]}
    """
    ...


async def lock_party_mode(
    db: Session,
    exp: ExperienceInstance,
    host_participant_id: UUID,
) -> None:
    """Host locks party mode when enough fakes are submitted.
    
    Validates: min 2 fake answers per round (else generates AI fallback).
    Assembles choices: correct + sample of fakes (max 6 total per round).
    Shuffles display_order.
    Transitions: players_submitting_fake_answers → ready_to_start.
    """
    ...
```

**Live Gameplay:**

```python
async def start_live_game(
    db: Session,
    exp: ExperienceInstance,
    host_participant_id: UUID,
) -> None:
    """Host starts live gameplay.
    
    Activates round 1 (status="active", started_at=now()).
    Transitions: ready_to_start → round_active.
    """
    ...


async def get_round_state(db: Session, exp: ExperienceInstance) -> dict:
    """Returns current round state for polling.
    
    Active round: question, shuffled choices (no correct marker), timer info, guess count.
    Reveal round: question, choices with correct marked, all guesses with distribution, scores.
    Also checks timer expiry and auto-locks if needed.
    
    Returns: {
        round_id, round_number, status, question_text,
        choices: [{id, text, is_correct (only on reveal), source_type (only on reveal for party mode)}],
        time_remaining_seconds,
        guesses_submitted, total_guessers,
        reveal: {correct_choice_id, distribution: [{choice_id, guessers: [participant_ids]}], scores},
        main_person_participant_id,
    }
    """
    ...


async def submit_mc_guess(
    db: Session,
    exp: ExperienceInstance,
    round_id: UUID,
    participant_id: UUID,
    choice_id: UUID,
) -> dict:
    """Player submits a multiple-choice guess.
    
    Validates:
    - Round is active
    - Caller is not main person
    - No duplicate guess for this round
    - Choice belongs to this round
    Creates GameMCGuess with is_correct and base points (100 if correct, 0 if not).
    Checks if all players answered → auto-locks round if yes.
    Returns: {ok: True, is_correct: bool, all_guessed: bool}
    """
    ...


async def check_and_lock_timer(db: Session, exp: ExperienceInstance, round_id: UUID) -> bool:
    """Check if round timer has expired; if so, lock the round.
    
    Called on each state poll.
    Returns: True if round was just locked due to timer.
    """
    ...


async def reveal_round(
    db: Session,
    exp: ExperienceInstance,
    round_id: UUID,
) -> None:
    """Reveal round results — called by host or auto after lock.
    
    Calculates Party Mode fool points (+50 per player fooled by your fake).
    Updates points_awarded on GameMCGuess entries.
    Sets round status="revealed".
    Transitions: round_active → round_reveal.
    """
    ...


async def advance_round(
    db: Session,
    exp: ExperienceInstance,
    round_id: UUID,
) -> dict:
    """Host advances to next round or completes game.
    
    Marks current round completed. Activates next or transitions to completed.
    Returns: {ok: True, is_last: bool}
    """
    ...
```

**Scoring:**

```python
async def compute_scores(db: Session, exp_id: UUID) -> list[dict]:
    """Compute leaderboard from GameMCGuess records.
    
    Returns: [{
        participant_id, display_name, score, correct_count,
        fool_count (Party Mode only), rank
    }]
    """
    # Sum points_awarded from all GameMCGuess for this experience
    # For Party Mode: also count how many other players selected a choice created by this participant
    ...
```

### 5.1 Update `apps/api/app/services/games/state.py`

Extend `VALID_TRANSITIONS` dict:

```python
# Add for how_well_do_you_know:
VALID_TRANSITIONS = {
    # ... existing who_knows_who transitions ...
    
    # HWDYK shared
    "lobby": ["main_person_answering", "question_collection", ...],
    "main_person_answering": ["ai_generating_choices", "players_submitting_fake_answers"],
    
    # HWDYK Default Mode
    "ai_generating_choices": ["main_person_reviewing_choices"],
    "main_person_reviewing_choices": ["ready_to_start"],
    
    # HWDYK Party Mode
    "players_submitting_fake_answers": ["ready_to_start"],
    
    # HWDYK shared gameplay (merge with existing)
    "ready_to_start": ["round_active"],
    "round_active": ["round_reveal"],
    "round_reveal": ["round_active", "completed"],  # next round or finish
}
```

Extend `get_game_state_payload()` to handle `experience_type == "how_well_do_you_know"` with MC-specific data.

---

## Phase 6: Catalog & Question Bank *(parallel with Phase 4)*

### 6.1 Update `apps/api/app/services/games/catalog.py`

```python
GAMES = [
    {
        "slug": "who-knows-who",
        "name": "Who Knows Who?",
        # ... existing ...
    },
    {
        "slug": "how-well-do-you-know",
        "name": "How Well Do You Know [Person]?",
        "description": "One person answers personal questions. Everyone else guesses the correct answer from multiple choices.",
        "min_players": 3,
        "max_players": 20,
        "modes": ["default", "party"],
        "status": "active",
    },
]
```

### 6.2 New question bank: `apps/api/app/services/games/hwdyk_questions.py`

```python
"""Question bank for How Well Do You Know [Person]? game."""

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
]

IntimacyLevel = Literal["light", "personal", "deep"]

QUESTIONS_BY_LEVEL: dict[IntimacyLevel, list[str]] = {
    "light": QUESTIONS_LIGHT,
    "personal": QUESTIONS_PERSONAL,
    "deep": QUESTIONS_DEEP,
}


def select_questions(count: int, intimacy_level: IntimacyLevel = "personal") -> list[str]:
    """Select random questions from the bank filtered by intimacy level.
    
    If count exceeds the pool for a single level, pulls from adjacent levels.
    """
    pool = list(QUESTIONS_BY_LEVEL[intimacy_level])
    
    # If not enough questions at this level, add from adjacent levels
    if len(pool) < count:
        if intimacy_level == "light":
            pool += QUESTIONS_PERSONAL
        elif intimacy_level == "deep":
            pool += QUESTIONS_PERSONAL
        else:  # personal
            pool += QUESTIONS_LIGHT + QUESTIONS_DEEP
    
    return random.sample(pool, min(count, len(pool)))
```

---

## Phase 7: API Routes *(depends on Phase 4)*

### Extend `apps/api/app/api/v1/routes/games.py`

New endpoints (all under `/api/v1`):

```python
# === SETUP ===

@router.post("/games/how-well-do-you-know/create")
async def create_hwdyk_game(body: CreateHWDYKBody, db: Session = Depends(get_db)):
    """Create a new How Well Do You Know game.
    Body: {display_name, mode, num_questions?, intimacy_level?}
    Returns: {group_id, session_id, experience_instance_id, participant_id, join_code, share_url}
    """
    ...

@router.post("/games/how-well-do-you-know/join")
async def join_hwdyk_game(body: JoinGameBody, db: Session = Depends(get_db)):
    """Join by code. Body: {join_code, display_name, join_mode}"""
    ...

@router.post("/experiences/{experience_id}/select-main-person")
async def select_main_person(experience_id: UUID, body: SelectMainPersonBody, db: Session = Depends(get_db)):
    """Host selects main person. Body: {host_participant_id, main_person_participant_id}"""
    ...

@router.post("/experiences/{experience_id}/start-setup")
async def start_hwdyk_setup(experience_id: UUID, body: StartBody, db: Session = Depends(get_db)):
    """Host starts setup phase. Body: {participant_id}"""
    ...

# === MAIN PERSON ANSWERS ===

@router.get("/experiences/{experience_id}/main-person-questions")
async def get_main_person_questions(experience_id: UUID, db: Session = Depends(get_db)):
    """Returns questions for the main person."""
    ...

@router.post("/experiences/{experience_id}/main-person-answer")
async def submit_main_person_answer(experience_id: UUID, body: MainPersonAnswerBody, db: Session = Depends(get_db)):
    """Main person submits answer. Body: {prompt_instance_id, participant_id, answer_text}"""
    ...

# === DEFAULT MODE REVIEW ===

@router.get("/experiences/{experience_id}/review-choices")
async def get_review_choices(experience_id: UUID, participant_id: UUID = Query(...), db: Session = Depends(get_db)):
    """Returns rounds + choices for main person review."""
    ...

@router.post("/experiences/{experience_id}/choices/{choice_id}/edit")
async def edit_choice(experience_id: UUID, choice_id: UUID, body: EditChoiceBody, db: Session = Depends(get_db)):
    """Main person edits a choice. Body: {participant_id, new_text}"""
    ...

@router.post("/experiences/{experience_id}/choices/{choice_id}/regenerate")
async def regenerate_choice(experience_id: UUID, choice_id: UUID, body: RegenerateBody, db: Session = Depends(get_db)):
    """Regenerate a single distractor. Body: {participant_id}"""
    ...

@router.post("/experiences/{experience_id}/confirm-choices")
async def confirm_choices(experience_id: UUID, body: ConfirmBody, db: Session = Depends(get_db)):
    """Main person locks all choices. Body: {participant_id}"""
    ...

# === PARTY MODE FAKE ANSWERS ===

@router.get("/experiences/{experience_id}/fake-answer-questions")
async def get_fake_answer_questions(experience_id: UUID, participant_id: UUID = Query(...), db: Session = Depends(get_db)):
    """Returns questions for non-main-person players."""
    ...

@router.post("/experiences/{experience_id}/fake-answer")
async def submit_fake_answer(experience_id: UUID, body: FakeAnswerBody, db: Session = Depends(get_db)):
    """Player submits fake answer. Body: {round_id, participant_id, fake_text}"""
    ...

@router.get("/experiences/{experience_id}/fake-answer-progress")
async def get_fake_answer_progress(experience_id: UUID, db: Session = Depends(get_db)):
    """Returns fake answer submission progress."""
    ...

@router.post("/experiences/{experience_id}/lock-party-mode")
async def lock_party_mode(experience_id: UUID, body: LockBody, db: Session = Depends(get_db)):
    """Host locks party mode. Body: {participant_id}"""
    ...

# === LIVE GAMEPLAY ===

@router.post("/experiences/{experience_id}/start-live")
async def start_live_game(experience_id: UUID, body: StartBody, db: Session = Depends(get_db)):
    """Host starts live gameplay. Body: {participant_id}"""
    ...

@router.post("/experiences/{experience_id}/rounds/{round_id}/mc-guess")
async def submit_mc_guess(experience_id: UUID, round_id: UUID, body: MCGuessBody, db: Session = Depends(get_db)):
    """Player submits MC guess. Body: {participant_id, choice_id}"""
    ...

# Reuse existing: reveal, advance, leaderboard, replay (extended for new game type)
```

---

## Phase 8-9: Frontend *(depends on Phase 7)*

### 8.1 Update `apps/web/lib/api.ts`

```typescript
// === HWDYK API Functions ===

export async function createHWDYKGame(
  displayName: string,
  mode: 'default' | 'party',
  numQuestions?: number,
  intimacyLevel?: 'light' | 'personal' | 'deep'
): Promise<{
  group_id: string; session_id: string; experience_instance_id: string;
  participant_id: string; join_code: string; share_url: string;
}> { ... }

export async function selectMainPerson(
  expId: string, hostParticipantId: string, mainPersonParticipantId: string
): Promise<{ ok: boolean }> { ... }

export async function startHWDYKSetup(
  expId: string, participantId: string
): Promise<{ prompts_created: number }> { ... }

export async function getMainPersonQuestions(
  expId: string
): Promise<{ questions: Array<{ prompt_instance_id: string; question_text: string; order: number }> }> { ... }

export async function submitMainPersonAnswer(
  expId: string, promptInstanceId: string, participantId: string, answerText: string
): Promise<{ ok: boolean; all_answered: boolean }> { ... }

export async function getReviewChoices(
  expId: string, participantId: string
): Promise<{ rounds: Array<{
  round_id: string; question_text: string; correct_answer: string;
  choices: Array<{ id: string; text: string; source_type: string; is_correct: boolean }>;
}> }> { ... }

export async function editChoice(
  expId: string, choiceId: string, participantId: string, newText: string
): Promise<{ ok: boolean }> { ... }

export async function regenerateChoice(
  expId: string, choiceId: string, participantId: string
): Promise<{ new_text: string }> { ... }

export async function confirmChoices(
  expId: string, participantId: string
): Promise<{ ok: boolean }> { ... }

export async function getFakeAnswerQuestions(
  expId: string, participantId: string
): Promise<{ questions: Array<{ round_id: string; question_text: string; already_submitted: boolean }> }> { ... }

export async function submitFakeAnswer(
  expId: string, roundId: string, participantId: string, fakeText: string
): Promise<{ ok: boolean }> { ... }

export async function getFakeAnswerProgress(
  expId: string
): Promise<{ rounds: Array<{ round_id: string; fake_count: number }>; players: Array<{ participant_id: string; submitted_count: number; total: number }> }> { ... }

export async function lockPartyMode(
  expId: string, participantId: string
): Promise<{ ok: boolean }> { ... }

export async function startLiveGame(
  expId: string, participantId: string
): Promise<{ ok: boolean }> { ... }

export async function submitMCGuess(
  expId: string, roundId: string, participantId: string, choiceId: string
): Promise<{ ok: boolean; is_correct: boolean; all_guessed: boolean }> { ... }
```

### 8.2 New page: `apps/web/app/games/experience/[experienceId]/answer/page.tsx`

Main person answers questions one-by-one:
- Progress bar ("Question 3 of 8")
- Textarea input (min 3 chars)
- "Next" / "Finish" buttons
- After all answered: "Generating choices..." (Default) or "Waiting for players..." (Party) with polling

### 8.3 New page: `apps/web/app/games/experience/[experienceId]/review/page.tsx`

Default Mode only — main person reviews AI choices:
- Shows each round as a card
- Question displayed prominently
- Correct answer highlighted in green (labeled "Your answer")
- AI-generated wrong answers shown as editable text fields
- "Edit" pencil icon per choice
- "Regenerate" button per choice (calls LLM for one new distractor)
- "Confirm All" button — validates all rounds and locks game
- Navigation between rounds (prev/next or scroll)

### 8.4 New page: `apps/web/app/games/experience/[experienceId]/fake-answers/page.tsx`

Party Mode only — non-main-person players submit fakes:
- Shows questions one-by-one
- Textarea input (max 80 chars, min 1 char)
- Progress indicator ("3 of 5 players have submitted")
- "Next" / "Done" buttons
- After all submitted: "Waiting for host to start..." with polling

### 8.5 Extend/New: `apps/web/app/games/experience/[experienceId]/play/page.tsx`

Multiple-choice gameplay (distinct from Who Knows Who's participant-guess UI):

**Round Active state:**
- Question displayed prominently
- 60-second countdown timer (animated bar/number)
- Multiple choice buttons (4-6 options, shuffled)
- Main person sees: "Sit back and relax — they're guessing about you!"
- After submitting: "Guess locked! Waiting for others..." + guess count indicator
- Polls `getGameState()` every 2.5s

**Round Reveal state:**
- Correct answer highlighted in green
- Each choice shows:
  - Number of players who selected it
  - List of player names who picked it (the "who picked what" feature)
  - In Party Mode: "Submitted by [PlayerName]" label on fake answers
  - In Party Mode: "+50 fool bonus" indicator if applicable
- Answer distribution bar chart
- Updated leaderboard/scores sidebar
- Host: "Next Round" or "Final Scores" button

### 8.6 Extend lobby page for HWDYK

- Add "Select Main Person" dropdown for host (shows all participants)
- Display selected main person with badge/highlight
- Mode indicator ("Default Mode" / "Party Mode")
- "Start Game" disabled until main person is selected + min 2 players
- Auto-redirect routing for new states:
  - `main_person_answering` → main person goes to `/answer`, others see "Waiting..."
  - `ai_generating_choices` → "AI is generating choices..."
  - `main_person_reviewing_choices` → main person goes to `/review`, others wait
  - `players_submitting_fake_answers` → non-main-person players go to `/fake-answers`
  - `ready_to_start` → host can start, others wait
  - `round_active` → everyone goes to `/play`

### 8.7 Extend leaderboard page

- Add "Fool Count" column for Party Mode
- Show "Players Fooled: X" stat per player
- Same replay functionality

---

## Phase 9: Timer Implementation

### Backend (server-authoritative):

```python
def check_and_lock_timer(db, exp, game_round):
    """Called on every GET /state poll."""
    if game_round.status != "active":
        return False
    if game_round.started_at is None:
        return False
    
    elapsed = (datetime.now(timezone.utc) - game_round.started_at).total_seconds()
    if elapsed >= game_round.timer_duration:
        game_round.round_locked_at = datetime.now(timezone.utc)
        # Don't auto-reveal — let host trigger reveal, but lock submissions
        return True
    return False
```

### State payload includes:

```python
"time_remaining_seconds": max(0, timer_duration - elapsed_seconds),
"is_locked": bool(round.round_locked_at),
```

### Frontend countdown:

- Render `time_remaining_seconds` from state payload
- Client-side decrement between polls (cosmetic)
- On reaching 0 client-side: show "Time's up!" and disable answer buttons
- Next poll confirms server lock

---

## Files Summary

### To Create:
| File | Purpose |
|------|---------|
| `apps/api/app/db/migrations/versions/003_how_well_do_you_know.py` | Alembic migration |
| `apps/api/app/db/models/game_choice.py` | GameChoice model |
| `apps/api/app/db/models/game_mc_guess.py` | GameMCGuess model |
| `apps/api/app/services/games/how_well_do_you_know.py` | Main game orchestrator |
| `apps/api/app/services/games/hwdyk_questions.py` | Question bank by intimacy level |
| `schemas/distractor_generation_output.json` | LLM output JSON schema |
| `apps/web/app/games/experience/[experienceId]/answer/page.tsx` | Main person answer page |
| `apps/web/app/games/experience/[experienceId]/review/page.tsx` | Choice review page (Default Mode) |
| `apps/web/app/games/experience/[experienceId]/fake-answers/page.tsx` | Fake answer page (Party Mode) |
| `apps/api/app/tests/test_hwdyk.py` | Unit + integration tests |

### To Modify:
| File | Change |
|------|--------|
| `apps/api/app/db/models/__init__.py` | Import GameChoice, GameMCGuess |
| `apps/api/app/db/models/experience.py` | Add main_person_participant_id, update CHECK constraints |
| `apps/api/app/db/models/game_round.py` | Add question_text, correct_choice_id, timer_duration, round_locked_at, relationships |
| `apps/api/app/services/games/catalog.py` | Add how-well-do-you-know entry |
| `apps/api/app/services/games/state.py` | Add new states + transitions + payload handling |
| `apps/api/app/services/llm/prompts.py` | Add DISTRACTOR_GENERATION_* templates |
| `apps/api/app/services/llm/schemas.py` | Add distractor_generation_schema() |
| `apps/api/app/api/v1/routes/games.py` | Add ~15 new endpoints |
| `apps/web/lib/api.ts` | Add typed client functions |
| `apps/web/app/games/[slug]/page.tsx` | Add mode/config selection for HWDYK |
| `apps/web/app/games/experience/[experienceId]/lobby/page.tsx` | Main person selector, state routing |
| `apps/web/app/games/experience/[experienceId]/play/page.tsx` | MC gameplay UI (may be new file for this game) |
| `apps/web/app/games/experience/[experienceId]/leaderboard/page.tsx` | Party Mode fool scoring display |

---

## Decisions

| Decision | Rationale |
|----------|-----------|
| Reuse `ExperienceInstance` | Follows established pattern; extends with new states + main_person_participant_id |
| Separate `game_choices` + `game_mc_guesses` tables | Fundamentally different from Who Knows Who's participant-guessing; MC selection needs choice-level tracking |
| Server-authoritative timer | Frontend countdown is cosmetic; server locks round on poll after 60s expiry |
| No WebSocket yet | Matches existing polling architecture; can upgrade later without restructuring |
| Host ≠ Main Person allowed | Host can select any participant (including self) as main person |
| Main person does NOT guess | Simplest MVP — excluded from gameplay rounds |
| Intimacy levels in question bank | Simple tag-based filtering; no LLM question generation in MVP |
| Normalized answers via LLM | Include normalization in distractor generation call for concise display |
| Party Mode self-selection allowed | Show all choices; exclude self-authored from fool scoring in backend (simpler UX) |
| Build Default Mode first | Per spec's MVP recommendation; Party Mode extends naturally afterward |

---

## Build Order

```
Phase 1-2 (Database) ─────────────────────────────┐
                                                    │
Phase 3 (LLM prompts/schemas) ──── parallel ───────┤
Phase 6 (Catalog + question bank) ─ parallel ───────┤
                                                    │
Phase 4-5 (Backend service + state) ───────────────┤─── depends on 1-2
                                                    │
Phase 7 (API routes) ──────────────────────────────┤─── depends on 4-5
                                                    │
Phase 8-9 (Frontend + timer) ──────────────────────┘─── depends on 7
```

**Estimated effort distribution:**
- Phase 1-2: Foundation — must be complete and correct first
- Phase 3+6: Small, self-contained — can be done quickly in parallel
- Phase 4-5: Largest phase — the orchestrator is the core of the game
- Phase 7: Mechanical — follows established patterns exactly
- Phase 8-9: UI-heavy — most user-facing complexity lives here

---

## Verification Checklist

- [ ] All state transitions validated for both modes
- [ ] Timer expiry correctly locks rounds and awards 0 points
- [ ] Main person cannot submit guesses
- [ ] Fake answers matching correct answer are rejected
- [ ] Party Mode fool scoring: +50 per player fooled, no self-fool credit
- [ ] "Who picked what" data returned in reveal payload
- [ ] AI distractor generation produces valid, non-offensive, non-duplicate outputs
- [ ] Review flow allows edit/regenerate/confirm cycle
- [ ] Minimum 2 fake answers enforced (with AI fallback)
- [ ] Replay creates new experience instance with same config
- [ ] Frontend routing handles all state transitions correctly
- [ ] Polling intervals: 2.5s during gameplay, 3s during lobby/setup
- [ ] localStorage persists participant_id across page refreshes
