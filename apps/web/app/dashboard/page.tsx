"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { LoadError } from "../_components/LoadError";
import {
  ApiError,
  getMe,
  createGroup,
  listPolicies,
  createSession,
} from "@/lib/api";

export default function DashboardPage() {
  const router = useRouter();
  const [user, setUser] = useState<{ id: string; email: string } | null>(null);
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState("");
  const [loadError, setLoadError] = useState("");
  const [reloadKey, setReloadKey] = useState(0);
  const isGuest = user?.email?.endsWith("@guest.local");

  useEffect(() => {
    setLoading(true);
    setLoadError("");
    getMe()
      .then(setUser)
      .catch((e) => {
        // Only a real "not signed in" answer sends you to login; an outage should not.
        if (e instanceof ApiError && e.status === 401) router.push("/login");
        else setLoadError(e?.message || "Couldn't reach the server.");
      })
      .finally(() => setLoading(false));
  }, [router, reloadKey]);

  const handleCreateSession = async () => {
    setCreating(true);
    setError("");
    try {
      // Create group
      const group = await createGroup("My Group");

      // Get default policy
      const { policies } = await listPolicies();
      if (!policies.length) throw new Error("No policies found");

      // Create session
      const session = await createSession(group.group_id, policies[0].id);

      // Store participant ID
      localStorage.setItem("participant_id", group.host_participant_id);
      localStorage.setItem("session_id", session.session_id);
      localStorage.setItem("join_code", session.join_code);

      router.push(`/session/${session.session_id}`);
    } catch (err: any) {
      setError(err.message);
    } finally {
      setCreating(false);
    }
  };

  if (loading) {
    return <p className="text-center py-16">Loading...</p>;
  }

  if (loadError) {
    return <LoadError message={loadError} onRetry={() => setReloadKey((n) => n + 1)} />;
  }

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-bold">
          {isGuest ? "Welcome, Guest" : `Welcome back, ${user?.email}`}
        </h1>
        <p className="text-muted mt-1">
          Start a new discussion session or join an existing one.
        </p>
        {isGuest && (
          <p className="text-sm text-accent mt-2">
            <a href="/login" className="hover:underline font-medium">
              Sign in with email
            </a>{" "}
            to save favorites and build a profile.
          </p>
        )}
      </div>

      {error && (
        <div className="bg-red-50 dark:bg-red-900/20 text-red-600 dark:text-red-400 p-3 rounded-md">
          {error}
        </div>
      )}

      <div className="grid gap-4 sm:grid-cols-2">
        <button
          onClick={handleCreateSession}
          disabled={creating}
          className="p-6 border border-soft rounded-md hover:bg-soft text-left transition"
        >
          <h2 className="text-lg font-semibold">
            {creating ? "Creating..." : "➕ New Session"}
          </h2>
          <p className="text-sm text-muted mt-1">
            Create a group and start generating discussion questions.
          </p>
        </button>

        <a
          href="/join"
          className="p-6 border border-soft rounded-md hover:bg-soft text-left transition block"
        >
          <h2 className="text-lg font-semibold">🔗 Join Session</h2>
          <p className="text-sm text-muted mt-1">
            Join an existing session with a code.
          </p>
        </a>
      </div>
    </div>
  );
}
