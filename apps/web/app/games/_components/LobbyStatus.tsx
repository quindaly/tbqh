"use client";

import Link from "next/link";

/** Shown when the game ID in the URL doesn't match any game. */
export function LobbyNotFound() {
  return (
    <div className="max-w-md mx-auto space-y-4 py-16 text-center">
      <h1 className="text-2xl font-bold">We couldn't find that game</h1>
      <p className="text-gray-500 dark:text-gray-400">
        The link may be old or mistyped. Ask the host for a fresh join code or
        link, or start a new game.
      </p>
      <div className="flex flex-col items-center gap-3 pt-2">
        <Link
          href="/games"
          className="w-64 px-6 py-3 bg-purple-600 text-white rounded-lg hover:bg-purple-700 transition"
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
      <p className="text-gray-500 dark:text-gray-400">
        Check your connection and try again.
      </p>
      <button
        onClick={onRetry}
        className="w-64 px-6 py-3 bg-purple-600 text-white rounded-lg hover:bg-purple-700 transition"
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
      className="rounded-lg border border-yellow-300 dark:border-yellow-700 bg-yellow-50 dark:bg-yellow-900/20 px-3 py-2 text-sm text-yellow-800 dark:text-yellow-200 flex items-center justify-between gap-3"
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
