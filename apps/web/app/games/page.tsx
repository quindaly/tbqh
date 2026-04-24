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

  useEffect(() => {
    listGames()
      .then((data) => setGames(data.games))
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return <p className="text-center py-16 text-gray-500">Loading games…</p>;
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
