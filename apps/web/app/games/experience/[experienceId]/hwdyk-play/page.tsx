"use client";

import { useEffect, useState, useCallback } from "react";
import { useParams, useRouter } from "next/navigation";
import {
  getHWDYKState,
  submitMCGuess,
  revealHWDYKRound,
  advanceHWDYKRound,
  getHWDYKLeaderboard,
} from "@/lib/api";

export default function HWDYKPlayPage() {
  const { experienceId } = useParams<{ experienceId: string }>();
  const router = useRouter();

  const [state, setState] = useState<any>(null);
  const [selectedChoice, setSelectedChoice] = useState<string | null>(null);
  const [guessSubmitted, setGuessSubmitted] = useState(false);
  const [guessResult, setGuessResult] = useState<boolean | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [timeLeft, setTimeLeft] = useState(60);

  const participantId =
    typeof window !== "undefined"
      ? localStorage.getItem(`game_pid_${experienceId}`) || ""
      : "";

  const fetchState = useCallback(async () => {
    try {
      const s = await getHWDYKState(experienceId);
      setState(s);

      if (s.game_state === "completed") {
        router.push(`/games/experience/${experienceId}/hwdyk-leaderboard`);
        return;
      }

      if (s.round?.time_remaining_seconds !== undefined) {
        setTimeLeft(s.round.time_remaining_seconds);
      }

      // Reset guess state on new round
      if (s.game_state === "round_active" && s.round) {
        // Check if we already guessed this round (by checking guesses_submitted)
      }
    } catch {}
  }, [experienceId, router]);

  useEffect(() => {
    fetchState();
    const interval = setInterval(fetchState, 2500);
    return () => clearInterval(interval);
  }, [fetchState]);

  // Client-side timer countdown
  useEffect(() => {
    if (!state || state.game_state !== "round_active") return;
    const timer = setInterval(() => {
      setTimeLeft((prev) => Math.max(0, prev - 1));
    }, 1000);
    return () => clearInterval(timer);
  }, [state?.game_state, state?.round?.round_id]);

  // Reset guess state on round change
  useEffect(() => {
    if (state?.game_state === "round_active") {
      setGuessSubmitted(false);
      setGuessResult(null);
      setSelectedChoice(null);
    }
  }, [state?.round?.round_id]);

  async function handleGuess(choiceId: string) {
    if (guessSubmitted || loading) return;
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
    } catch (e: any) {
      setError(e.message);
      setSelectedChoice(null);
    } finally {
      setLoading(false);
    }
  }

  async function handleReveal() {
    try {
      await revealHWDYKRound(experienceId, state.round.round_id);
    } catch (e: any) {
      setError(e.message);
    }
  }

  async function handleAdvance() {
    try {
      const res = await advanceHWDYKRound(experienceId, state.round.round_id);
      if (res.is_last) {
        router.push(`/games/experience/${experienceId}/hwdyk-leaderboard`);
      }
    } catch (e: any) {
      setError(e.message);
    }
  }

  if (!state) {
    return <div className="py-12 text-center text-gray-500">Loading…</div>;
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
            {timeLeft}s
          </div>
        </div>

        {/* Timer bar */}
        <div className="w-full bg-gray-200 dark:bg-gray-700 rounded-full h-2">
          <div
            className={`h-2 rounded-full transition-all duration-1000 ${
              timeLeft <= 10 ? "bg-red-500" : "bg-purple-600"
            }`}
            style={{ width: `${(timeLeft / 60) * 100}%` }}
          />
        </div>

        {/* Question */}
        <h2 className="text-xl font-semibold text-center">{round.question_text}</h2>

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
                disabled={timeLeft === 0}
                className={`w-full px-5 py-4 text-left rounded-xl border-2 transition ${
                  selectedChoice === choice.id
                    ? "border-purple-500 bg-purple-50 dark:bg-purple-900/30"
                    : "border-gray-200 dark:border-gray-700 hover:border-purple-300 dark:hover:border-purple-700"
                } ${timeLeft === 0 ? "opacity-50 cursor-not-allowed" : ""}`}
              >
                {choice.text}
              </button>
            ))}
            {timeLeft === 0 && (
              <p className="text-center text-red-500 font-medium">Time's up!</p>
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
          <h2 className="text-xl font-semibold mt-2">{round.question_text}</h2>
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
