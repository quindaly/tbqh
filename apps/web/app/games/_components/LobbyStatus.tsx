"use client";

import Link from "next/link";

/** Shown when the game ID in the URL doesn't match any game. */
export function LobbyNotFound() {
  return (
    <div className="max-w-md mx-auto space-y-4 py-16 text-center">
      <h1 className="text-2xl font-bold">We couldn't find that game</h1>
      <p className="text-muted">
        The link may be old or mistyped. Ask the host for a fresh join code or
        link, or start a new game.
      </p>
      <div className="flex flex-col items-center gap-3 pt-2">
        <Link
          href="/games"
          className="w-64 px-6 py-3 bg-btn text-btn-text rounded-md font-medium hover:opacity-90 transition"
        >
          Back to games
        </Link>
      </div>
    </div>
  );
}

/** Shown when the lobby has never loaded and repeated attempts failed. */
export function LobbyUnreachable({ onRetry }: { onRetry: () => void }) {
  return (
    <div className="max-w-md mx-auto space-y-4 py-16 text-center">
      <h1 className="text-2xl font-bold">Can't reach the game</h1>
      <p className="text-muted">
        Check your connection and try again.
      </p>
      <button
        onClick={onRetry}
        className="w-64 px-6 py-3 bg-btn text-btn-text rounded-md font-medium hover:opacity-90 transition"
      >
        Try again
      </button>
    </div>
  );
}

/** Slim notice shown above a lobby that is already on screen while polling fails. */
export function ConnectionBanner({
  gaveUp,
  onRetry,
}: {
  gaveUp: boolean;
  onRetry: () => void;
}) {
  return (
    <div
      role="status"
      className="rounded-md border border-soft bg-surface px-3 py-2 text-sm text-ink flex items-center justify-between gap-3"
    >
      <span>
        {gaveUp
          ? "Connection lost. This page has stopped updating."
          : "Connection lost. Retrying…"}
      </span>
      {gaveUp && (
        <button onClick={onRetry} className="font-medium underline shrink-0">
          Try again
        </button>
      )}
    </div>
  );
}
