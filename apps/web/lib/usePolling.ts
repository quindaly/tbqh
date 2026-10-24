"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError } from "@/lib/api";

// A response with one of these statuses will not fix itself, so polling stops.
const FATAL_STATUSES = new Set([400, 403, 404, 410, 422]);

interface PollingOptions {
  /** Delay between successful polls. */
  baseMs?: number;
  /** Longest delay between polls while requests keep failing. */
  maxMs?: number;
  /** Consecutive failures before polling stops and the user can retry. */
  maxFailures?: number;
}

/**
 * Calls `poll` on a timer. `poll` should throw when its request fails.
 *
 * - A permanent error (for example a 404) stops polling and is returned as `fatal`.
 * - Temporary errors (offline, 5xx) back off exponentially. `failures` counts
 *   them, and after `maxFailures` in a row polling stops with `gaveUp` set.
 * - `retry()` restarts polling from scratch.
 *
 * `poll` can change between renders without restarting the timer.
 */
export function usePolling(poll: () => Promise<void>, options: PollingOptions = {}) {
  const { baseMs = 3000, maxMs = 15000, maxFailures = 6 } = options;

  const pollRef = useRef(poll);
  pollRef.current = poll;

  const [failures, setFailures] = useState(0);
  const [fatal, setFatal] = useState<ApiError | null>(null);
  const [run, setRun] = useState(0);

  useEffect(() => {
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    let consecutiveFailures = 0;

    setFailures(0);
    setFatal(null);

    const tick = async () => {
      try {
        await pollRef.current();
        if (cancelled) return;
        consecutiveFailures = 0;
        setFailures(0);
      } catch (err) {
        if (cancelled) return;
        if (err instanceof ApiError && FATAL_STATUSES.has(err.status)) {
          setFatal(err);
          return;
        }
        consecutiveFailures += 1;
        setFailures(consecutiveFailures);
        if (consecutiveFailures >= maxFailures) return;
      }
      const delay = Math.min(baseMs * 2 ** consecutiveFailures, maxMs);
      timer = setTimeout(tick, delay);
    };

    tick();

    return () => {
      cancelled = true;
      if (timer) clearTimeout(timer);
    };
  }, [baseMs, maxMs, maxFailures, run]);

  const retry = useCallback(() => setRun((n) => n + 1), []);

  return { failures, fatal, gaveUp: failures >= maxFailures, retry };
}
