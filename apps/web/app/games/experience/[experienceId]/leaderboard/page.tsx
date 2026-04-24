"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { getLeaderboard, replayGame } from "@/lib/api";

interface LeaderboardEntry {
  participant_id: string;
  display_name: string;
  score: number;
  rank: number;
}

export default function LeaderboardPage() {
  const { experienceId } = useParams<{ experienceId: string }>();
  const router = useRouter();

  const [entries, setEntries] = useState<LeaderboardEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [replaying, setReplaying] = useState(false);
  const [error, setError] = useState("");

  const [participantId, setParticipantId] = useState<string | null>(null);

  useEffect(() => {
    setParticipantId(localStorage.getItem(`game_pid_${experienceId}`));
  }, [experienceId]);

  useEffect(() => {
    getLeaderboard(experienceId)
      .then((data) => setEntries(data.leaderboard))
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [experienceId]);

  async function handleReplay() {
    setReplaying(true);
    setError("");
    try {
      const res = await replayGame(experienceId);
      localStorage.setItem(`game_pid_${res.experience_instance_id}`, participantId!);
      router.push(`/games/experience/${res.experience_instance_id}/lobby`);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setReplaying(false);
    }
  }

  if (loading) {
    return <p className="text-center py-16 text-gray-500">Loading results…</p>;
  }

  const winner = entries[0];

  return (
    <div className="max-w-md mx-auto space-y-8 py-8">
      <h1 className="text-3xl font-bold text-center">Leaderboard</h1>

      {/* Winner highlight */}
      {winner && (
        <div className="text-center space-y-2">
          <span className="text-5xl">🏆</span>
          <p className="text-2xl font-bold">{winner.display_name}</p>
          <p className="text-gray-500">
            {winner.score} correct guess{winner.score !== 1 ? "es" : ""}
          </p>
        </div>
      )}

      {/* Full rankings */}
      <div className="space-y-2">
        {entries.map((entry) => (
          <div
            key={entry.participant_id}
            className={`flex items-center justify-between px-4 py-3 rounded-lg border ${
              entry.rank === 1
                ? "border-yellow-400 bg-yellow-50 dark:bg-yellow-900/20"
                : entry.rank === 2
                ? "border-gray-400 bg-gray-50 dark:bg-gray-800"
                : entry.rank === 3
                ? "border-orange-300 bg-orange-50 dark:bg-orange-900/20"
                : ""
            } ${entry.participant_id === participantId ? "ring-2 ring-purple-500" : ""}`}
          >
            <div className="flex items-center gap-3">
              <span className="text-lg font-bold w-6 text-center">
                {entry.rank === 1 ? "🥇" : entry.rank === 2 ? "🥈" : entry.rank === 3 ? "🥉" : `${entry.rank}`}
              </span>
              <span className="font-medium">{entry.display_name}</span>
            </div>
            <span className="font-mono text-lg">{entry.score}</span>
          </div>
        ))}
      </div>

      {error && <p className="text-red-500 text-sm">{error}</p>}

      {/* Actions */}
      <div className="flex flex-col gap-3">
        <button
          onClick={handleReplay}
          disabled={replaying}
          className="w-full px-6 py-3 bg-purple-600 text-white rounded-lg hover:bg-purple-700 transition disabled:opacity-50"
        >
          {replaying ? "Creating…" : "Play Again"}
        </button>
        <button
          onClick={() => router.push("/games")}
          className="w-full px-6 py-3 border border-gray-300 dark:border-gray-600 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-800 transition"
        >
          Choose Another Game
        </button>
      </div>
    </div>
  );
}
