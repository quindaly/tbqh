"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { listGames } from "@/lib/api";

interface Game {
  id: string;
  slug: string;
  display_name: string;
  description: string;
  status: string;
}

export default function GamesPage() {
  const router = useRouter();
  const [games, setGames] = useState<Game[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadFailed, setLoadFailed] = useState(false);
  const [reloadKey, setReloadKey] = useState(0);

  useEffect(() => {
    setLoading(true);
    setLoadFailed(false);
    listGames()
      .then((data) => setGames(data.games))
      .catch(() => setLoadFailed(true))
      .finally(() => setLoading(false));
  }, [reloadKey]);

  if (loading) {
    return <p className="text-center py-16 text-gray-500">Loading games…</p>;
  }

  if (loadFailed) {
    return (
      <div className="max-w-md mx-auto space-y-4 py-16 text-center">
        <h1 className="text-2xl font-bold">Couldn't load the games</h1>
        <p className="text-gray-500 dark:text-gray-400">
          Check your connection and try again.
        </p>
        <button
          onClick={() => setReloadKey((n) => n + 1)}
          className="w-64 px-6 py-3 bg-purple-600 text-white rounded-lg hover:bg-purple-700 transition"
        >
          Try again
        </button>
      </div>
    );
  }

  return (
    <div className="space-y-8 py-8">
      <h1 className="text-3xl font-bold text-center">Social Games</h1>
      <p className="text-center text-gray-500 dark:text-gray-400">
        Choose a game to play with your friends.
      </p>

      <div className="grid gap-6 sm:grid-cols-2">
        {games.map((game) => (
          <button
            key={game.id}
            onClick={() => router.push(`/games/${game.slug}`)}
            className="rounded-xl border border-gray-200 dark:border-gray-700 p-6 text-left hover:border-purple-500 hover:shadow-lg transition"
          >
            <h2 className="text-xl font-semibold">{game.display_name}</h2>
            <p className="mt-2 text-gray-500 dark:text-gray-400">
              {game.description}
            </p>
          </button>
        ))}
      </div>

      <div className="text-center">
        <a
          href="/"
          className="text-sm text-gray-500 hover:underline"
        >
          ← Back to home
        </a>
      </div>
    </div>
  );
}
