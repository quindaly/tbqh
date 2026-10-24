/**
 * API client for communicating with the FastAPI backend.
 */

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000/api/v1";

/**
 * Error thrown for any failed API call. `status` is the HTTP status, or 0 when
 * the request never got a response (offline, DNS failure, blocked by CORS).
 */
export class ApiError extends Error {
  status: number;
  /** Machine-readable reason from the server (e.g. "stale_revision"), if given. */
  code?: string;

  constructor(message: string, status: number, code?: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
  }
}

/** Turn FastAPI's `detail` (string, {code,message}, or validation list) into text. */
function describeDetail(detail: unknown): { message?: string; code?: string } {
  if (typeof detail === "string") return { message: detail };
  if (Array.isArray(detail)) {
    const msgs = detail
      .map((d) => (d && typeof d === "object" && "msg" in d ? String((d as any).msg) : ""))
      .filter(Boolean);
    return { message: msgs.join("; ") || undefined };
  }
  if (detail && typeof detail === "object") {
    const d = detail as { message?: unknown; code?: unknown };
    return {
      message: typeof d.message === "string" ? d.message : undefined,
      code: typeof d.code === "string" ? d.code : undefined,
    };
  }
  return {};
}

async function apiFetch<T>(
  path: string,
  options: RequestInit = {}
): Promise<T> {
  const url = `${API_BASE}${path}`;
  let res: Response;
  try {
    res = await fetch(url, {
      credentials: "include",
      headers: {
        "Content-Type": "application/json",
        ...(options.headers || {}),
      },
      ...options,
    });
  } catch {
    throw new ApiError("Can't reach the server. Check your connection.", 0);
  }
  if (!res.ok) {
    const body = await res.json().catch(() => ({ error: res.statusText }));
    const { message, code } = describeDetail(body.detail);
    throw new ApiError(
      message || body.error || `API error ${res.status}`,
      res.status,
      code
    );
  }
  return res.json();
}

// ---- Auth ----

export async function requestMagicLink(email: string) {
  return apiFetch<{ ok: boolean }>("/auth/magic-link", {
    method: "POST",
    body: JSON.stringify({ email }),
  });
}

export async function getMe() {
  return apiFetch<{ id: string; email: string }>("/auth/me");
}

export async function logout() {
  return apiFetch<{ ok: boolean }>("/auth/logout", { method: "POST" });
}

export async function createGuestSession() {
  return apiFetch<{
    user_id: string;
    group_id: string;
    session_id: string;
    participant_id: string;
    join_code: string;
  }>("/auth/guest", { method: "POST" });
}

// ---- Groups ----

export async function createGroup(name?: string) {
  return apiFetch<{ group_id: string; host_participant_id: string }>("/groups", {
    method: "POST",
    body: JSON.stringify({ name }),
  });
}

// ---- Policies ----

export async function listPolicies() {
  return apiFetch<{
    policies: { id: string; name: string; excluded_categories: string[] }[];
  }>("/policies");
}

// ---- Sessions ----

export async function createSession(groupId: string, policyProfileId: string) {
  return apiFetch<{ session_id: string; join_code: string }>("/sessions", {
    method: "POST",
    body: JSON.stringify({ group_id: groupId, policy_profile_id: policyProfileId }),
  });
}

export async function getSession(sessionId: string) {
  return apiFetch<{
    id: string;
    group_id: string;
    policy_profile: { id: string; name: string; excluded_categories: string[] };
    status: string;
    participants: {
      id: string;
      user_id: string | null;
      display_name: string;
      role: string;
      join_type: string;
    }[];
  }>(`/sessions/${sessionId}`);
}

export async function joinSession(
  sessionId: string,
  joinCode: string,
  displayName: string,
  joinMode: "anonymous" | "authenticated"
) {
  return apiFetch<{ participant_id: string; session_id: string; group_id: string }>(
    `/sessions/${sessionId}/join`,
    {
      method: "POST",
      body: JSON.stringify({
        join_code: joinCode,
        display_name: displayName,
        join_mode: joinMode,
      }),
    }
  );
}

// ---- Intake ----

export async function submitGroupText(
  sessionId: string,
  text: string,
  participantId: string
) {
  return apiFetch<{
    provisional_group_profile_id: string;
    followups_created: number;
  }>(`/sessions/${sessionId}/group-text`, {
    method: "POST",
    body: JSON.stringify({ text, participant_id: participantId }),
  });
}

export async function getFollowups(sessionId: string) {
  return apiFetch<{
    prompts: {
      id: string;
      prompt_type: string;
      prompt_text: string;
      options: string[];
      allow_other: boolean;
    }[];
  }>(`/sessions/${sessionId}/followups`);
}

export async function answerFollowup(
  sessionId: string,
  promptInstanceId: string,
  participantId: string,
  selectedOption: string | null,
  otherText: string | null
) {
  return apiFetch<{ ok: boolean }>(`/sessions/${sessionId}/followups/answer`, {
    method: "POST",
    body: JSON.stringify({
      prompt_instance_id: promptInstanceId,
      participant_id: participantId,
      selected_option: selectedOption,
      other_text: otherText,
    }),
  });
}

// ---- Profiles ----

export async function commitGroupProfile(
  sessionId: string,
  provisionalGroupProfileId: string
) {
  return apiFetch<{ group_profile_id: string; version: number }>(
    `/sessions/${sessionId}/group-profile/commit`,
    {
      method: "POST",
      body: JSON.stringify({
        provisional_group_profile_id: provisionalGroupProfileId,
      }),
    }
  );
}

// ---- Experiences ----

export async function createExperience(
  sessionId: string,
  groupProfileId: string,
  experienceType: string = "discussion_recs",
  config?: Record<string, unknown>
) {
  return apiFetch<{ experience_instance_id: string }>(
    `/sessions/${sessionId}/experiences`,
    {
      method: "POST",
      body: JSON.stringify({
        group_profile_id: groupProfileId,
        experience_type: experienceType,
        config,
      }),
    }
  );
}

export async function getRecommendations(
  experienceId: string,
  batchSize: number = 10,
  configOverrides?: Record<string, unknown>
) {
  return apiFetch<{
    content_items: {
      id: string;
      content_type: string;
      text: string;
      metadata: Record<string, unknown>;
    }[];
  }>(`/experiences/${experienceId}/recommendations`, {
    method: "POST",
    body: JSON.stringify({
      batch_size: batchSize,
      config_overrides: configOverrides,
    }),
  });
}

export async function getMoreRecommendations(
  experienceId: string,
  batchSize: number = 10,
  configOverrides?: Record<string, unknown>
) {
  return apiFetch<{
    content_items: {
      id: string;
      content_type: string;
      text: string;
      metadata: Record<string, unknown>;
    }[];
  }>(`/experiences/${experienceId}/more`, {
    method: "POST",
    body: JSON.stringify({
      batch_size: batchSize,
      config_overrides: configOverrides,
    }),
  });
}

// ---- Feedback ----

export async function submitFeedback(
  contentItemId: string,
  experienceInstanceId: string,
  participantId: string,
  feedback: "like" | "dislike" | "skip"
) {
  return apiFetch<{ ok: boolean }>(`/content/${contentItemId}/feedback`, {
    method: "POST",
    body: JSON.stringify({
      experience_instance_id: experienceInstanceId,
      participant_id: participantId,
      feedback,
    }),
  });
}

// ---- User lists ----

export async function getFavorites() {
  return apiFetch<{
    question_items: {
      question_item_id: string;
      question_text: string;
      liked_at: string;
    }[];
  }>("/users/me/favorites");
}

export async function getBlocked() {
  return apiFetch<{
    question_items: {
      question_item_id: string;
      question_text: string;
      blocked_at: string;
    }[];
  }>("/users/me/blocked");
}

// ---- Games ----

export async function listGames() {
  return apiFetch<{
    games: {
      id: string;
      slug: string;
      display_name: string;
      description: string;
      status: string;
    }[];
  }>("/games");
}

export async function createGame(gameSlug: string, displayName: string) {
  return apiFetch<{
    group_id: string;
    session_id: string;
    experience_instance_id: string;
    participant_id: string;
    join_code: string;
    share_url: string;
  }>(`/games/${gameSlug}/create`, {
    method: "POST",
    body: JSON.stringify({ display_name: displayName }),
  });
}

export async function joinGame(
  gameSlug: string,
  joinCode: string,
  displayName: string,
  joinMode: string = "anonymous"
) {
  return apiFetch<{
    participant_id: string;
    session_id: string;
    experience_instance_id: string;
  }>(`/games/${gameSlug}/join`, {
    method: "POST",
    body: JSON.stringify({
      join_code: joinCode,
      display_name: displayName,
      join_mode: joinMode,
    }),
  });
}

export async function getLobby(experienceId: string) {
  return apiFetch<{
    experience_id: string;
    game_state: string;
    game_slug: string;
    join_code: string;
    share_url: string;
    host_id: string | null;
    participants: { id: string; display_name: string; role: string }[];
  }>(`/experiences/${experienceId}/lobby`);
}

export async function startCollection(experienceId: string, participantId: string) {
  return apiFetch<{ prompts_created: number }>(`/experiences/${experienceId}/start`, {
    method: "POST",
    body: JSON.stringify({ participant_id: participantId }),
  });
}

export async function getGamePrompts(experienceId: string) {
  return apiFetch<{
    prompts: { id: string; prompt_text: string; prompt_type: string }[];
  }>(`/experiences/${experienceId}/prompts`);
}

export async function submitGameAnswer(
  experienceId: string,
  promptInstanceId: string,
  participantId: string,
  answerText: string
) {
  return apiFetch<{ ok: boolean; all_submitted: boolean }>(
    `/experiences/${experienceId}/prompts/answer`,
    {
      method: "POST",
      body: JSON.stringify({
        prompt_instance_id: promptInstanceId,
        participant_id: participantId,
        answer_text: answerText,
      }),
    }
  );
}

export async function getGameState(experienceId: string) {
  return apiFetch<{
    experience_id: string;
    experience_type: string;
    game_state: string;
    current_round: number;
    max_rounds: number;
    participants: { id: string; display_name: string; role: string }[];
    round?: {
      round_id: string;
      round_number: number;
      status: string;
      question_text: string;
      answer_text: string;
      answering_participant_id: string;
      answering_participant_name?: string;
      guesses?: {
        guessing_participant_id: string;
        guessed_participant_id: string;
        is_correct: boolean;
      }[];
    };
    scores?: {
      participant_id: string;
      display_name: string;
      score: number;
      rank: number;
    }[];
  }>(`/experiences/${experienceId}/state`);
}

export async function submitGuess(
  experienceId: string,
  roundId: string,
  guessingParticipantId: string,
  guessedParticipantId: string
) {
  return apiFetch<{ ok: boolean; is_correct: boolean; all_guessed: boolean }>(
    `/experiences/${experienceId}/rounds/${roundId}/guess`,
    {
      method: "POST",
      body: JSON.stringify({
        guessing_participant_id: guessingParticipantId,
        guessed_participant_id: guessedParticipantId,
      }),
    }
  );
}

export async function revealRound(experienceId: string, roundId: string) {
  return apiFetch<{ ok: boolean }>(
    `/experiences/${experienceId}/rounds/${roundId}/reveal`,
    { method: "POST" }
  );
}

export async function advanceRound(experienceId: string, roundId: string) {
  return apiFetch<{ ok: boolean; is_last: boolean }>(
    `/experiences/${experienceId}/rounds/${roundId}/advance`,
    { method: "POST" }
  );
}

export async function getLeaderboard(experienceId: string) {
  return apiFetch<{
    leaderboard: {
      participant_id: string;
      display_name: string;
      score: number;
      rank: number;
    }[];
  }>(`/experiences/${experienceId}/leaderboard`);
}

export async function replayGame(experienceId: string) {
  return apiFetch<{
    experience_instance_id: string;
    join_code: string;
    share_url: string;
  }>(`/experiences/${experienceId}/replay`, { method: "POST" });
}

// ---- How Well Do You Know [Person]? ----

export async function createHWDYKGame(
  displayName: string,
  mode: "default" | "party",
  numQuestions: number = 5
) {
  return apiFetch<{
    group_id: string;
    session_id: string;
    experience_instance_id: string;
    participant_id: string;
    join_code: string;
    share_url: string;
  }>("/games/how-well-do-you-know/create", {
    method: "POST",
    body: JSON.stringify({
      display_name: displayName,
      mode,
      num_questions: numQuestions,
    }),
  });
}

export async function joinHWDYKGame(
  joinCode: string,
  displayName: string,
  joinMode: string = "anonymous"
) {
  return apiFetch<{
    participant_id: string;
    session_id: string;
    experience_instance_id: string;
  }>("/games/how-well-do-you-know/join", {
    method: "POST",
    body: JSON.stringify({
      join_code: joinCode,
      display_name: displayName,
      join_mode: joinMode,
    }),
  });
}

/** Countdown for a timed phase, as measured by the server when it replied. */
export interface PhaseInfo {
  name: string;
  seconds_remaining: number;
  duration_seconds: number;
  deadline_at: string;
  server_now: string;
}

export async function getHWDYKLobby(experienceId: string) {
  return apiFetch<{
    experience_id: string;
    game_state: string;
    state_version: number;
    phase: PhaseInfo | null;
    progress: { answered: number; total: number } | null;
    notice: { code: string; message: string } | null;
    game_slug: string;
    mode: string;
    join_code: string;
    share_url: string;
    host_id: string | null;
    main_person_participant_id: string | null;
    participants: { id: string; display_name: string; role: string }[];
  }>(`/experiences/${experienceId}/hwdyk/lobby`);
}

export async function selectMainPerson(
  experienceId: string,
  hostParticipantId: string,
  mainPersonParticipantId: string
) {
  return apiFetch<{ ok: boolean }>(
    `/experiences/${experienceId}/select-main-person`,
    {
      method: "POST",
      body: JSON.stringify({
        host_participant_id: hostParticipantId,
        main_person_participant_id: mainPersonParticipantId,
      }),
    }
  );
}

export async function startHWDYKSetup(experienceId: string, participantId: string) {
  return apiFetch<{ prompts_created: number }>(
    `/experiences/${experienceId}/start-setup`,
    {
      method: "POST",
      body: JSON.stringify({ participant_id: participantId }),
    }
  );
}

export async function getMainPersonQuestions(experienceId: string) {
  return apiFetch<{
    game_state: string;
    phase: PhaseInfo | null;
    questions: {
      id: string;
      prompt_text: string;
      round_number: number;
      answered: boolean;
    }[];
  }>(`/experiences/${experienceId}/main-person-questions`);
}

export async function submitMainPersonAnswer(
  experienceId: string,
  promptInstanceId: string,
  participantId: string,
  answerText: string
) {
  return apiFetch<{ ok: boolean; all_answered: boolean }>(
    `/experiences/${experienceId}/main-person-answer`,
    {
      method: "POST",
      body: JSON.stringify({
        prompt_instance_id: promptInstanceId,
        participant_id: participantId,
        answer_text: answerText,
      }),
    }
  );
}

export async function getReviewChoices(experienceId: string, participantId: string) {
  return apiFetch<{
    game_state: string;
    phase: PhaseInfo | null;
    rounds: {
      round_id: string;
      round_number: number;
      question_text: string;
      choices: {
        id: string;
        text: string;
        is_correct: boolean;
        source_type: string;
        revision: number;
        regenerations_used: number;
      }[];
    }[];
  }>(`/experiences/${experienceId}/review-choices?participant_id=${participantId}`);
}

export async function editChoice(
  experienceId: string,
  choiceId: string,
  participantId: string,
  newText: string,
  expectedRevision?: number
) {
  return apiFetch<{ ok: boolean; id: string; text: string; revision: number }>(
    `/experiences/${experienceId}/choices/${choiceId}/edit`,
    {
      method: "POST",
      body: JSON.stringify({
        participant_id: participantId,
        new_text: newText,
        expected_revision: expectedRevision,
      }),
    }
  );
}

export async function regenerateChoice(
  experienceId: string,
  choiceId: string,
  participantId: string,
  expectedRevision?: number
) {
  return apiFetch<{
    id: string;
    new_text: string;
    text: string;
    revision: number;
    regenerations_used: number;
    regenerations_remaining: number;
  }>(`/experiences/${experienceId}/choices/${choiceId}/regenerate`, {
    method: "POST",
    body: JSON.stringify({
      participant_id: participantId,
      expected_revision: expectedRevision,
    }),
  });
}

export async function confirmChoices(
  experienceId: string,
  participantId: string,
  revisions?: Record<string, number>
) {
  return apiFetch<{ ok: boolean }>(
    `/experiences/${experienceId}/confirm-choices`,
    {
      method: "POST",
      body: JSON.stringify({ participant_id: participantId, revisions }),
    }
  );
}

export async function getFakeAnswerQuestions(
  experienceId: string,
  participantId: string
) {
  return apiFetch<{
    questions: {
      round_id: string;
      question_text: string;
      round_number: number;
      already_submitted: boolean;
    }[];
  }>(`/experiences/${experienceId}/fake-answer-questions?participant_id=${participantId}`);
}

export async function submitFakeAnswer(
  experienceId: string,
  roundId: string,
  participantId: string,
  fakeText: string
) {
  return apiFetch<{ ok: boolean }>(`/experiences/${experienceId}/fake-answer`, {
    method: "POST",
    body: JSON.stringify({
      round_id: roundId,
      participant_id: participantId,
      fake_text: fakeText,
    }),
  });
}

export async function getFakeAnswerProgress(experienceId: string) {
  return apiFetch<{
    rounds: { round_id: string; round_number: number; fake_count: number }[];
    players: {
      participant_id: string;
      display_name: string;
      submitted_count: number;
      total: number;
    }[];
  }>(`/experiences/${experienceId}/fake-answer-progress`);
}

export async function lockPartyMode(experienceId: string, participantId: string) {
  return apiFetch<{ ok: boolean }>(
    `/experiences/${experienceId}/lock-party-mode`,
    {
      method: "POST",
      body: JSON.stringify({ participant_id: participantId }),
    }
  );
}

export async function startLiveGame(experienceId: string, participantId: string) {
  return apiFetch<{ ok: boolean }>(`/experiences/${experienceId}/start-live`, {
    method: "POST",
    body: JSON.stringify({ participant_id: participantId }),
  });
}

export async function getHWDYKState(experienceId: string) {
  return apiFetch<{
    experience_id: string;
    experience_type: string;
    game_state: string;
    state_version: number;
    mode: string;
    current_round: number;
    max_rounds: number;
    main_person_participant_id: string | null;
    participants: { id: string; display_name: string; role: string }[];
    round?: {
      round_id: string;
      round_number: number;
      status: string;
      question_text: string;
      question_text_self?: string;
      /** Server-measured seconds left in the guessing window. */
      seconds_remaining: number;
      time_remaining_seconds: number;
      duration_seconds: number;
      eligible_participant_ids: string[];
      guessed_participant_ids: string[];
      is_locked: boolean;
      guesses_submitted: number;
      total_guessers: number;
      choices: {
        id: string;
        text: string;
        is_correct?: boolean;
        source_type?: string;
        created_by_participant_id?: string | null;
      }[];
      distribution?: {
        choice_id: string;
        choice_text: string;
        is_correct: boolean;
        guessers: string[];
      }[];
    };
    scores?: {
      participant_id: string;
      display_name: string;
      score: number;
      correct_count: number;
      fool_count?: number;
      rank: number;
    }[];
  }>(`/experiences/${experienceId}/hwdyk/state`);
}

export async function submitMCGuess(
  experienceId: string,
  roundId: string,
  participantId: string,
  choiceId: string
) {
  return apiFetch<{ ok: boolean; is_correct: boolean; all_guessed: boolean }>(
    `/experiences/${experienceId}/rounds/${roundId}/mc-guess`,
    {
      method: "POST",
      body: JSON.stringify({
        participant_id: participantId,
        choice_id: choiceId,
      }),
    }
  );
}

export async function revealHWDYKRound(experienceId: string, roundId: string) {
  return apiFetch<{ ok: boolean }>(
    `/experiences/${experienceId}/rounds/${roundId}/hwdyk-reveal`,
    { method: "POST" }
  );
}

export async function advanceHWDYKRound(experienceId: string, roundId: string) {
  return apiFetch<{ ok: boolean; is_last: boolean; advanced: boolean }>(
    `/experiences/${experienceId}/rounds/${roundId}/hwdyk-advance`,
    { method: "POST" }
  );
}

export async function getHWDYKLeaderboard(experienceId: string) {
  return apiFetch<{
    leaderboard: {
      participant_id: string;
      display_name: string;
      score: number;
      correct_count: number;
      fool_count?: number;
      rank: number;
    }[];
    next_experience_id?: string | null;
  }>(`/experiences/${experienceId}/hwdyk/leaderboard`);
}

export async function replayHWDYKGame(experienceId: string) {
  return apiFetch<{
    experience_instance_id: string;
    join_code: string;
    share_url: string;
  }>(`/experiences/${experienceId}/hwdyk/replay`, { method: "POST" });
}
