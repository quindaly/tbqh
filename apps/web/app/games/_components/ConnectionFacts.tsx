"use client";

import { memo, useEffect, useState } from "react";
import {
  CONNECTION_FACTS,
  FACT_ROTATION_MS,
  type ConnectionFact,
} from "@/lib/connectionFacts";

interface Props {
  facts?: readonly ConnectionFact[];
  intervalMs?: number;
}

/**
 * A quiet card that shows one connection fact at a time and moves to the next
 * every 20 seconds, looping forever.
 *
 * - It owns its timer and takes no props from the lobby, so the lobby's
 *   frequent refreshes can't restart it (it's memoised for the same reason).
 * - Every fact is laid out in the same grid cell with only the current one
 *   visible, so the card is always as tall as the longest fact and never
 *   shifts the page when it changes, at any screen width.
 * - It isn't a live region: a screen reader reads it where it sits, but is not
 *   interrupted every 20 seconds. The fade is skipped for people who ask for
 *   reduced motion (see globals.css).
 */
function ConnectionFactsBase({
  facts = CONNECTION_FACTS,
  intervalMs = FACT_ROTATION_MS,
}: Props) {
  const [index, setIndex] = useState(0);
  const count = facts.length;

  useEffect(() => {
    if (count < 2) return;
    const timer = setInterval(() => setIndex((i) => (i + 1) % count), intervalMs);
    return () => clearInterval(timer);
  }, [count, intervalMs]);

  if (count === 0) return null;

  return (
    <aside
      aria-label="Did you know?"
      className="rounded-xl border border-purple-200 dark:border-purple-800 bg-purple-50 dark:bg-purple-900/20 px-4 py-3 text-left"
    >
      <p className="text-xs font-medium uppercase tracking-wide text-purple-700 dark:text-purple-300">
        Did you know?
      </p>
      <div className="grid mt-1">
        {facts.map((fact, i) => {
          const active = i === index;
          return (
            <div
              key={fact.id}
              data-active={active}
              aria-hidden={!active}
              // Same grid cell for all, so the tallest sets the height.
              style={{ gridArea: "1 / 1" }}
              className={`min-w-0 break-words ${
                active ? "connection-fact-fade" : "invisible"
              }`}
            >
              <p className="text-sm font-semibold text-gray-900 dark:text-gray-100">
                {fact.title}
              </p>
              <p className="text-sm text-gray-700 dark:text-gray-300">{fact.body}</p>
            </div>
          );
        })}
      </div>
    </aside>
  );
}

export const ConnectionFacts = memo(ConnectionFactsBase);
