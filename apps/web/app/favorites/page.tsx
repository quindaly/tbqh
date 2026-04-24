"use client";

import { useState, useEffect } from "react";
import { getFavorites } from "@/lib/api";

export default function FavoritesPage() {
  const [items, setItems] = useState<
    { question_item_id: string; question_text: string; liked_at: string }[]
  >([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    getFavorites()
      .then((data) => setItems(data.question_items))
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <p className="text-center py-16">Loading favorites...</p>;

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">❤️ My Favorites</h1>
      {error && <p className="text-red-500">{error}</p>}

      {items.length === 0 ? (
        <p className="text-gray-500 text-center py-8">
          No favorites yet. Like some questions to see them here!
        </p>
      ) : (
        <ul className="space-y-3">
          {items.map((item) => (
            <li
              key={item.question_item_id}
              className="bg-white dark:bg-gray-800 rounded-xl p-4 border border-gray-200 dark:border-gray-700"
            >
              <p className="text-lg">{item.question_text}</p>
              <p className="text-xs text-gray-400 mt-1">
                Liked {new Date(item.liked_at).toLocaleDateString()}
              </p>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
