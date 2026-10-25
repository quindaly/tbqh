"use client";

import { useState, useEffect } from "react";
import { getBlocked } from "@/lib/api";
import { LoadError } from "../_components/LoadError";
import { Eyebrow, Heading } from "../_components/ui";

export default function BlockedPage() {
  const [items, setItems] = useState<
    { question_item_id: string; question_text: string; blocked_at: string }[]
  >([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [reloadKey, setReloadKey] = useState(0);

  useEffect(() => {
    setLoading(true);
    setError("");
    getBlocked()
      .then((data) => setItems(data.question_items))
      .catch((err) => setError(err.message || "Couldn't load this list."))
      .finally(() => setLoading(false));
  }, [reloadKey]);

  if (loading) return <p className="text-center py-16 text-muted">Loading blocked list…</p>;
  if (error) return <LoadError message={error} onRetry={() => setReloadKey((n) => n + 1)} />;

  return (
    <div className="max-w-md mx-auto py-8 space-y-6">
      <div className="space-y-3">
        <Eyebrow>Your list</Eyebrow>
        <Heading>Blocked questions</Heading>
      </div>

      {items.length === 0 ? (
        <p className="text-muted text-center py-8">
          Nothing blocked. Questions you mark &ldquo;Not for us&rdquo; show up here.
        </p>
      ) : (
        <ul className="space-y-3">
          {items.map((item) => (
            <li
              key={item.question_item_id}
              className="bg-surface rounded-md p-4 border border-soft opacity-60"
            >
              <p className="font-serif text-lg line-through">{item.question_text}</p>
              <p className="text-xs text-muted mt-1">
                Blocked {new Date(item.blocked_at).toLocaleDateString()}
              </p>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
