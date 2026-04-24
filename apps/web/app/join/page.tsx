"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { joinSession } from "@/lib/api";

export default function JoinPage() {
  const router = useRouter();
  const [sessionId, setSessionId] = useState("");
  const [joinCode, setJoinCode] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [joinMode, setJoinMode] = useState<"anonymous" | "authenticated">("anonymous");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const handleJoin = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      const result = await joinSession(sessionId, joinCode, displayName, joinMode);
      localStorage.setItem("participant_id", result.participant_id);
      localStorage.setItem("session_id", result.session_id);
      router.push(`/session/${result.session_id}`);
    } catch (err: any) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="max-w-md mx-auto space-y-6 py-8">
      <h1 className="text-2xl font-bold text-center">Join a Session</h1>
      <form onSubmit={handleJoin} className="space-y-4">
        <input
          type="text"
          placeholder="Session ID"
          value={sessionId}
          onChange={(e) => setSessionId(e.target.value)}
          required
          className="w-full px-4 py-3 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-800"
        />
        <input
          type="text"
          placeholder="Join Code"
          value={joinCode}
          onChange={(e) => setJoinCode(e.target.value)}
          required
          className="w-full px-4 py-3 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-800"
        />
        <input
          type="text"
          placeholder="Your Display Name"
          value={displayName}
          onChange={(e) => setDisplayName(e.target.value)}
          required
          className="w-full px-4 py-3 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-800"
        />
        <select
          value={joinMode}
          onChange={(e) => setJoinMode(e.target.value as any)}
          className="w-full px-4 py-3 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-800"
        >
          <option value="anonymous">Join Anonymously</option>
          <option value="authenticated">Join with Account</option>
        </select>
        {error && <p className="text-red-500 text-sm">{error}</p>}
        <button
          type="submit"
          disabled={loading}
          className="w-full px-4 py-3 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 transition"
        >
          {loading ? "Joining..." : "Join Session"}
        </button>
      </form>
    </div>
  );
}
