# Discussion Questions: audit and LLM context review

What I tested, what I fixed, and what I recommend for the model context. Verified by running the full flow in a browser against a stub model (real model not available in my environment, so retrieval *quality* is reasoned from the code, not measured).

## How it works today

1. **Describe the group** (free text, host only) → one LLM call (`INTAKE_EXTRACTION`) returns a provisional summary plus 3–8 multiple-choice follow-ups. Stored as a *provisional* `GroupProfile` and `PromptInstance` rows.
2. **Answer follow-ups** → one `PromptResponse` per answer.
3. **Commit** → second LLM call (`GROUP_PROFILE_SYNTHESIS`) turns description + Q&A into `summary / key_traits / topics_of_interest / constraints / vibe / depth / audience_context`. A string of `free text | summary | traits | topics` is embedded and stored on the profile, which becomes the group's active profile.
4. **Recommend** → cosine search over `question_items` (top 200), minus questions already shown to this profile and ones anyone in the session disliked, minus the policy's excluded categories. Take 7 by similarity (max 2 per topic) plus 3 "explore" picks from topics not yet covered. Optional LLM rewording (off by default).
5. **Feedback** → like / dislike / skip. Dislike blocks the question. Like feeds Favorites (signed-in or guest-cookie users only).

### Where the questions come from

Not the LLM. The bank is **human-written**: `scripts/general-questions.csv` (215 questions), imported by `scripts/import_questions.py`, labeled offline by `scripts/label_questions.py` (an LLM assigns `content_categories`, `topics`, `audience_fit`, `depth_level`), then embedded by `scripts/embed_questions.py` as `question [categories] [topics] [audience] [depth]`. The live LLM only *interprets the group*; it never writes questions. I read the whole CSV: it's mild (no explicit or inflammatory items; a couple of debate-style ones such as religion and "can a man and woman be just friends").

I exhausted a bank-only group end to end: **215 questions = 22 batches of 10, then nothing**. The page used to go blank at that point.

## Bugs found and fixed in this PR

| # | Problem | Fix |
|---|---|---|
| 1 | Going Back and describing the group again stacked the *old* follow-ups on top of the new ones | Only the newest profile's follow-ups are listed; the API also returns which profile they belong to |
| 2 | Reloading, or Back then forward, answered the same question twice; synthesis saw both answers | One answer per person per question; re-answering replaces it |
| 3 | "Other" was detected with `"other" in text`: **"Weekend get-togethers", "Mother's side" opened the free-text box, and the server skipped adding a real "Other" option** | Exact match on "Other (type your own)", normalised and always last, on server and client |
| 4 | Follow-up order was arbitrary (same timestamp in one transaction) | Stored position keeps the model's order |
| 5 | "Other" with an empty box was accepted and became "(skipped)" | Blocked in the UI and the API |
| 6 | Answers, group text and feedback accepted from anyone who knew a UUID, any value, any length | Must be a session member; option must be a real choice; text trimmed and length-limited |
| 7 | A profile from one group could be committed to or used by another group's session | Profile must belong to the session's group |
| 8 | Reloading the questions page created a new experience, burning 10 unseen questions each time and losing your place | Page remembers its experience and resumes at the first unrated question (`GET /experiences/{id}/items`) |
| 9 | Blank card and `NaN%` progress bar when no questions came back; blank after "Get 10 more" ran dry | Clear empty and "you've seen them all" states (`exhausted` flag) |
| 10 | Asking for batch size 20 silently returned 10; no upper bound | Batch honours the size (same ~70/30 similarity/explore split), bounded 1–30 |
| 11 | Rating twice created duplicate rows; any participant ID could rate any item | One rating per person per question, session members only |
| 12 | Join codes case-sensitive, 8 chars of upper-cased base64 (includes `-`, `_`, O/0) | 6 unambiguous characters, case-insensitive; blank names rejected |
| 13 | Joining meant typing a 36-character session UUID | Invite link with the code filled in; one join form instead of two |
| 14 | Browser kept one global participant/profile slot, so a second session overwrote the first | Remembered per session |
| 15 | LLM calls had no timeout (SDK default is 10 minutes) and raw errors reached the user | 45s timeout (`LLM_TIMEOUT_SECONDS`), friendly 502 "try again" |
| 16 | Guest sessions picked an arbitrary policy (`.first()`) | Prefer `family_friendly` |
| 17 | "👎 Blocked. You won't see this again" over-promised (see open issue 4) | Honest wording: "we won't suggest this one again" |

Lowered temperature on the structured steps (0.7 → 0.4 extraction, 0.3 synthesis) since they return JSON classifications, not prose.

## Open issues I did not change (need your call)

1. **The safety filter almost certainly filters nothing.** The default policy excludes `sexual, violence, drugs, hate_speech`, but the labeler invents free-form categories ("Personal Growth", "Relationships") so they never match. It also **fails open**: unlabeled questions (NULL categories) pass, and `backfill_categories.sql` turns NULL into `{}`, which also passes. The labeler's `family_friendly_ok` answer is thrown away. Low risk with today's tame bank; real risk if the bank grows or comes from elsewhere. (Fix: see recommendation 2.)
2. **Constraints are never applied.** "Keep it PG", "avoid politics" end up in `constraints` and in the embedded text, where they *attract* the topics they name. Nothing reads `constraints` at ranking time.
3. **Joiners get their own copy of the whole flow.** A friend who joins sees the same "describe your group" form, and committing their profile *deactivates the host's*. There's no shared "current questions" for the session, so joining adds little. Most real use is probably one phone read aloud. Options: (a) drop joining from this feature; (b) make the host drive and let joiners view the current question live; (c) leave as is.
4. **Dislikes are per participant row, not per person.** A guest who starts a new session is a new participant, so their dislikes only carry over if they have a user (guest cookie or account). One person's dislike blocks the question for everyone in that session.
5. **No way to unblock or unfavorite** (Favorites / Blocked are read-only lists).
6. **Strict output schemas turn model quirks into errors.** `key_traits` requires ≥3 items; my stub returning two failed validation and the user would have seen the 502. Real models do this occasionally on short descriptions.
7. **Prompt injection.** The group description is interpolated straight into the prompt. Output is schema-validated so the blast radius is small, but there's no instruction-injection guard.
8. **Dead code**: `FOLLOWUP_GENERATION_*` prompts and schema are unused.

## What the model sees (and doesn't)

| Step | Receives | Doesn't receive |
|---|---|---|
| Intake extraction (temp now 0.4) | description, policy name, excluded categories | group size, occasion, time available, previous sessions; no examples; no instruction to skip what the description already answers; asks for 3–8 questions, which is a lot of taps |
| Synthesis (temp 0.3) | description, Q&A, policy name | **the extraction's own vibe/depth/audience guesses**, excluded categories, the bank's actual topic vocabulary |
| Embedding of the group | description, summary, traits, topics | audience and depth in the same `[audience: …][depth: …]` format the *questions* are embedded in |
| Ranking | embedding only | depth, audience, vibe, constraints (all computed, none used) |
| Rewording (off) | summary, traits, one question | vibe, depth, constraints; runs one call per question (10 sequential calls when on) |

## Recommendations, in the order I'd do them

1. **Use what you already compute.** Filter or boost on `depth` (soft window ±1 around the group's depth) and `audience_fit` containing the group's `audience_context`. Order each batch light → deep so a session starts as an icebreaker. No new LLM calls.
2. **Make the safety filter real.** Give the labeler a fixed enum of sensitive tags (the policy's `excluded_categories` plus a few more), store `family_friendly_ok` as a column, and make the query **exclude unlabeled questions** whenever a policy has exclusions.
3. **Apply constraints.** Give synthesis the bank's topic vocabulary (a short list from the DB) and ask for `excluded_topics` chosen from it; filter on those. Keep constraint text out of the embedded string.
4. **Fix the embedding asymmetry.** Build the group string like the question strings: `summary [audience: friends] [topics: …] [depth: deep]`. Re-embed active profiles once.
5. **Add one rerank call.** Retrieve ~30, ask the model to pick 10 given summary, vibe, depth, constraints, with a one-line reason each. Cheaper and more controllable than per-question rewording, and it can enforce variety.
6. **Tighten the intake prompt.** Ask for 3–4 follow-ups; "do not ask what the description already answers"; add one good example; cover relationship length, occasion and desired depth. Pass the extraction into synthesis. On schema failure, retry once with the validation error appended, and relax `minItems` where a short answer is legitimate.
7. **Learn from feedback.** Likes, dislikes and skips already land in `user_question_feedback`. Aggregate per question (like-rate) and use it as a tie-breaker; flag questions with a high dislike rate for review.
8. **Grow and curate the bank.** 215 questions is ~22 batches. Generate candidates offline with the model, then human-review before import so the "all human-written" property holds.
9. **An eval set.** 15–20 group descriptions with a one-line "should feel like / must not include", rerun after each change, read the top 10 by eye. That's the only way to measure whether 1–6 helped.

## Things to check in production

```sql
SELECT count(*) total,
       count(embedding) embedded,
       count(*) FILTER (WHERE content_categories IS NULL OR content_categories = '{}') unlabeled
FROM question_items WHERE status = 'active';

SELECT name, excluded_categories FROM policy_profiles;

SELECT unnest(content_categories) c, count(*) FROM question_items GROUP BY 1 ORDER BY 2 DESC LIMIT 30;
```
If `embedded` is 0 or lower than `total`, recommendations will be empty or thin. The last query shows whether any label matches `sexual / violence / drugs / hate_speech`.

## Deploy notes

No database migration. New optional env var `LLM_TIMEOUT_SECONDS` (default 45). New endpoint `GET /experiences/{id}/items`; `followups` and recommendation responses gained optional fields (`provisional_group_profile_id`, `exhausted`, `feedback`). Web and API can deploy in either order: the new pages tolerate the old API for everything except resume-after-reload.
