"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import {
  ApiError,
  getHWDYKState,
  submitMCGuess,
  revealHWDYKRound,
  advanceHWDYKRound,
} from "@/lib/api";
import { useCountdown } from "@/lib/countdown";
import { usePolling } from "@/lib/usePolling";
import {
  ConnectionBanner,
  LobbyNotFound,
  LobbyUnreachable,
} from "../../../_components/LobbyStatus";

export default function HWDYKPlayPage() {
  const { experienceId } = useParams<{ experienceId: string }>();
  const router = useRouter();

  const [state, setState] = useState<any>(null);
  // When `state` arrived on this device's clock (the countdown is measured from here).
  const [receivedAt, setReceivedAt] = useState(0);
  const lastVersion = useRef(-1);
  const [selectedChoice, setSelectedChoice] = useState<string | null>(null);
  const [guessSubmitted, setGuessSubmitted] = useState(false);
  const [guessResult, setGuessResult] = useState<boolean | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const [participantId] = useState(() =>
    typeof window !== "undefined"
      ? localStorage.getItem(`game_pid_${experienceId}`) || ""
      : ""
  );

  // Throws on failure so usePolling can back off and surface outages.
  const fetchState = useCallback(async () => {
    const s = await getHWDYKState(experienceId);
    // Two polls can overlap; never let an older reply replace a newer state.
    if (s.state_version < lastVersion.current) return;
    lastVersion.current = s.state_version;
    setState(s);
    setReceivedAt(Date.now());

    if (s.game_state === "completed") {
      router.push(`/games/experience/${experienceId}/hwdyk-leaderboard`);
    }
  }, [experienceId, router]);

  const { failures, fatal, gaveUp, retry } = usePolling(fetchState, { baseMs: 2500 });

  // The server owns the clock: count down from the seconds it reported when it
  // replied, so a device with a wrong clock still shows the right time.
  const timeLeft =
    useCountdown(
      state?.game_state === "round_active" && state?.round
        ? { seconds_remaining: state.round.seconds_remaining ?? state.round.time_remaining_seconds }
        : null,
      receivedAt
    ) ?? 0;
  const duration = state?.round?.duration_seconds || 30;

  // New round: clear last round's pick. After a reload, remember a guess we already made.
  const roundId = state?.round?.round_id;
  useEffect(() => {
    if (!state?.round) return;
    const mine = state.round.guessed_participant_ids?.includes(participantId);
    setGuessSubmitted(!!mine);
    if (!mine) {
      setGuessResult(null);
      setSelectedChoice(null);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [roundId]);

  // Someone else's tab (or a reload) may already hold our guess.
  useEffect(() => {
    if (state?.round?.guessed_participant_ids?.includes(participantId)) {
      setGuessSubmitted(true);
    }
  }, [state?.round?.guessed_participant_ids, participantId]);

  async function handleGuess(choiceId: string) {
    if (guessSubmitted || loading || timeLeft <= 0) return;
    setSelectedChoice(choiceId);
    setLoading(true);
    setError("");
    try {
      const res = await submitMCGuess(
        experienceId,
        state.round.round_id,
        participantId,
        choiceId
      );
      setGuessSubmitted(true);
      setGuessResult(res.is_correct);
      void fetchState().catch(() => {});
    } catch (e: any) {
      if (e instanceof ApiError && e.code === "already_guessed") {
        setGuessSubmitted(true);
      } else if (e instanceof ApiError && e.code === "round_closed") {
        // Too late: the round is over for everyone. Show the reveal.
        setSelectedChoice(null);
        void fetchState().catch(() => {});
      } else {
        setSelectedChoice(null);
        setError(e.message || "Couldn't send your guess. Try again.");
      }
    } finally {
      setLoading(false);
    }
  }

  async function handleReveal() {
    try {
      await revealHWDYKRound(experienceId, state.round.round_id, participantId);
      void fetchState().catch(() => {});
    } catch (e: any) {
      setError(e.message);
    }
  }

  async function handleAdvance() {
    try {
      const res = await advanceHWDYKRound(experienceId, state.round.round_id, participantId);
      if (res.is_last) {
        router.push(`/games/experience/${experienceId}/hwdyk-leaderboard`);
      } else {
        void fetchState().catch(() => {});
      }
    } catch (e: any) {
      setError(e.message);
    }
  }

  if (fatal) {
    return <LobbyNotFound />;
  }

  if (!state) {
    return gaveUp ? (
      <LobbyUnreachable onRetry={retry} />
    ) : (
      <div className="py-12 text-center text-gray-500">Loading…</div>
    );
  }

  const isMainPerson = participantId === state.main_person_participant_id;
  const isHost = state.participants?.find(
    (p: any) => p.id === participantId
  )?.role === "host";

  // ROUND ACTIVE
  if (state.game_state === "round_active" && state.round) {
    const round = state.round;

    return (
      <div className="max-w-lg mx-auto py-8 space-y-6">
        {failures > 0 && <ConnectionBanner gaveUp={gaveUp} onRetry={retry} />}
        {/* Header */}
        <div className="flex items-center justify-between">
          <span className="text-sm text-gray-500">
            Round {round.round_number} of {state.max_rounds}
          </span>
          <div
            className={`text-lg font-mono font-bold ${
              timeLeft <= 10 ? "text-red-500 animate-pulse" : "text-gray-700 dark:text-gray-300"
            }`}
          >
            {Math.ceil(timeLeft)}s
          </div>
        </div>

        {/* Timer bar */}
        <div className="w-full bg-gray-200 dark:bg-gray-700 rounded-full h-2">
          <div
            className={`h-2 rounded-full transition-all duration-1000 ${
              timeLeft <= 10 ? "bg-red-500" : "bg-purple-600"
            }`}
            style={{ width: `${Math.min(100, (timeLeft / duration) * 100)}%` }}
          />
        </div>

        {/* Question */}
        <h2 className="text-xl font-semibold text-center">
          {isMainPerson ? round.question_text_self || round.question_text : round.question_text}
        </h2>

        {/* Main person view */}
        {isMainPerson ? (
          <div className="text-center py-8 space-y-2">
            <p className="text-2xl">😎</p>
            <p className="text-gray-500">
              Sit back and relax — they're guessing about you!
            </p>
            <p className="text-sm text-gray-400">
              {round.guesses_submitted} of {round.total_guessers} have guessed
            </p>
            {(isHost || isMainPerson) && (round.is_locked || round.guesses_submitted >= round.total_guessers) && (
              <button
                onClick={handleReveal}
                className="mt-4 px-6 py-2 bg-purple-600 text-white rounded-lg hover:bg-purple-700 transition"
              >
                Reveal Answer
              </button>
            )}
          </div>
        ) : guessSubmitted ? (
          <div className="text-center py-8 space-y-2">
            <p className="text-2xl">{guessResult ? "🎉" : "🤔"}</p>
            <p className="text-gray-500">
              Guess locked! Waiting for others…
            </p>
            <p className="text-sm text-gray-400">
              {round.guesses_submitted} of {round.total_guessers} have guessed
            </p>
          </div>
        ) : (
          <div className="space-y-3">
            {round.choices?.map((choice: any) => (
              <button
                key={choice.id}
                onClick={() => handleGuess(choice.id)}
                disabled={timeLeft <= 0}
                className={`w-full px-5 py-4 text-left rounded-xl border-2 transition ${
                  selectedChoice === choice.id
                    ? "border-purple-500 bg-purple-50 dark:bg-purple-900/30"
                    : "border-gray-200 dark:border-gray-700 hover:border-purple-300 dark:hover:border-purple-700"
                } ${timeLeft <= 0 ? "opacity-50 cursor-not-allowed" : ""}`}
              >
                {choice.text}
              </button>
            ))}
            {timeLeft <= 0 && (
              <p className="text-center text-red-500 font-medium" role="status">
                Time's up!
              </p>
            )}
          </div>
        )}

        {/* Host reveal button */}
        {isHost && !isMainPerson && (round.is_locked || round.guesses_submitted >= round.total_guessers) && (
          <button
            onClick={handleReveal}
            className="w-full px-6 py-3 bg-purple-600 text-white rounded-lg hover:bg-purple-700 transition"
          >
            Reveal Answer
          </button>
        )}

        {error && <p className="text-red-500 text-sm text-center">{error}</p>}
      </div>
    );
  }

  // ROUND REVEAL
  if (state.game_state === "round_reveal" && state.round) {
    const round = state.round;
    const participants = state.participants || [];

    const getPlayerName = (pid: string) =>
      participants.find((p: any) => p.id === pid)?.display_name || "Unknown";

    return (
      <div className="max-w-lg mx-auto py-8 space-y-6">
        <div className="text-center">
          <span className="text-sm text-gray-500">
            Round {round.round_number} of {state.max_rounds}
          </span>
          <h2 className="text-xl font-semibold mt-2">
            {isMainPerson ? round.question_text_self || round.question_text : round.question_text}
          </h2>
        </div>

        {/* Answer distribution */}
        <div className="space-y-3">
          {round.choices?.map((choice: any) => {
            const dist = round.distribution?.find(
              (d: any) => d.choice_id === choice.id
            );
            const guessers = dist?.guessers || [];
            const isCorrect = choice.is_correct;

            return (
              <div
                key={choice.id}
                className={`px-5 py-4 rounded-xl border-2 ${
                  isCorrect
                    ? "border-green-400 bg-green-50 dark:bg-green-900/20 dark:border-green-700"
                    : "border-gray-200 dark:border-gray-700"
                }`}
              >
                <div className="flex items-center justify-between">
                  <span className="font-medium">
                    {isCorrect && "✓ "}
                    {choice.text}
                  </span>
                  <span className="text-sm text-gray-500">
                    {guessers.length} pick{guessers.length !== 1 ? "s" : ""}
                  </span>
                </div>

                {/* Who picked this */}
                {guessers.length > 0 && (
                  <div className="mt-2 flex flex-wrap gap-1">
                    {guessers.map((pid: string) => (
                      <span
                        key={pid}
                        className={`text-xs px-2 py-1 rounded-full ${
                          isCorrect
                            ? "bg-green-100 dark:bg-green-800/40 text-green-700 dark:text-green-300"
                            : "bg-gray-100 dark:bg-gray-800 text-gray-600 dark:text-gray-400"
                        }`}
                      >
                        {getPlayerName(pid)}
                      </span>
                    ))}
                  </div>
                )}

                {/* Party mode: who submitted this fake */}
                {state.mode === "party" &&
                  choice.source_type === "player_fake" &&
                  choice.created_by_participant_id && (
                    <p className="mt-1 text-xs text-gray-400">
                      Submitted by {getPlayerName(choice.created_by_participant_id)}
                      {guessers.length > 0 && ` — fooled ${guessers.length}!`}
                    </p>
                  )}
              </div>
            );
          })}
        </div>

        {/* Scores */}
        {state.scores && state.scores.length > 0 && (
          <div className="border rounded-xl p-4">
            <h3 className="text-sm font-medium text-gray-500 mb-3">Scores</h3>
            <div className="space-y-2">
              {state.scores.map((s: any) => (
                <div
                  key={s.participant_id}
                  className={`flex justify-between items-center px-3 py-2 rounded-lg ${
                    s.participant_id === participantId
                      ? "bg-purple-50 dark:bg-purple-900/20"
                      : ""
                  }`}
                >
                  <span className="text-sm">
                    {s.rank}. {s.display_name}
                  </span>
                  <span className="text-sm font-medium">{s.score} pts</span>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Advance button (host) */}
        {isHost && (
          <button
            onClick={handleAdvance}
            className="w-full px-6 py-3 bg-purple-600 text-white rounded-lg hover:bg-purple-700 transition"
          >
            {round.round_number >= state.max_rounds
              ? "Show Final Scores"
              : "Next Round"}
          </button>
        )}

        {error && <p className="text-red-500 text-sm text-center">{error}</p>}
      </div>
    );
  }

  // Fallback / loading between states
  return (
    <div className="py-12 text-center space-y-4">
      <p className="text-gray-500">Waiting for the game to continue…</p>
      <div className="animate-pulse text-purple-500">●●●</div>
    </div>
  );
}
