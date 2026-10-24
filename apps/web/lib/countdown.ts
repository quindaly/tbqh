"use client";

import { useEffect, useState } from "react";

/** Format whole seconds as m:ss (never negative). */
export function formatClock(seconds: number): string {
  const s = Math.max(0, Math.ceil(seconds));
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}

/**
 * Seconds left now, given what the server reported when the response arrived.
 *
 * The server sends "seconds_remaining" rather than a wall-clock deadline so a
 * phone with a wrong clock still shows the right time: we only measure how long
 * it has been since the response came in, on our own clock.
 */
export function secondsLeft(
  secondsRemainingAtReceipt: number,
  receivedAtMs: number,
  nowMs: number
): number {
  return Math.max(0, secondsRemainingAtReceipt - (nowMs - receivedAtMs) / 1000);
}

/**
 * Live countdown for a server-timed phase. `phase` is the object from an API
 * response (or null when untimed) and `receivedAt` is `Date.now()` captured when
 * that response arrived. Returns null when there is no clock to show.
 */
export function useCountdown(
  phase: { seconds_remaining: number } | null | undefined,
  receivedAt: number
): number | null {
  const [now, setNow] = useState(() => Date.now());
  // Depend on primitives so callers can pass a fresh object every render.
  const hasClock = !!phase;
  const secondsRemaining = phase?.seconds_remaining;

  useEffect(() => {
    if (!hasClock) return;
    setNow(Date.now());
    const id = setInterval(() => setNow(Date.now()), 250);
    return () => clearInterval(id);
  }, [hasClock, secondsRemaining, receivedAt]);

  if (!phase) return null;
  return secondsLeft(phase.seconds_remaining, receivedAt, now);
}
