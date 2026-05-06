"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { createHWDYKGame, joinHWDYKGame } from "@/lib/api";

export default function HowWellDoYouKnowPage() {
  const router = useRouter();

  const [mode, setMode] = useState<"choose" | "create" | "join">("choose");
  const [displayName, setDisplayName] = useState("");
  const [joinCode, setJoinCode] = useState("");
  const [gameMode, setGameMode] = useState<"default" | "party">("default");
  const [numQuestions, setNumQuestions] = useState(5);
  const [intimacyLevel, setIntimacyLevel] = useState<"light" | "personal" | "deep">("personal");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function handleCreate() {
    if (!displayName.trim()) {
      setError("Enter a display name");
      return;
    }
    setLoading(true);
    setError("");
    try {
      const res = await createHWDYKGame(displayName.trim(), gameMode, numQuestions, intimacyLevel);
      localStorage.setItem(`game_pid_${res.experience_instance_id}`, res.participant_id);
      router.push(`/games/experience/${res.experience_instance_id}/hwdyk-lobby`);
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
      const res = await joinHWDYKGame(joinCode.trim().toUpperCase(), displayName.trim());
      localStorage.setItem(`game_pid_${res.experience_instance_id}`, res.participant_id);
      router.push(`/games/experience/${res.experience_instance_id}/hwdyk-lobby`);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }

  if (mode === "choose") {
    return (
      <div className="space-y-8 py-12 text-center">
        <h1 className="text-3xl font-bold">How Well Do You Know [Person]?</h1>
        <p className="text-gray-500 dark:text-gray-400">
          One person answers personal questions. Everyone else guesses the correct answer.
        </p>
        <div className="flex flex-col gap-4 items-center">
          <button
            onClick={() => setMode("create")}
            className="w-64 px-6 py-3 bg-purple-600 text-white rounded-lg hover:bg-purple-700 transition"
          >
            Create Game
          </button>
          <button
            onClick={() => setMode("join")}
            className="w-64 px-6 py-3 border border-gray-300 dark:border-gray-600 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-800 transition"
          >
            Join Game
          </button>
        </div>
        <a href="/games" className="text-sm text-gray-500 hover:underline">
          ← Back to games
        </a>
      </div>
    );
  }

  if (mode === "create") {
    return (
      <div className="max-w-md mx-auto space-y-6 py-12">
        <h1 className="text-2xl font-bold text-center">Create Game</h1>

        <div className="space-y-4">
          <input
            type="text"
            placeholder="Your display name"
            value={displayName}
            onChange={(e) => setDisplayName(e.target.value)}
            className="w-full px-4 py-3 border rounded-lg bg-white dark:bg-gray-800 focus:ring-2 focus:ring-purple-500 outline-none"
          />

          {/* Game Mode */}
          <div>
            <label className="block text-sm font-medium mb-2">Game Mode</label>
            <div className="grid grid-cols-2 gap-3">
              <button
                onClick={() => setGameMode("default")}
                className={`px-4 py-3 rounded-lg border text-sm transition ${
                  gameMode === "default"
                    ? "border-purple-500 bg-purple-50 dark:bg-purple-900/30 text-purple-700 dark:text-purple-300"
                    : "border-gray-300 dark:border-gray-600 hover:bg-gray-50 dark:hover:bg-gray-800"
                }`}
              >
                <div className="font-medium">Default</div>
                <div className="text-xs text-gray-500 mt-1">AI generates wrong answers</div>
              </button>
              <button
                onClick={() => setGameMode("party")}
                className={`px-4 py-3 rounded-lg border text-sm transition ${
                  gameMode === "party"
                    ? "border-purple-500 bg-purple-50 dark:bg-purple-900/30 text-purple-700 dark:text-purple-300"
                    : "border-gray-300 dark:border-gray-600 hover:bg-gray-50 dark:hover:bg-gray-800"
                }`}
              >
                <div className="font-medium">Party</div>
                <div className="text-xs text-gray-500 mt-1">Players write fake answers</div>
              </button>
            </div>
          </div>

          {/* Number of Questions */}
          <div>
            <label className="block text-sm font-medium mb-2">
              Questions: {numQuestions}
            </label>
            <input
              type="range"
              min={3}
              max={10}
              value={numQuestions}
              onChange={(e) => setNumQuestions(Number(e.target.value))}
              className="w-full"
            />
            <div className="flex justify-between text-xs text-gray-400">
              <span>3</span>
              <span>10</span>
            </div>
          </div>

          {/* Intimacy Level */}
          <div>
            <label className="block text-sm font-medium mb-2">Question Style</label>
            <div className="grid grid-cols-3 gap-2">
              {(["light", "personal", "deep"] as const).map((level) => (
                <button
                  key={level}
                  onClick={() => setIntimacyLevel(level)}
                  className={`px-3 py-2 rounded-lg border text-sm capitalize transition ${
                    intimacyLevel === level
                      ? "border-purple-500 bg-purple-50 dark:bg-purple-900/30 text-purple-700 dark:text-purple-300"
                      : "border-gray-300 dark:border-gray-600 hover:bg-gray-50 dark:hover:bg-gray-800"
                  }`}
                >
                  {level}
                </button>
              ))}
            </div>
          </div>

          {error && <p className="text-red-500 text-sm">{error}</p>}

          <button
            onClick={handleCreate}
            disabled={loading}
            className="w-full px-6 py-3 bg-purple-600 text-white rounded-lg hover:bg-purple-700 transition disabled:opacity-50"
          >
            {loading ? "Creating…" : "Create Game"}
          </button>

          <button
            onClick={() => { setMode("choose"); setError(""); }}
            className="w-full text-sm text-gray-500 hover:underline"
          >
            ← Back
          </button>
        </div>
      </div>
    );
  }

  // Join mode
  return (
    <div className="max-w-md mx-auto space-y-6 py-12">
      <h1 className="text-2xl font-bold text-center">Join Game</h1>

      <div className="space-y-4">
        <input
          type="text"
          placeholder="Your display name"
          value={displayName}
          onChange={(e) => setDisplayName(e.target.value)}
          className="w-full px-4 py-3 border rounded-lg bg-white dark:bg-gray-800 focus:ring-2 focus:ring-purple-500 outline-none"
        />
        <input
          type="text"
          placeholder="Join code"
          value={joinCode}
          onChange={(e) => setJoinCode(e.target.value)}
          className="w-full px-4 py-3 border rounded-lg bg-white dark:bg-gray-800 focus:ring-2 focus:ring-purple-500 outline-none uppercase tracking-widest text-center"
          maxLength={6}
        />

        {error && <p className="text-red-500 text-sm">{error}</p>}

        <button
          onClick={handleJoin}
          disabled={loading}
          className="w-full px-6 py-3 bg-purple-600 text-white rounded-lg hover:bg-purple-700 transition disabled:opacity-50"
        >
          {loading ? "Joining…" : "Join"}
        </button>

        <button
          onClick={() => { setMode("choose"); setError(""); }}
          className="w-full text-sm text-gray-500 hover:underline"
        >
          ← Back
        </button>
      </div>
    </div>
  );
}
