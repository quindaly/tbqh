"use client";

import { useCallback, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { ApiError, getHWDYKLeaderboard, returnToHWDYKLobby } from "@/lib/api";
import { usePolling } from "@/lib/usePolling";

interface ScoreEntry {
  participant_id: string;
  display_name: string;
  score: number;
  correct_count: number;
  fool_count?: number;
  rank: number;
}

interface NextGame {
  id: string | null;
  state: string | null;
  returned: string[];
  total: number;
}

export default function HWDYKLeaderboardPage() {
  const { experienceId } = useParams<{ experienceId: string }>();
  const router = useRouter();

  const [scores, setScores] = useState<ScoreEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [next, setNext] = useState<NextGame>({ id: null, state: null, returned: [], total: 0 });
  const [returning, setReturning] = useState(false);
  const [error, setError] = useState("");

  const participantId =
    typeof window !== "undefined"
      ? localStorage.getItem(`game_pid_${experienceId}`) || ""
      : "";

  // Keep the next lobby's headcount fresh. Nobody is moved automatically:
  // each person chooses to come back, and the host starts with whoever did.
  const { fatal } = usePolling(
    useCallback(async () => {
      const res = await getHWDYKLeaderboard(experienceId);
      setScores(res.leaderboard || []);
      setNext({
        id: res.next_experience_id,
        state: res.next_game_state,
        returned: res.returned_ids || [],
        total: res.participant_count || 0,
      });
      setLoading(false);
    }, [experienceId]),
    { baseMs: 3000 }
  );

  // The next game moved on without us (we didn't come back in time).
  const missedIt =
    !!next.id &&
    next.state !== null &&
    next.state !== "lobby" &&
    !next.returned.includes(participantId);

  async function handleReturn() {
    if (!participantId) return;
    setReturning(true);
    setError("");
    try {
      const res = await returnToHWDYKLobby(experienceId, participantId);
      // The lobby recognises this player by their id, kept per game.
      localStorage.setItem(`game_pid_${res.experience_instance_id}`, participantId);
      router.push(`/games/experience/${res.experience_instance_id}/hwdyk-lobby`);
    } catch (e: any) {
      if (e instanceof ApiError && e.code === "game_in_progress") {
        setError(
          "The next game has already started without you. You can join the one after it."
        );
      } else {
        setError(e.message || "Couldn't get back to the lobby. Try again.");
      }
      setReturning(false);
    }
  }

  if (fatal) {
    return <div className="py-12 text-center text-muted">We couldn't find that game.</div>;
  }

  if (loading) {
    return <div className="py-12 text-center text-muted">Loading…</div>;
  }

  const iAmBack = next.returned.includes(participantId);

  const topScore = scores[0]?.score;
  const winners = scores.filter((e) => e.score === topScore);
  const headline =
    scores.length === 0
      ? "Game over"
      : winners.length === 1
      ? `${winners[0].display_name} wins.`
      : "It's a tie.";

  return (
    <div className="max-w-lg mx-auto py-12 space-y-8">
      <div className="space-y-1.5">
        <p className="text-xs uppercase tracking-[0.14em] text-muted">Final scores</p>
        <h1 className="font-serif text-[44px] leading-[1.05] tracking-[-0.01em] font-normal">
          {headline}
        </h1>
      </div>

      {/* Leaderboard */}
      <ol className="border-t border-line">
        {scores.map((entry) => (
          <li
            key={entry.participant_id}
            className="flex items-baseline gap-4 border-b border-soft py-4"
          >
            <span
              className={`w-7 font-serif text-[26px] ${
                entry.rank === 1 ? "text-accent" : "text-muted"
              }`}
            >
              {entry.rank}
            </span>
            <div className="flex-1">
              <span className="font-serif text-[26px] leading-tight">
                {entry.display_name}
              </span>
              {entry.participant_id === participantId && (
                <span className="ml-2 text-xs text-accent">you</span>
              )}
              <div className="text-xs text-muted mt-0.5">
                {entry.correct_count} correct
                {(entry.fool_count ?? 0) > 0 && <> · fooled {entry.fool_count}</>}
              </div>
            </div>
            <span className="text-xl tabular-nums">{entry.score}</span>
          </li>
        ))}
      </ol>

      {error && <p className="text-red-500 text-sm text-center">{error}</p>}

      {/* Actions */}
      <div className="space-y-3">
        {next.id && next.state === "lobby" && (
          <p className="text-center text-sm text-muted" role="status">
            {next.returned.length} of {next.total} back in the lobby
          </p>
        )}
        {missedIt && (
          <p className="text-center text-sm text-muted" role="status">
            The next game has already started. You can join the one after it.
          </p>
        )}
        {participantId ? (
          <button
            onClick={handleReturn}
            disabled={returning || missedIt}
            className="w-full min-h-[56px] px-6 bg-btn text-btn-text rounded-md font-medium hover:opacity-90 transition disabled:opacity-50"
          >
            {returning ? "Going back…" : iAmBack ? "Go to the lobby" : "Return to lobby"}
          </button>
        ) : (
          <p className="text-center text-sm text-muted">
            Open the game from the link you used to join to play again.
          </p>
        )}
        <a
          href="/games"
          className="flex items-center justify-center w-full min-h-[56px] px-6 border border-line rounded-md hover:bg-surface transition"
        >
          Choose another game
        </a>
      </div>
    </div>
  );
}
