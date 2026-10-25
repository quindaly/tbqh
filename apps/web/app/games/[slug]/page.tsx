"use client";

import { useState, useEffect } from "react";
import { useParams, useRouter } from "next/navigation";
import { createGame, joinGame } from "@/lib/api";

export default function GameSlugPage() {
  const { slug } = useParams<{ slug: string }>();
  const router = useRouter();

  // Redirect HWDYK to its dedicated page
  useEffect(() => {
    if (slug === "how-well-do-you-know") {
      router.replace("/games/how-well-do-you-know");
    }
  }, [slug, router]);

  const [mode, setMode] = useState<"choose" | "create" | "join">("choose");
  const [displayName, setDisplayName] = useState("");
  const [joinCode, setJoinCode] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  // Invite links look like /games/who-knows-who?code=ABC123: jump straight to
  // the join form with the code filled in.
  useEffect(() => {
    const code = new URLSearchParams(window.location.search).get("code");
    if (code) {
      setJoinCode(code.toUpperCase().slice(0, 6));
      setMode("join");
    }
  }, []);

  async function handleCreate() {
    if (!displayName.trim()) {
      setError("Enter a display name");
      return;
    }
    setLoading(true);
    setError("");
    try {
      const res = await createGame(slug, displayName.trim());
      localStorage.setItem(`game_pid_${res.experience_instance_id}`, res.participant_id);
      router.push(`/games/experience/${res.experience_instance_id}/lobby`);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }

  async function handleJoin() {
    if (!displayName.trim() || !joinCode.trim()) {
      setError("Enter a display name and join code");
      return;
    }
    setLoading(true);
    setError("");
    try {
      const res = await joinGame(slug, joinCode.trim().toUpperCase(), displayName.trim());
      localStorage.setItem(`game_pid_${res.experience_instance_id}`, res.participant_id);
      router.push(`/games/experience/${res.experience_instance_id}/lobby`);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }

  if (mode === "choose") {
    return (
      <div className="space-y-8 py-12 text-center">
        <h1 className="text-3xl font-bold">Who Knows Who</h1>
        <p className="text-muted">
          Answer questions about yourself, then guess who gave each answer.
        </p>
        <div className="flex flex-col gap-4 items-center">
          <button
            onClick={() => setMode("create")}
            className="w-64 px-6 py-3 bg-btn text-btn-text rounded-md hover:opacity-90 transition font-medium"
          >
            Create Game
          </button>
          <button
            onClick={() => setMode("join")}
            className="w-64 px-6 py-3 border border-line rounded-md hover:bg-soft transition"
          >
            Join Game
          </button>
        </div>
        <a href="/games" className="text-sm text-muted hover:underline">
          ← Back to games
        </a>
      </div>
    );
  }

  return (
    <div className="max-w-md mx-auto space-y-6 py-12">
      <h1 className="text-2xl font-bold text-center">
        {mode === "create" ? "Create Game" : "Join Game"}
      </h1>

      <div className="space-y-4">
        <input
          type="text"
          placeholder="Your display name"
          value={displayName}
          onChange={(e) => setDisplayName(e.target.value)}
          className="w-full px-4 py-3 border rounded-md bg-surface"
        />

        {mode === "join" && (
          <input
            type="text"
            placeholder="Join code"
            value={joinCode}
            onChange={(e) => setJoinCode(e.target.value)}
            className="w-full px-4 py-3 border rounded-md bg-surface uppercase tracking-widest text-center"
            maxLength={6}
          />
        )}

        {error && <p className="text-red-500 text-sm">{error}</p>}

        <button
          onClick={mode === "create" ? handleCreate : handleJoin}
          disabled={loading}
          className="w-full px-6 py-3 bg-btn text-btn-text rounded-md hover:opacity-90 transition disabled:opacity-50 min-h-[56px] font-medium"
        >
          {loading ? "Loading…" : mode === "create" ? "Create" : "Join"}
        </button>

        <button
          onClick={() => {
            setMode("choose");
            setError("");
          }}
          className="w-full text-sm text-muted hover:underline"
        >
          ← Back
        </button>
      </div>
    </div>
  );
}
