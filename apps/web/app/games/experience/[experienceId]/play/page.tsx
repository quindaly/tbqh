"use client";

import { useEffect, useState, useCallback } from "react";
import { useParams, useRouter } from "next/navigation";
import {
  getGameState,
  submitGuess,
  revealRound,
  advanceRound,
} from "@/lib/api";

interface ParticipantInfo {
  id: string;
  display_name: string;
  role: string;
}

interface RoundInfo {
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
}

interface ScoreInfo {
  participant_id: string;
  display_name: string;
  score: number;
  rank: number;
}

export default function PlayPage() {
  const { experienceId } = useParams<{ experienceId: string }>();
  const router = useRouter();

  const [gameState, setGameState] = useState("");
  const [currentRound, setCurrentRound] = useState(0);
  const [maxRounds, setMaxRounds] = useState(0);
  const [participants, setParticipants] = useState<ParticipantInfo[]>([]);
  const [round, setRound] = useState<RoundInfo | null>(null);
  const [scores, setScores] = useState<ScoreInfo[]>([]);
  const [guessSubmitted, setGuessSubmitted] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");

  const [participantId, setParticipantId] = useState<string | null>(null);

  useEffect(() => {
    setParticipantId(localStorage.getItem(`game_pid_${experienceId}`));
  }, [experienceId]);

  const fetchState = useCallback(async () => {
    try {
      const data = await getGameState(experienceId);
      setGameState(data.game_state);
      setCurrentRound(data.current_round);
      setMaxRounds(data.max_rounds);
      setParticipants(data.participants);
      setRound(data.round || null);
      setScores(data.scores || []);

      if (data.game_state === "leaderboard" || data.game_state === "completed") {
        router.push(`/games/experience/${experienceId}/leaderboard`);
      }

      // Reset guess state on new round
      if (data.round && data.game_state === "round_active") {
        const alreadyGuessed = data.round.guesses?.some(
          (g) => g.guessing_participant_id === participantId
        );
        setGuessSubmitted(!!alreadyGuessed);
      }
      if (data.game_state === "round_reveal") {
        setGuessSubmitted(false);
      }
    } catch {}
  }, [experienceId, participantId, router]);

  useEffect(() => {
    fetchState();
    const interval = setInterval(fetchState, 2500);
    return () => clearInterval(interval);
  }, [fetchState]);

  async function handleGuess(guessedId: string) {
    if (!participantId || !round) return;
    setSubmitting(true);
    setError("");
    try {
      await submitGuess(experienceId, round.round_id, participantId, guessedId);
      setGuessSubmitted(true);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setSubmitting(false);
    }
  }

  async function handleReveal() {
    if (!round) return;
    try {
      await revealRound(experienceId, round.round_id);
      fetchState();
    } catch (e: any) {
      setError(e.message);
    }
  }

  async function handleAdvance() {
    if (!round) return;
    try {
      const res = await advanceRound(experienceId, round.round_id);
      if (res.is_last) {
        router.push(`/games/experience/${experienceId}/leaderboard`);
      } else {
        fetchState();
      }
    } catch (e: any) {
      setError(e.message);
    }
  }

  const isHost = participants.find((p) => p.role === "host")?.id === participantId;
  const isAnswerOwner = round?.answering_participant_id === participantId;

  if (!round && gameState !== "round_reveal") {
    return <p className="text-center py-16 text-gray-500">Loading round…</p>;
  }

  // ---- Round Active ----
  if (gameState === "round_active" && round) {
    return (
      <div className="max-w-md mx-auto space-y-6 py-8">
        <div className="flex justify-between items-center">
          <h1 className="text-xl font-bold">Round {round.round_number} / {maxRounds}</h1>
          {scores.length > 0 && (
            <span className="text-sm text-gray-500">
              Your score: {scores.find((s) => s.participant_id === participantId)?.score ?? 0}
            </span>
          )}
        </div>

        {/* Question + answer */}
        <div className="rounded-xl border p-6 space-y-3">
          <p className="text-sm text-gray-500 uppercase tracking-wide">Question</p>
          <p className="text-lg font-medium">{round.question_text}</p>
          <div className="border-t pt-3">
            <p className="text-sm text-gray-500 uppercase tracking-wide">Someone answered</p>
            <p className="text-lg italic">&ldquo;{round.answer_text}&rdquo;</p>
          </div>
        </div>

        {isAnswerOwner ? (
          <div className="text-center py-4 text-gray-500 dark:text-gray-400">
            <p className="font-medium">This round is based on your answer!</p>
            <p className="text-sm">Sit back and watch the others guess.</p>
          </div>
        ) : guessSubmitted ? (
          <div className="text-center py-4 text-gray-500">
            <p>Guess submitted! Waiting for others…</p>
          </div>
        ) : (
          <div className="space-y-2">
            <p className="text-sm font-semibold text-gray-600 dark:text-gray-300">
              Who said this?
            </p>
            {participants.map((p) => (
              <button
                key={p.id}
                onClick={() => handleGuess(p.id)}
                disabled={submitting}
                className="w-full px-4 py-3 rounded-lg border hover:border-purple-500 hover:bg-purple-50 dark:hover:bg-purple-900/20 transition text-left disabled:opacity-50"
              >
                {p.display_name}
              </button>
            ))}
          </div>
        )}

        {error && <p className="text-red-500 text-sm">{error}</p>}

        {isHost && (
          <button
            onClick={handleReveal}
            className="w-full px-6 py-3 bg-purple-600 text-white rounded-lg hover:bg-purple-700 transition"
          >
            Reveal Answer
          </button>
        )}
      </div>
    );
  }

  // ---- Round Reveal ----
  if (gameState === "round_reveal" && round) {
    return (
      <div className="max-w-md mx-auto space-y-6 py-8">
        <h1 className="text-xl font-bold text-center">
          Round {round.round_number} — Reveal
        </h1>

        <div className="rounded-xl border p-6 space-y-3">
          <p className="text-lg font-medium">{round.question_text}</p>
          <p className="italic">&ldquo;{round.answer_text}&rdquo;</p>
          <div className="border-t pt-3">
            <p className="text-sm text-gray-500">Answer by:</p>
            <p className="text-lg font-bold text-purple-600">
              {round.answering_participant_name ||
                participants.find((p) => p.id === round.answering_participant_id)
                  ?.display_name}
            </p>
          </div>
        </div>

        {/* Vote distribution */}
        {round.guesses && round.guesses.length > 0 && (
          <div className="space-y-2">
            <h2 className="font-semibold">Who guessed what</h2>
            {round.guesses.map((g) => {
              const guesser = participants.find(
                (p) => p.id === g.guessing_participant_id
              );
              const guessed = participants.find(
                (p) => p.id === g.guessed_participant_id
              );
              return (
                <div
                  key={g.guessing_participant_id}
                  className={`flex justify-between items-center px-3 py-2 rounded-lg border ${
                    g.is_correct
                      ? "border-green-300 bg-green-50 dark:bg-green-900/20"
                      : "border-red-200 bg-red-50 dark:bg-red-900/20"
                  }`}
                >
                  <span>{guesser?.display_name}</span>
                  <span className="text-sm text-gray-500">
                    → {guessed?.display_name} {g.is_correct ? "✓" : "✗"}
                  </span>
                </div>
              );
            })}
          </div>
        )}

        {/* Scores */}
        {scores.length > 0 && (
          <div className="space-y-1">
            <h2 className="font-semibold">Scores</h2>
            {scores.map((s) => (
              <div key={s.participant_id} className="flex justify-between px-3 py-1">
                <span>{s.display_name}</span>
                <span className="font-mono">{s.score}</span>
              </div>
            ))}
          </div>
        )}

        {error && <p className="text-red-500 text-sm">{error}</p>}

        {isHost && (
          <button
            onClick={handleAdvance}
            className="w-full px-6 py-3 bg-purple-600 text-white rounded-lg hover:bg-purple-700 transition"
          >
            {round.round_number >= maxRounds ? "Show Leaderboard" : "Next Round"}
          </button>
        )}

        {!isHost && (
          <p className="text-center text-gray-500 text-sm">
            Waiting for host to continue…
          </p>
        )}
      </div>
    );
  }

  return <p className="text-center py-16 text-gray-500">Loading…</p>;
}
