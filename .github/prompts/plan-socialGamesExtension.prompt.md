## Plan: Social Games Extension — Who Knows Who

Extend TBQH with a multiplayer social games framework, starting with "Who Knows Who." Reuses existing Group, Participant, Session, ExperienceInstance, PromptInstance/Response, PlayerAction, ScoreSnapshot, and EventLog models. Adds game state columns to `experience_instances`, new `game_rounds` and `game_guesses` tables, a static question bank, 5 backend services, 13 API endpoints, and 6 new frontend pages. Polling-based sync for MVP.

---

### Phase 1: Schema & Migration

1. **Create migration** `002_social_games.py` — all schema changes in one file:
   - Add to `experience_instances`: `game_state` (TEXT, CHECK enum), `current_round` (INT, default 0), `max_rounds` (INT), `game_config` (JSONB), `started_at`, `completed_at`, `parent_experience_instance_id` (self-FK). Update `experience_type` CHECK to include `'who_knows_who'`.
   - Add to `prompt_instances`: `experience_instance_id` (FK → experience_instances), `round_number` (INT, nullable)
   - New table `game_rounds`: id, experience_instance_id (FK), round_number, source_prompt_instance_id (FK), source_response_id (FK), answering_participant_id (FK), status (CHECK enum), started_at, revealed_at, created_at
   - New table `game_guesses`: id, game_round_id (FK), guessing_participant_id (FK), guessed_participant_id (FK), is_correct, submitted_at. UNIQUE on (game_round_id, guessing_participant_id)

2. **Update SQLAlchemy models** — modify [experience.py](apps/api/app/db/models/experience.py) and [prompt.py](apps/api/app/db/models/prompt.py) for new columns; create `game_round.py` and `game_guess.py`; update [models/__init__.py](apps/api/app/db/models/__init__.py)

### Phase 2: Backend Services (*depends on Phase 1*)

3. **GameCatalogService** (`services/games/catalog.py`) — hardcoded game registry, `list_games()` and `get_game(slug)`
4. **ShareService** (`services/games/sharing.py`) — `generate_join_code()`, `generate_share_url()`, `validate_join_code()`
5. **GameStateService** (`services/games/state.py`) — state machine transitions dict, `transition_state()` with validation, `get_game_state_payload()` for full state response
6. **WhoKnowsWhoService** (`services/games/who_knows_who.py`) — orchestrates: create_game, join_game, start_answer_collection, check_all_answers_submitted, generate_rounds, submit_guess, reveal_round, advance_round, compute_leaderboard, replay_game
7. **ScoreService** (`services/games/scoring.py`) — compute scores from `game_guesses`, produce leaderboard, optionally persist to existing `score_snapshots` table
8. **Question bank** (`services/games/question_bank.py`) — 30-50 static "about me" questions, `select_questions(count=10)` via `random.sample`

### Phase 3: API Endpoints (*depends on Phase 2*)

9. **Games routes** (`api/v1/routes/games.py`) — 13 endpoints:

   | Method | Path | Purpose |
   |--------|------|---------|
   | GET | `/games` | List available games |
   | POST | `/games/{slug}/create` | Create game (group + session + experience) |
   | POST | `/games/{slug}/join` | Join via code |
   | GET | `/experiences/{id}/lobby` | Lobby state + participants |
   | POST | `/experiences/{id}/start` | Host starts answer collection |
   | GET | `/experiences/{id}/prompts` | Get self-answer prompts |
   | POST | `/experiences/{id}/prompts/answer` | Submit free-text answer |
   | GET | `/experiences/{id}/state` | Full game state (polled) |
   | POST | `/experiences/{id}/rounds/{rid}/guess` | Submit guess |
   | POST | `/experiences/{id}/rounds/{rid}/reveal` | Reveal round |
   | POST | `/experiences/{id}/rounds/{rid}/advance` | Advance to next round |
   | GET | `/experiences/{id}/leaderboard` | Final scores |
   | POST | `/experiences/{id}/replay` | Create new game with same group |

10. **Mount router** in [main.py](apps/api/app/main.py); add event logging calls for all 12 game event types

### Phase 4: Frontend (*parallel with Phase 3 after API client*)

11. **Extend API client** — add 13 functions to [api.ts](apps/web/lib/api.ts) (*parallel with step 9*)
12. **Update home page** [page.tsx](apps/web/app/page.tsx) — add "Play Social Games" button
13. **Game selection page** `apps/web/app/games/page.tsx` — fetch games, render cards
14. **Create/Join page** `apps/web/app/games/[slug]/page.tsx` — two-path UI (create or enter join code)
15. **Lobby page** `apps/web/app/games/experience/[experienceId]/lobby/page.tsx` — polls every 3s, shows participants, join code, share link, host start button
16. **Self-answer page** `apps/web/app/games/experience/[experienceId]/questions/page.tsx` — free-text prompts, progress bar, waits for all players
17. **Gameplay page** `apps/web/app/games/experience/[experienceId]/play/page.tsx` — round display, guess buttons (disabled for answer owner), reveal panel with vote distribution, host advance button
18. **Leaderboard page** `apps/web/app/games/experience/[experienceId]/leaderboard/page.tsx` — ranked list, winner highlight, "Play Again" and "Choose Another Game" buttons

### Phase 5: Hardening (*depends on Phases 3-4*)

19. **Backend tests** `tests/test_games.py` — create, join, answer, generate rounds, guess, reveal, leaderboard, replay
20. **Edge case tests** `tests/test_games_edge_cases.py` — no join after lobby, min 2 players, no double guess, blank answer rejection, answer owner excluded
21. **Manual E2E test** — full flow across two browsers

---

### Relevant Files

**Modify:**
- [apps/api/app/db/models/experience.py](apps/api/app/db/models/experience.py) — add 7 columns to `ExperienceInstance`
- [apps/api/app/db/models/prompt.py](apps/api/app/db/models/prompt.py) — add `experience_instance_id`, `round_number` to `PromptInstance`
- [apps/api/app/db/models/__init__.py](apps/api/app/db/models/__init__.py) — export `GameRound`, `GameGuess`
- [apps/api/app/main.py](apps/api/app/main.py) — mount games router
- [apps/web/lib/api.ts](apps/web/lib/api.ts) — add 13 API functions
- [apps/web/app/page.tsx](apps/web/app/page.tsx) — add games CTA button

**Create (backend — 12 files):**
- `apps/api/app/db/migrations/versions/002_social_games.py`
- `apps/api/app/db/models/game_round.py`, `game_guess.py`
- `apps/api/app/services/games/__init__.py`, `catalog.py`, `sharing.py`, `state.py`, `who_knows_who.py`, `scoring.py`, `question_bank.py`
- `apps/api/app/api/v1/routes/games.py`
- `apps/api/app/tests/test_games.py`, `test_games_edge_cases.py`

**Create (frontend — 6 files):**
- `apps/web/app/games/page.tsx`
- `apps/web/app/games/[slug]/page.tsx`
- `apps/web/app/games/experience/[experienceId]/lobby/page.tsx`
- `apps/web/app/games/experience/[experienceId]/questions/page.tsx`
- `apps/web/app/games/experience/[experienceId]/play/page.tsx`
- `apps/web/app/games/experience/[experienceId]/leaderboard/page.tsx`

---

### Verification

1. `alembic upgrade head` succeeds; `alembic check` shows no drift
2. `pytest apps/api/app/tests/test_games.py apps/api/app/tests/test_games_edge_cases.py -v` — all pass
3. Swagger UI at `/docs` lists all 13 new endpoints with correct request/response schemas
4. `docker compose up` — all services healthy
5. Manual E2E: create game → join from 2nd browser tab → answer questions → play 10 rounds → leaderboard → replay
6. `SELECT event_type, COUNT(*) FROM event_log WHERE event_type LIKE 'game_%' GROUP BY event_type` — confirms all event types logged

---

### Decisions

- **Polling (2-3s) over WebSockets** — MVP simplicity; server-side state allows WebSocket upgrade later without restructuring
- **Single migration file** — all schema changes are one atomic feature
- **Static question bank** — 30-50 hardcoded questions; AI generation is a future enhancement
- **Answer owner cannot guess** on their own round; UI shows informational message
- **Host-only controls** — host starts game and advances rounds; host can rejoin if disconnected
- **No component library** — continue inline Tailwind matching existing frontend style
- **Reuse existing `score_snapshots`** table from `game_scaffold.py`; authoritative scores derived from `game_guesses`
- **No late joiners** — join only in lobby state
- **Defaults: 10 questions, 10 rounds** — configurable via `game_config` JSONB
