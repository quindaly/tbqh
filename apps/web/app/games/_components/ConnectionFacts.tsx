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
      className="rounded-md border border-soft bg-surface px-4 py-3 text-left"
    >
      <p className="text-xs uppercase tracking-[0.14em] text-muted">
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
              <p className="font-serif text-base leading-snug text-ink">
                {fact.title}
              </p>
              <p className="mt-0.5 text-sm text-muted">{fact.body}</p>
            </div>
          );
        })}
      </div>
    </aside>
  );
}

export const ConnectionFacts = memo(ConnectionFactsBase);
