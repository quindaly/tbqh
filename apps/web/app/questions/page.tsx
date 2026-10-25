"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { createGuestSession, joinSession } from "@/lib/api";

export default function QuestionsPage() {
  const router = useRouter();
  const [mode, setMode] = useState<"choose" | "join">("choose");
  const [starting, setStarting] = useState(false);
  const [error, setError] = useState("");

  // Join form state
  const [sessionId, setSessionId] = useState("");
  const [joinCode, setJoinCode] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [loading, setLoading] = useState(false);

  async function handleGuestStart() {
    setStarting(true);
    setError("");
    try {
      const res = await createGuestSession();
      localStorage.setItem("participant_id", res.participant_id);
      localStorage.setItem("session_id", res.session_id);
      localStorage.setItem("join_code", res.join_code);
      router.push(`/session/${res.session_id}`);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setStarting(false);
    }
  }

  async function handleJoin(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      const result = await joinSession(sessionId, joinCode, displayName, "anonymous");
      localStorage.setItem("participant_id", result.participant_id);
      localStorage.setItem("session_id", result.session_id);
      router.push(`/session/${result.session_id}`);
    } catch (err: any) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  if (mode === "join") {
    return (
      <div className="max-w-md mx-auto space-y-6 py-12">
        <h1 className="text-2xl font-bold text-center">Join a Session</h1>
        <form onSubmit={handleJoin} className="space-y-4">
          <input
            type="text"
            placeholder="Session ID"
            value={sessionId}
            onChange={(e) => setSessionId(e.target.value)}
            required
            className="w-full px-4 py-3 border border-line rounded-md bg-surface"
          />
          <input
            type="text"
            placeholder="Join Code"
            value={joinCode}
            onChange={(e) => setJoinCode(e.target.value)}
            required
            className="w-full px-4 py-3 border border-line rounded-md bg-surface"
          />
          <input
            type="text"
            placeholder="Your Display Name"
            value={displayName}
            onChange={(e) => setDisplayName(e.target.value)}
            required
            className="w-full px-4 py-3 border border-line rounded-md bg-surface"
          />
          {error && <p className="text-red-500 text-sm">{error}</p>}
          <button
            type="submit"
            disabled={loading}
            className="w-full px-4 py-3 bg-btn text-btn-text rounded-md hover:opacity-90 disabled:opacity-50 transition min-h-[56px] font-medium"
          >
            {loading ? "Joining…" : "Join"}
          </button>
        </form>
        <button
          onClick={() => { setMode("choose"); setError(""); }}
          className="block mx-auto text-sm text-muted hover:underline"
        >
          ← Back
        </button>
      </div>
    );
  }

  return (
    <div className="space-y-8 py-12 text-center">
      <h1 className="text-3xl font-bold">Discussion Questions</h1>
      <p className="text-muted">
        Get personalized discussion prompts for your group.
      </p>

      <div className="flex flex-col gap-4 items-center">
        <button
          onClick={handleGuestStart}
          disabled={starting}
          className="w-72 px-6 py-4 bg-btn text-btn-text text-lg rounded-md hover:opacity-90 disabled:opacity-50 transition font-medium"
        >
          {starting ? "Setting up…" : "Start New Session"}
        </button>
        <p className="text-sm text-muted -mt-2">
          No account needed — jump straight in
        </p>
        <button
          onClick={() => setMode("join")}
          className="w-72 px-6 py-3 border border-line rounded-md hover:bg-soft transition"
        >
          Join Existing Session
        </button>
      </div>

      {error && <p className="text-red-500 text-sm">{error}</p>}

      <a href="/" className="text-sm text-muted hover:underline inline-block pt-2">
        ← Back to home
      </a>
    </div>
  );
}
