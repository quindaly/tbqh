"use client";

import { useState, useCallback } from "react";
import { useParams, useRouter } from "next/navigation";
import {
  getGameState,
  submitGuess,
  revealRound,
  advanceRound,
} from "@/lib/api";
import { usePolling } from "@/lib/usePolling";
import { Eyebrow, Heading, PrimaryButton } from "../../../../_components/ui";
import {
  ConnectionBanner,
  LobbyNotFound,
  LobbyUnreachable,
} from "../../../_components/LobbyStatus";

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
  is_yours: boolean;
  you_guessed: boolean;
  guessed_count: number;
  guesser_count: number;
  answering_participant_id?: string;
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
  const [maxRounds, setMaxRounds] = useState(0);
  const [participants, setParticipants] = useState<ParticipantInfo[]>([]);
  const [round, setRound] = useState<RoundInfo | null>(null);
  const [scores, setScores] = useState<ScoreInfo[]>([]);
  // The round this device has already guessed in, so the buttons stay away
  // between tapping a name and the server's next reply.
  const [guessedRoundId, setGuessedRoundId] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");

  // Read straight away (not in an effect) so the first load already knows who
  // is looking. null if this device never joined.
  const [participantId] = useState<string | null>(() =>
    typeof window === "undefined" ? null : localStorage.getItem(`game_pid_${experienceId}`)
  );

  // Throws on failure so usePolling can back off and stop on a missing game.
  const fetchState = useCallback(async () => {
    const data = await getGameState(experienceId, participantId);
    setGameState(data.game_state);
    setMaxRounds(data.max_rounds);
    setParticipants(data.participants);
    setRound(data.round || null);
    setScores(data.scores || []);

    if (data.game_state === "leaderboard" || data.game_state === "completed") {
      router.push(`/games/experience/${experienceId}/leaderboard`);
    }
  }, [experienceId, participantId, router]);

  const { failures, fatal, gaveUp, retry } = usePolling(fetchState, { baseMs: 2500 });

  async function handleGuess(guessedId: string) {
    if (!participantId || !round) return;
    setSubmitting(true);
    setError("");
    try {
      await submitGuess(experienceId, round.round_id, participantId, guessedId);
      setGuessedRoundId(round.round_id);
      void fetchState().catch(() => {});
    } catch (e: any) {
      // Already guessed (another tab, or a retry): treat it as done.
      if (/already guessed/i.test(e.message)) {
        setGuessedRoundId(round.round_id);
      } else {
        setError(e.message);
      }
    } finally {
      setSubmitting(false);
    }
  }

  async function handleReveal() {
    if (!round || !participantId) return;
    setError("");
    try {
      await revealRound(experienceId, round.round_id, participantId);
      void fetchState().catch(() => {});
    } catch (e: any) {
      setError(e.message);
    }
  }

  async function handleAdvance() {
    if (!round || !participantId) return;
    setError("");
    try {
      const res = await advanceRound(experienceId, round.round_id, participantId);
      if (res.is_last) {
        router.push(`/games/experience/${experienceId}/leaderboard`);
      } else {
        void fetchState().catch(() => {});
      }
    } catch (e: any) {
      setError(e.message);
    }
  }

  const isPlayer = !!participantId && participants.some((p) => p.id === participantId);
  const isHost = isPlayer && participants.find((p) => p.role === "host")?.id === participantId;

  if (fatal) {
    return <LobbyNotFound />;
  }

  if (!round) {
    return gaveUp ? (
      <LobbyUnreachable onRetry={retry} />
    ) : (
      <p className="text-center py-16 text-muted">Loading round…</p>
    );
  }

  const myScore = scores.find((s) => s.participant_id === participantId)?.score;

  // ---- Round Active ----
  if (gameState === "round_active") {
    const hasGuessed = round.you_guessed || guessedRoundId === round.round_id;
    const everyoneGuessed = round.guesser_count > 0 && round.guessed_count >= round.guesser_count;
    const canReveal = isHost || (isPlayer && everyoneGuessed);
    // You never guess yourself, so you are not an option.
    const options = participants.filter((p) => p.id !== participantId);

    return (
      <div className="max-w-md mx-auto flex flex-col gap-6 py-8">
        {failures > 0 && <ConnectionBanner gaveUp={gaveUp} onRetry={retry} />}
        <div className="flex items-baseline justify-between">
          <Eyebrow>
            Round {round.round_number} of {maxRounds}
          </Eyebrow>
          {isPlayer && myScore !== undefined && (
            <span className="text-sm text-muted tabular-nums">Your score: {myScore}</span>
          )}
        </div>

        {/* Question + answer */}
        <div className="flex flex-col gap-4">
          <Heading size={28}>{round.question_text}</Heading>
          <div className="border-l-2 border-accent pl-4">
            <p className="text-xs uppercase tracking-[0.14em] text-muted mb-1">Someone answered</p>
            <p className="font-serif text-[24px] leading-[1.25]">
              &ldquo;{round.answer_text}&rdquo;
            </p>
          </div>
        </div>

        {!isPlayer ? (
          <p className="text-center text-muted">You&apos;re watching this game.</p>
        ) : round.is_yours ? (
          <div className="rounded-md border border-soft bg-surface p-4 text-center text-muted">
            <p className="text-ink font-medium">This round is based on your answer</p>
            <p className="text-sm">Sit back and watch the others guess.</p>
          </div>
        ) : hasGuessed ? (
          <div className="rounded-md border border-soft bg-surface p-4 text-center text-muted">
            <p>Guess locked in. Waiting for the others…</p>
          </div>
        ) : (
          <div className="flex flex-col gap-2">
            <p className="text-xs uppercase tracking-[0.14em] text-muted">Who wrote this?</p>
            {options.map((p) => (
              <button
                key={p.id}
                onClick={() => handleGuess(p.id)}
                disabled={submitting}
                className="w-full px-4 min-h-[56px] rounded-md border border-soft bg-surface hover:border-accent hover:bg-selected transition text-left text-[17px] disabled:opacity-50"
              >
                {p.display_name}
              </button>
            ))}
          </div>
        )}

        <p className="text-center text-sm text-muted tabular-nums">
          {round.guessed_count} of {round.guesser_count} guessed
        </p>

        {error && (
          <p role="alert" className="text-red-500 text-sm">
            {error}
          </p>
        )}

        {canReveal && (
          <PrimaryButton onClick={handleReveal}>
            {everyoneGuessed ? "Everyone has guessed. Reveal" : "Reveal answer"}
          </PrimaryButton>
        )}
      </div>
    );
  }

  // ---- Round Reveal ----
  if (gameState === "round_reveal") {
    const ownerName =
      round.answering_participant_name ||
      participants.find((p) => p.id === round.answering_participant_id)?.display_name;
    return (
      <div className="max-w-md mx-auto flex flex-col gap-6 py-8">
        {failures > 0 && <ConnectionBanner gaveUp={gaveUp} onRetry={retry} />}
        <Eyebrow>
          Round {round.round_number} of {maxRounds}
        </Eyebrow>

        <div className="flex flex-col gap-3">
          <Heading size={28}>{round.question_text}</Heading>
          <p className="font-serif text-[24px] leading-[1.25]">&ldquo;{round.answer_text}&rdquo;</p>
          <div className="border-t border-soft pt-3">
            <p className="text-xs uppercase tracking-[0.14em] text-muted">Written by</p>
            <p className="font-serif text-[28px] leading-tight text-accent">{ownerName}</p>
          </div>
        </div>

        {/* Vote distribution */}
        {round.guesses && round.guesses.length > 0 && (
          <div className="flex flex-col gap-2">
            <h2 className="text-xs uppercase tracking-[0.14em] text-muted font-normal">
              Who guessed what
            </h2>
            {round.guesses.map((g) => {
              const guesser = participants.find((p) => p.id === g.guessing_participant_id);
              const guessed = participants.find((p) => p.id === g.guessed_participant_id);
              return (
                <div
                  key={g.guessing_participant_id}
                  className={`flex justify-between items-center px-3 min-h-[48px] rounded-md border ${
                    g.is_correct
                      ? "border-green-300 bg-green-50 dark:bg-green-900/20"
                      : "border-soft bg-surface"
                  }`}
                >
                  <span>{guesser?.display_name}</span>
                  <span className="text-sm text-muted">
                    {guessed?.display_name} {g.is_correct ? "✓" : "✗"}
                  </span>
                </div>
              );
            })}
          </div>
        )}

        {/* Scores */}
        {scores.length > 0 && (
          <div className="flex flex-col">
            <h2 className="text-xs uppercase tracking-[0.14em] text-muted font-normal mb-2">
              Scores
            </h2>
            <ul className="border-t border-soft">
              {scores.map((s) => (
                <li
                  key={s.participant_id}
                  className="flex justify-between items-center border-b border-soft min-h-[44px]"
                >
                  <span>{s.display_name}</span>
                  <span className="tabular-nums">{s.score}</span>
                </li>
              ))}
            </ul>
          </div>
        )}

        {error && (
          <p role="alert" className="text-red-500 text-sm">
            {error}
          </p>
        )}

        {isHost ? (
          <PrimaryButton onClick={handleAdvance}>
            {round.round_number >= maxRounds ? "Show final scores" : "Next round"}
          </PrimaryButton>
        ) : (
          <p className="text-center text-muted text-sm">Waiting for the host to continue…</p>
        )}
      </div>
    );
  }

  return <p className="text-center py-16 text-muted">Loading…</p>;
}
