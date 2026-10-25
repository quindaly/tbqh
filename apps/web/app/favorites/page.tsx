"use client";

import { useState, useEffect } from "react";
import { getFavorites } from "@/lib/api";
import { LoadError } from "../_components/LoadError";
import { Eyebrow, Heading } from "../_components/ui";

export default function FavoritesPage() {
  const [items, setItems] = useState<
    { question_item_id: string; question_text: string; liked_at: string }[]
  >([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [reloadKey, setReloadKey] = useState(0);

  useEffect(() => {
    setLoading(true);
    setError("");
    getFavorites()
      .then((data) => setItems(data.question_items))
      .catch((err) => setError(err.message || "Couldn't load this list."))
      .finally(() => setLoading(false));
  }, [reloadKey]);

  if (loading) return <p className="text-center py-16 text-muted">Loading favorites…</p>;
  if (error) return <LoadError message={error} onRetry={() => setReloadKey((n) => n + 1)} />;

  return (
    <div className="max-w-md mx-auto py-8 space-y-6">
      <div className="space-y-3">
        <Eyebrow>Your list</Eyebrow>
        <Heading>Favorites</Heading>
      </div>

      {items.length === 0 ? (
        <p className="text-muted text-center py-8">
          No favorites yet. Tap &ldquo;Love it&rdquo; on a question and it will show up here.
        </p>
      ) : (
        <ul className="space-y-3">
          {items.map((item) => (
            <li
              key={item.question_item_id}
              className="bg-surface rounded-md p-4 border border-soft"
            >
              <p className="font-serif text-lg">{item.question_text}</p>
              <p className="text-xs text-muted mt-1">
                Liked {new Date(item.liked_at).toLocaleDateString()}
              </p>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
