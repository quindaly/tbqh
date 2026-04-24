0) Product scope for MVP
MVP user flows
1.	Host signs in (magic link) → creates a Group (solo by default) + Session
2.	Host enters free-text group description
3.	Backend (LLM) extracts structured signals and generates follow-up MC questions (each includes “Other (type your own)”)
4.	Host answers follow-ups (optionally invites a Guest who may join anonymously or sign in)
5.	System builds a GroupProfile (versioned) and computes an embedding
6.	System retrieves candidate discussion questions from dataset via embeddings + filters (policy + blocklists)
7.	System selects 10 questions = mix of top similarity + explore bucket + diversity constraints
8.	Questions shown one-by-one; each participant can Like / Dislike / Skip
o	Like → saved to favorites for that user
o	Dislike → permanently block for that user (hard filter forever)
9.	Host can click “Get 10 more” using same GroupProfile (no re-intake) with configurable knobs.
MVP admin/backoffice
•	Seed questions dataset (import script)
•	Offline AI labeling job (optional in MVP but schema supports it)
 
1) High-level architecture (services & responsibilities)
Frontend (Web first)
•	Next.js (App Router) + React
•	Auth UI (magic link) + “Join as guest”
•	Session lobby + follow-up flow + question presentation + feedback buttons
•	“Get 10 more” trigger with config controls (simple advanced panel)
Backend API (monolith to start)
•	Node (NestJS) or Python (FastAPI). Pick one; both work.
•	Responsibilities:
o	Auth & session mgmt
o	LLM orchestration (intake parsing, follow-ups, rewording)
o	Embedding + similarity retrieval
o	Ranking/mixing/diversity
o	Safety policy enforcement
o	Event logging & feedback persistence
Data layer
•	Postgres (primary store)
•	Vector search:
o	Either pgvector in Postgres (simplest)
o	or external vector DB (Pinecone/Weaviate) later
•	Redis (optional) for ephemeral session state / rate limiting
AI providers
•	LLM for:
o	intake extraction + follow-up generation
o	optional rewording
o	offline labeling (later)
•	Embeddings model for:
o	group profile embedding
o	question embedding
Realtime (not MVP, but enabled)
•	Plan for WebSocket channels keyed by experience_instance_id
•	For MVP: poll-based “live scores” is not required, but schema supports game actions.
 
2) Domain model (entities)
Core
•	User (authenticated account)
•	Group (persistent grouping; can be solo)
•	Participant (person in a group/session; may map to User or be anonymous)
•	Session (a gathering instance; ties participants + policy profile)
•	PolicyProfile (family-friendly now; extensible categories later)
Profile + AI intake
•	GroupProfile (versioned representation of group; reusable for reruns)
•	PromptTemplate (system prompts for follow-ups, trivia intake later)
•	PromptInstance (a generated follow-up question shown to a participant)
•	PromptResponse (MC selection + optional free text)
Content & recommendations
•	QuestionItem (your human-authored discussion dataset)
•	ContentItem (generic “thing shown” — discussion question now, quiz question later)
•	RecommendationRun (implemented as an ExperienceInstance with type discussion_recs)
•	ContentExposure (what was shown, when, to whom)
Feedback & analytics
•	UserQuestionFeedback (like/dislike/skip + permanent block)
•	EventLog (append-only event stream)
Future games (scaffold now)
•	ExperienceInstance (type: discussion_recs, personal_trivia, etc.)
•	PlayerAction (answers/guesses/buzzes)
•	ScoreSnapshot (optional; can also be derived)
 
3) Database schema (Postgres + pgvector)
Use UUIDs everywhere. Add created_at/updated_at where relevant.
3.1 Auth & identity
users
•	id uuid pk
•	email text unique
•	created_at timestamptz
groups
•	id uuid pk
•	created_by_user_id uuid fk users(id)
•	name text null
•	created_at timestamptz
participants
•	id uuid pk
•	group_id uuid fk groups(id)
•	user_id uuid fk users(id) null
•	display_name text
•	role text check in ('host','guest')
•	join_type text check in ('authenticated','anonymous')
•	created_at timestamptz
3.2 Sessions & policy
policy_profiles
•	id uuid pk
•	name text (e.g., 'family_friendly')
•	excluded_categories text[] (extensible)
•	created_at timestamptz
sessions
•	id uuid pk
•	group_id uuid fk groups(id)
•	policy_profile_id uuid fk policy_profiles(id)
•	status text check in ('active','ended')
•	created_at timestamptz
•	ended_at timestamptz null
session_participants
•	session_id uuid fk sessions(id)
•	participant_id uuid fk participants(id)
•	pk (session_id, participant_id)
3.3 GroupProfile (re-run support)
group_profiles
•	id uuid pk
•	group_id uuid fk groups(id)
•	source_free_text text
•	derived_attributes jsonb (LLM-extracted: vibe, topics, constraints, etc.)
•	embedding vector(1536) (size depends on your embeddings model)
•	version int
•	is_active boolean
•	created_at timestamptz
Index:
•	ivfflat or hnsw index on embedding (pgvector)
•	group_id, is_active
3.4 AI follow-ups (generic prompts/responses)
prompt_templates
•	id uuid pk
•	name text (e.g., 'group_followups_v1')
•	template text (system prompt)
•	created_at timestamptz
prompt_instances
•	id uuid pk
•	session_id uuid fk sessions(id)
•	group_profile_id uuid fk group_profiles(id) null (null while building profile)
•	participant_id uuid fk participants(id) null (who it was asked to; host initially)
•	prompt_type text (e.g., 'group_followup', 'trivia_subject_intake')
•	prompt_text text
•	options jsonb (array of options; include “Other”)
•	allow_other boolean default true
•	created_at timestamptz
prompt_responses
•	id uuid pk
•	prompt_instance_id uuid fk prompt_instances(id)
•	participant_id uuid fk participants(id)
•	selected_option text null
•	other_text text null
•	normalized_value text null (optional)
•	created_at timestamptz
3.5 Question dataset (human-authored)
question_items
•	id uuid pk
•	question_text text
•	embedding vector(1536)
•	status text check in ('active','retired') default 'active'
•	content_categories text[] (for safety; AI-labeled offline later)
•	topics text[] (optional)
•	audience_fit text[] (optional)
•	depth_level int null
•	created_at timestamptz
Index:
•	vector index on embedding
•	gin index on content_categories, topics
3.6 Generic content items (what gets shown)
content_items
•	id uuid pk
•	content_type text (e.g., 'discussion_question', 'quiz_question')
•	source_question_item_id uuid fk question_items(id) null (for discussion questions)
•	text text
•	metadata jsonb (e.g., quiz correct answer, distractors later)
•	created_at timestamptz
For MVP, you can skip content_items and show question_items directly, but I strongly recommend including it so games don’t fork everything.
3.7 Experience instances (discussion run + future games)
experience_instances
•	id uuid pk
•	session_id uuid fk sessions(id)
•	group_profile_id uuid fk group_profiles(id)
•	experience_type text (e.g., 'discussion_recs', 'personal_trivia')
•	config jsonb (knobs: top_k, explore_count, explore_policy, diversity, etc.)
•	status text check in ('active','completed')
•	created_at timestamptz
content_exposures
•	id uuid pk
•	experience_instance_id uuid fk experience_instances(id)
•	content_item_id uuid fk content_items(id)
•	shown_to_participant_id uuid fk participants(id) null (null = shown to group)
•	position int
•	shown_at timestamptz
Index:
•	(experience_instance_id, content_item_id) unique to prevent duplicates in a run
3.8 Feedback & blocklists
user_question_feedback
•	id uuid pk
•	participant_id uuid fk participants(id) (or user_id if you want cross-group; keep participant for MVP)
•	user_id uuid fk users(id) null (if signed-in; helps cross-group personalization later)
•	question_item_id uuid fk question_items(id)
•	feedback text check in ('like','dislike','skip')
•	created_at timestamptz
Hard block rule:
•	Any dislike creates a block. Implement as:
o	either query feedback table for dislikes
o	or materialize in a separate table for speed:
user_question_blocklist (optional)
•	user_id uuid fk users(id)
•	question_item_id uuid fk question_items(id)
•	pk (user_id, question_item_id)
If user is anonymous guest, store blocklist under participant_id and migrate later if they sign in.
3.9 Events (append-only)
event_log
•	id uuid pk
•	session_id uuid
•	experience_instance_id uuid null
•	participant_id uuid null
•	event_type text
•	payload jsonb
•	created_at timestamptz
Event types:
•	session_created
•	participant_joined
•	group_text_submitted
•	followup_prompt_generated
•	followup_answered
•	group_profile_created
•	recommendation_generated
•	content_shown
•	feedback_given
•	get_more_clicked
3.10 Game scaffolding (later)
player_actions
•	id uuid pk
•	experience_instance_id uuid
•	participant_id uuid
•	action_type text (guess_submitted, answered, etc.)
•	payload jsonb
•	created_at timestamptz
score_snapshots
•	id uuid pk
•	experience_instance_id uuid
•	payload jsonb (scores by participant)
•	created_at timestamptz
 
4) API design (REST; agent can implement)
All endpoints under /api/v1.
4.1 Auth
•	POST /auth/magic-link {email}
•	GET /auth/callback?token=...
•	POST /auth/logout
4.2 Group/session lifecycle
•	POST /groups → creates group + host participant
•	POST /sessions {group_id, policy_profile_id} → returns session_id + join_code
•	POST /sessions/{session_id}/join {join_code, display_name, join_mode: 'anonymous'|'authenticated'}
o	If authenticated, attaches user_id to participant.
•	GET /sessions/{session_id} → session details + participants
4.3 Intake + follow-ups
•	POST /sessions/{session_id}/group-text {text}
o	creates a provisional group_profile record (version+1, is_active=false)
o	triggers follow-up generation (sync or background job)
•	GET /sessions/{session_id}/followups → list prompt_instances (MC options)
•	POST /sessions/{session_id}/followups/answer
o	{prompt_instance_id, selected_option, other_text}
•	POST /sessions/{session_id}/group-profile/commit
o	finalizes derived_attributes + embedding, sets is_active=true, updates others to inactive
o	returns group_profile_id
4.4 Generate recommendations (Experience instance)
•	POST /sessions/{session_id}/experiences
o	body: {group_profile_id, experience_type:'discussion_recs', config}
o	returns experience_instance_id and first batch
•	POST /experiences/{experience_id}/recommendations
o	generates (or regenerates) a batch of 10
o	respects:
	policy constraints
	blocklists
	exclude previously shown in this group_profile (default true)
o	returns list of content_items with ids
•	POST /experiences/{experience_id}/more
o	same as above, with possibly new config overrides
o	returns next 10
4.5 Presentation + feedback
•	GET /experiences/{experience_id}/next?cursor=... (optional; can just send all 10 upfront)
•	POST /content/{content_item_id}/feedback
o	{experience_id, participant_id, feedback: like|dislike|skip}
o	side effects:
	if dislike → add to blocklist (user_id if exists else participant_id scoped)
	if like → save to favorites
•	GET /users/me/favorites
•	GET /users/me/blocked
 
5) AI orchestration (prompt contracts)
5.1 Intake extraction prompt (server-side)
Input: free text group description + policy profile + (optionally) previous group_profile derived_attributes
Output (JSON):
•	group_summary
•	audience_context (friends/coworkers/family/strangers guess)
•	desired_vibe (e.g., playful, reflective)
•	depth_preference (1–5)
•	avoid_topics (based on policy + user implied)
•	followup_needed boolean
•	followup_question_specs[] (see below)
5.2 Follow-up generation prompt
Generate 3–8 MC questions (bounded). Each question:
•	id (client-side temp id)
•	prompt_text
•	options (4–8)
•	include "Other (type your own)"
•	answer_type: single_select (MVP)
•	why_needed (for debugging)
Persist each as prompt_instance.
5.3 GroupProfile synthesis prompt
Once follow-ups answered:
Input: free text + all responses
Output JSON (derived_attributes):
•	summary
•	key_traits (array)
•	topics_of_interest (array)
•	constraints (array)
•	vibe
•	depth
•	audience_context
•	language
•	safety_mode (policy profile)
This becomes derived_attributes and is embedded.
5.4 Rewording prompt (optional, constrained)
Input: candidate question text + derived_attributes summary
Output:
•	reworded_question OR null (if no change)
Rules:
•	preserve meaning
•	keep human tone
•	no sensitive categories under policy
Persist rewording decision in content_items.text and metadata {original_question_item_id, reworded:true}.
 
6) Embeddings & retrieval
6.1 What gets embedded
•	Each question_items.question_text → question_items.embedding
•	Each group_profiles representation:
o	embed source_free_text + normalized followup answers + derived summary
6.2 Candidate retrieval query (pgvector)
•	get top K (e.g., 200) question_items by cosine similarity to group_profile.embedding
•	filter:
o	status='active'
o	safety: content_categories not overlapping policy exclusions
o	blocklist: remove any disliked by user(s)
Multi-participant note: for MVP, treat blocklist as:
•	union of any signed-in user dislikes in the session
•	plus anonymous participant dislikes scoped to that participant
Configurable later.
 
7) Ranking, diversity, and explore mix (the “10 questions” algorithm)
Define knobs in experience_instances.config:
{
  "batch_size": 10,
  "candidate_k": 200,
  "top_similarity_n": 7,
  "explore_n": 3,
  "explore_policy": "popular|random|diverse",
  "exclude_previously_shown": true,
  "rewording_enabled": true,
  "diversity": {
    "max_per_topic": 2,
    "min_topic_coverage": 4
  }
}
7.1 Steps
1.	Retrieve top candidate_k by similarity
2.	Remove blocked (hard)
3.	If exclude_previously_shown:
o	remove any question_items already used in any prior discussion_recs experience for this group_profile_id
4.	Build Top Similarity set:
o	take top_similarity_n after diversity constraints
5.	Build Explore set size explore_n:
o	Policy popular: sample from globally high-like-rate but still safe + not blocked
o	Policy random: random safe pool excluding blocked + shown
o	Policy diverse: pick from topics not represented in similarity set
6.	Combine → 10
7.	For each selected question_item:
o	create a content_item (type discussion_question)
o	optionally reword
8.	Create content_exposures rows for ordering and tracking
9.	Return list to client
 
8) “Get 10 more” / reruns
Two user intents:
1.	Same group profile, more questions (no re-intake):
o	Create a new experience_instance (type discussion_recs) referencing the same group_profile_id OR reuse the same experience_instance and just call /more.
o	I recommend: new experience_instance per batch request only if you want clean audit; otherwise keep single experience and append exposures.
o	Simpler: single experience instance and /more appends additional exposures.
2.	Update group profile and rerun:
o	start new group_profile version
o	future recs point to new group_profile_id
 
9) Safety policy (family-friendly now, extensible later)
9.1 Policy enforcement points
•	Follow-up generation prompt: include policy profile and forbidden categories
•	GroupProfile synthesis: ensure no sensitive expansions
•	Retrieval filter: exclude any question_items tagged with restricted categories
•	Rewording: ensure no policy violations
9.2 Dataset tagging
Even if your dataset starts as just question_text, create columns now:
•	content_categories text[]
Then provide a CLI job:
•	label_questions.py:
o	LLM assigns categories and a boolean family_friendly_ok
o	store categories
MVP can start with all categories empty + rely on LLM guardrails, but you’ll get better guarantees if you run labeling early.
 
10) Guest identity rules (auth optional)
•	Guest joins session:
o	if anonymous: create Participant with user_id=null
o	if authenticated: attach user_id
•	Feedback storage:
o	If user_id exists → store in user_question_blocklist and user_question_feedback
o	Else store feedback linked to participant_id only
•	If anonymous later signs in:
o	add endpoint POST /participants/{participant_id}/claim to attach a user_id and migrate blocklist/favorites.
 
11) Observability & evaluation hooks (build in early)
•	Log every LLM call in event_log with:
o	model name
o	prompt_template_id
o	latency
o	token usage (if available)
o	safety mode
•	Log recommendation decisions:
o	similarity scores (store in payload; not necessarily as columns)
o	chosen explore policy and selections
•	This will let you tune:
o	explore_count
o	diversity constraints
o	follow-up count
 
12) Implementation plan (sequence for agentic coding model)
Phase 1: Foundations
1.	Repo setup: Next.js + Backend (FastAPI/Nest) + Postgres + pgvector
2.	Auth: magic link, user table
3.	Core tables: groups, participants, sessions, policy_profiles
4.	Session creation + join (anonymous or auth)
Phase 2: Intake & GroupProfile
5.	UI: free-text group description
6.	Backend: LLM intake extraction + follow-up generation
7.	Persist prompt_instances + prompt_responses
8.	Synthesize GroupProfile + compute embedding + persist
Phase 3: Question dataset + retrieval
9.	Import script for question_items
10.	Embedding pipeline for question_items
11.	Vector search query + filtering
Phase 4: Ranking + delivery
12.	Implement experience_instances + content_items + exposures
13.	Implement recommendation algorithm (top similarity + explore + diversity)
14.	Optional constrained rewording
Phase 5: UX + feedback loop
15.	Show questions one-by-one
16.	Like/Dislike/Skip endpoints
17.	Favorites + blocklist behavior
18.	“Get 10 more” endpoint + UI controls
Phase 6: Hardening
19.	Basic analytics dashboard endpoints (top liked, most disliked, etc.)
20.	Safety policy toggle wiring end-to-end
21.	Rate limiting + caching (optional)
Phase 7 (Later): Social games scaffolding → personal trivia
22.	Implement personal_trivia experience_type with:
•	subject intake prompts
•	quiz synthesis to content_items (quiz_question)
•	player_actions + scoring
23.	Add realtime updates (WS) on experience_instance channels
 
13) Non-functional requirements (guardrails)
•	Privacy: group profiles may contain personal data; encrypt at rest if needed; at minimum restrict access by session membership.
•	Prompt injection: treat free-text as untrusted; enforce strict JSON outputs; validate and sanitize.
•	Determinism: store all configs + model versions per run for reproducibility.
•	Cost controls: cap follow-ups (3–8), cap candidate_k, cache embeddings.
