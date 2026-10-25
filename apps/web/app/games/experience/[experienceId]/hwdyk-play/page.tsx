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
import { formatClock, useCountdown } from "@/lib/countdown";
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
      <div className="py-12 text-center text-muted">Loading…</div>
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
        <div className="flex items-baseline justify-between">
          <span className="text-xs uppercase tracking-[0.14em] text-muted">
            Round {round.round_number} of {state.max_rounds}
          </span>
          <div
            className={`text-[28px] tabular-nums ${
              timeLeft <= 10 ? "text-red-500 animate-pulse" : "text-accent"
            }`}
          >
            {formatClock(timeLeft)}
          </div>
        </div>

        {/* Timer bar */}
        <div className="w-full bg-soft h-[3px]">
          <div
            className={`h-[3px] transition-all duration-1000 ${
              timeLeft <= 10 ? "bg-red-500" : "bg-accent"
            }`}
            style={{ width: `${Math.min(100, (timeLeft / duration) * 100)}%` }}
          />
        </div>

        {/* Question */}
        <h2 className="font-serif text-[32px] leading-[1.15] tracking-[-0.01em] font-normal">
          {isMainPerson ? round.question_text_self || round.question_text : round.question_text}
        </h2>

        {/* Main person view */}
        {isMainPerson ? (
          <div className="text-center py-8 space-y-2">
            <p className="text-muted">
              Sit back. They're guessing about you.
            </p>
            <p className="text-sm text-muted">
              {round.guesses_submitted} of {round.total_guessers} have guessed
            </p>
            {(isHost || isMainPerson) && (round.is_locked || round.guesses_submitted >= round.total_guessers) && (
              <button
                onClick={handleReveal}
                className="mt-4 min-h-[44px] px-6 bg-btn text-btn-text rounded-md font-medium hover:opacity-90 transition"
              >
                Reveal Answer
              </button>
            )}
          </div>
        ) : guessSubmitted ? (
          <div className="text-center py-8 space-y-2">
            <p className="text-muted">
              Guess locked. Waiting for others…
            </p>
            <p className="text-sm text-muted">
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
                className={`w-full min-h-[56px] px-4 py-3.5 text-left text-[17px] leading-snug rounded-md border transition ${
                  selectedChoice === choice.id
                    ? "border-2 border-accent bg-selected"
                    : "border-soft bg-surface hover:border-accent"
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
            className="w-full min-h-[56px] px-6 bg-btn text-btn-text rounded-md font-medium hover:opacity-90 transition"
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
        <div>
          <span className="text-xs uppercase tracking-[0.14em] text-muted">
            Round {round.round_number} of {state.max_rounds}
          </span>
          <h2 className="font-serif text-[32px] leading-[1.15] tracking-[-0.01em] font-normal mt-2">
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
                className={`px-4 py-3.5 rounded-md ${
                  isCorrect
                    ? "border-2 border-accent bg-selected"
                    : "border border-soft bg-surface"
                }`}
              >
                <div className="flex items-center justify-between">
                  <span className="text-[17px] leading-snug">
                    {choice.text}
                  </span>
                  <span className="text-sm text-muted shrink-0 pl-3">
                    {isCorrect && <span className="text-accent">Correct · </span>}
                    {guessers.length} pick{guessers.length !== 1 ? "s" : ""}
                  </span>
                </div>

                {/* Who picked this */}
                {guessers.length > 0 && (
                  <div className="mt-2 flex flex-wrap gap-1">
                    {guessers.map((pid: string) => (
                      <span
                        key={pid}
                        className={`text-xs px-2 py-1 rounded-md ${
                          isCorrect
                            ? "bg-selected text-accent"
                            : "bg-soft text-muted"
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
                    <p className="mt-1 text-xs text-muted">
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
          <div className="border border-soft bg-surface rounded-md p-4">
            <h3 className="text-xs uppercase tracking-[0.14em] text-muted font-normal mb-3">Scores</h3>
            <div className="space-y-2">
              {state.scores.map((s: any) => (
                <div
                  key={s.participant_id}
                  className={`flex justify-between items-center px-3 py-2 rounded-md ${
                    s.participant_id === participantId
                      ? "bg-selected"
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
            className="w-full min-h-[56px] px-6 bg-btn text-btn-text rounded-md font-medium hover:opacity-90 transition"
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
      <p className="text-muted">Waiting for the game to continue…</p>
      <div aria-hidden="true" className="mx-auto h-2 w-2 rounded-full bg-accent animate-pulse" />
    </div>
  );
}
