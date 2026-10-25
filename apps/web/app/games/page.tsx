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
    return <p className="text-center py-16 text-muted">Loading games…</p>;
  }

  if (loadFailed) {
    return (
      <div className="max-w-md mx-auto space-y-4 py-16 text-center">
        <h1 className="text-2xl font-bold">Couldn't load the games</h1>
        <p className="text-muted">
          Check your connection and try again.
        </p>
        <button
          onClick={() => setReloadKey((n) => n + 1)}
          className="w-64 px-6 py-3 bg-btn text-btn-text rounded-md hover:opacity-90 transition font-medium"
        >
          Try again
        </button>
      </div>
    );
  }

  return (
    <div className="space-y-8 py-8">
      <h1 className="text-3xl font-bold text-center">Social Games</h1>
      <p className="text-center text-muted">
        Choose a game to play with your friends.
      </p>

      <div className="grid gap-6 sm:grid-cols-2">
        {games.map((game) => (
          <button
            key={game.id}
            onClick={() => router.push(`/games/${game.slug}`)}
            className="rounded-md border border-soft p-6 text-left hover:border-accent hover:shadow-lg transition"
          >
            <h2 className="text-xl font-semibold">{game.display_name}</h2>
            <p className="mt-2 text-muted">
              {game.description}
            </p>
          </button>
        ))}
      </div>

      <div className="text-center">
        <a
          href="/"
          className="text-sm text-muted hover:underline"
        >
          ← Back to home
        </a>
      </div>
    </div>
  );
}
