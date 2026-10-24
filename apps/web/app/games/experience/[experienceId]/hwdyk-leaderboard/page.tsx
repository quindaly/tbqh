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
    return <div className="py-12 text-center text-gray-500">We couldn't find that game.</div>;
  }

  if (loading) {
    return <div className="py-12 text-center text-gray-500">Loading…</div>;
  }

  const iAmBack = next.returned.includes(participantId);

  const getMedal = (rank: number) => {
    if (rank === 1) return "🥇";
    if (rank === 2) return "🥈";
    if (rank === 3) return "🥉";
    return `${rank}.`;
  };

  return (
    <div className="max-w-lg mx-auto py-12 space-y-8">
      <div className="text-center space-y-2">
        <h1 className="text-3xl font-bold">Game Over!</h1>
      </div>

      {/* Leaderboard */}
      <div className="space-y-3">
        {scores.map((entry) => (
          <div
            key={entry.participant_id}
            className={`flex items-center justify-between px-5 py-4 rounded-xl border-2 transition ${
              entry.participant_id === participantId
                ? "border-purple-400 bg-purple-50 dark:bg-purple-900/20 dark:border-purple-700"
                : "border-gray-200 dark:border-gray-700"
            }`}
          >
            <div className="flex items-center gap-3">
              <span className="text-xl">{getMedal(entry.rank)}</span>
              <div>
                <span className="font-medium">{entry.display_name}</span>
                {entry.participant_id === participantId && (
                  <span className="ml-2 text-xs text-purple-500">(you)</span>
                )}
                <div className="text-xs text-gray-500 mt-0.5">
                  {entry.correct_count} correct
                  {(entry.fool_count ?? 0) > 0 && (
                    <> · fooled {entry.fool_count}</>
                  )}
                </div>
              </div>
            </div>
            <span className="text-lg font-bold text-purple-600">
              {entry.score}
            </span>
          </div>
        ))}
      </div>

      {error && <p className="text-red-500 text-sm text-center">{error}</p>}

      {/* Actions */}
      <div className="space-y-3">
        {next.id && next.state === "lobby" && (
          <p className="text-center text-sm text-gray-500" role="status">
            {next.returned.length} of {next.total} back in the lobby
          </p>
        )}
        {missedIt && (
          <p className="text-center text-sm text-gray-500" role="status">
            The next game has already started. You can join the one after it.
          </p>
        )}
        {participantId ? (
          <button
            onClick={handleReturn}
            disabled={returning || missedIt}
            className="w-full px-6 py-3 bg-purple-600 text-white rounded-lg hover:bg-purple-700 transition disabled:opacity-50"
          >
            {returning ? "Going back…" : iAmBack ? "Go to the lobby" : "Return to Lobby"}
          </button>
        ) : (
          <p className="text-center text-sm text-gray-500">
            Open the game from the link you used to join to play again.
          </p>
        )}
        <a
          href="/games"
          className="block w-full text-center px-6 py-3 border border-gray-300 dark:border-gray-600 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-800 transition"
        >
          Back to Games
        </a>
      </div>
    </div>
  );
}
