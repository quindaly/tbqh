"use client";

import { useState, useEffect } from "react";
import { useParams, useRouter } from "next/navigation";
import { getSession, submitGroupText } from "@/lib/api";

export default function SessionLobbyPage() {
  const params = useParams();
  const router = useRouter();
  const sessionId = params.id as string;

  const [session, setSession] = useState<any>(null);
  const [groupText, setGroupText] = useState("");
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    getSession(sessionId)
      .then(setSession)
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false));
  }, [sessionId]);

  const handleSubmitGroupText = async (e: React.FormEvent) => {
    e.preventDefault();
    setSubmitting(true);
    setError("");
    try {
      const participantId = localStorage.getItem("participant_id");
      if (!participantId) throw new Error("No participant ID found");

      const result = await submitGroupText(sessionId, groupText, participantId);
      localStorage.setItem(
        "provisional_group_profile_id",
        result.provisional_group_profile_id
      );
      router.push(`/session/${sessionId}/followups`);
    } catch (err: any) {
      setError(err.message);
    } finally {
      setSubmitting(false);
    }
  };

  if (loading) return <p className="text-center py-16">Loading session...</p>;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold">Session Lobby</h1>
        <div className="mt-2 flex gap-4 text-sm text-gray-500">
          <span>
            Status:{" "}
            <span className="font-medium text-green-600">{session?.status}</span>
          </span>
          <span>
            Join code:{" "}
            <span className="font-mono font-bold">
              {localStorage.getItem("join_code") || "—"}
            </span>
          </span>
        </div>
      </div>

      {/* Participants */}
      <div className="bg-white dark:bg-gray-800 rounded-xl p-4 border border-gray-200 dark:border-gray-700">
        <h2 className="font-semibold mb-2">
          Participants ({session?.participants?.length || 0})
        </h2>
        <ul className="space-y-1">
          {session?.participants?.map((p: any) => (
            <li key={p.id} className="text-sm flex items-center gap-2">
              <span
                className={`px-2 py-0.5 rounded text-xs ${
                  p.role === "host"
                    ? "bg-blue-100 text-blue-700 dark:bg-blue-900 dark:text-blue-300"
                    : "bg-gray-100 text-gray-600 dark:bg-gray-700 dark:text-gray-300"
                }`}
              >
                {p.role}
              </span>
              {p.display_name}
            </li>
          ))}
        </ul>
      </div>

      {/* Group description form */}
      <form onSubmit={handleSubmitGroupText} className="space-y-4">
        <div>
          <label className="block font-semibold mb-1">
            Describe your group
          </label>
          <p className="text-sm text-gray-500 mb-2">
            Tell us about your group — who are you, what's the vibe, any topics
            to explore or avoid?
          </p>
          <textarea
            value={groupText}
            onChange={(e) => setGroupText(e.target.value)}
            rows={4}
            required
            placeholder="e.g., We're a group of college friends catching up after 5 years. We like deep conversations, humor, and nostalgia. Keep it PG."
            className="w-full px-4 py-3 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-800 resize-none"
          />
        </div>
        {error && <p className="text-red-500 text-sm">{error}</p>}
        <button
          type="submit"
          disabled={submitting}
          className="w-full px-4 py-3 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 transition"
        >
          {submitting ? "Generating follow-ups..." : "Continue →"}
        </button>
      </form>
    </div>
  );
}
