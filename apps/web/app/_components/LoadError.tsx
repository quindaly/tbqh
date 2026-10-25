"use client";

/** Shown when a page's main data failed to load, with a way to try again. */
export function LoadError({
  message,
  onRetry,
}: {
  message?: string;
  onRetry: () => void;
}) {
  return (
    <div role="alert" className="max-w-md mx-auto space-y-4 py-16 text-center">
      <h1 className="text-2xl font-bold">Couldn't load this page</h1>
      <p className="text-muted">
        {message || "Check your connection and try again."}
      </p>
      <button
        onClick={onRetry}
        className="w-64 px-6 py-3 bg-btn text-btn-text rounded-md hover:opacity-90 transition font-medium"
      >
        Try again
      </button>
    </div>
  );
}
