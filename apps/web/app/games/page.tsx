"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { listGames } from "@/lib/api";
import { Eyebrow, Heading, PrimaryButton } from "../_components/ui";

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
        <h1 className="font-serif text-[28px] leading-[1.15] font-normal">Couldn't load the games</h1>
        <p className="text-muted">
          Check your connection and try again.
        </p>
        <PrimaryButton onClick={() => setReloadKey((n) => n + 1)} className="w-64">
          Try again
        </PrimaryButton>
      </div>
    );
  }

  return (
    <div className="max-w-2xl mx-auto space-y-8 py-8">
      <div className="space-y-3">
        <Eyebrow>Games</Eyebrow>
        <Heading>Pick a game</Heading>
        <p className="text-muted">Choose one to play with your friends.</p>
      </div>

      <div className="grid gap-4 sm:grid-cols-2">
        {games.map((game) => (
          <button
            key={game.id}
            onClick={() => router.push(`/games/${game.slug}`)}
            className="rounded-md border border-soft bg-surface p-6 text-left hover:border-accent transition"
          >
            <h2 className="font-serif text-2xl">{game.display_name}</h2>
            <p className="mt-2 text-muted">
              {game.description}
            </p>
          </button>
        ))}
      </div>

      <div>
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
