"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { getHWDYKLeaderboard, replayHWDYKGame } from "@/lib/api";

interface ScoreEntry {
  participant_id: string;
  display_name: string;
  score: number;
  correct_count: number;
  fool_count?: number;
  rank: number;
}

export default function HWDYKLeaderboardPage() {
  const { experienceId } = useParams<{ experienceId: string }>();
  const router = useRouter();

  const [scores, setScores] = useState<ScoreEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [replaying, setReplaying] = useState(false);
  const [error, setError] = useState("");

  const participantId =
    typeof window !== "undefined"
      ? localStorage.getItem(`game_pid_${experienceId}`) || ""
      : "";

  useEffect(() => {
    getHWDYKLeaderboard(experienceId).then((res) => {
      setScores(res.leaderboard || []);
      setLoading(false);
    }).catch((e) => {
      setError(e.message);
      setLoading(false);
    });
  }, [experienceId]);

  async function handleReplay() {
    setReplaying(true);
    try {
      const res = await replayHWDYKGame(experienceId);
      router.push(`/games/experience/${res.experience_instance_id}/hwdyk-lobby`);
    } catch (e: any) {
      setError(e.message);
      setReplaying(false);
    }
  }

  if (loading) {
    return <div className="py-12 text-center text-gray-500">Loading…</div>;
  }

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
                  {entry.fool_count && entry.fool_count > 0 && (
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
        <button
          onClick={handleReplay}
          disabled={replaying}
          className="w-full px-6 py-3 bg-purple-600 text-white rounded-lg hover:bg-purple-700 transition disabled:opacity-50"
        >
          {replaying ? "Setting up…" : "Play Again (New Main Person)"}
        </button>
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
