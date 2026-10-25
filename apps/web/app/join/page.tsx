"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { getMe, joinSession } from "@/lib/api";
import { rememberSession } from "@/lib/discussionSession";
import { Eyebrow, Heading, PrimaryButton } from "../_components/ui";

const field = "w-full px-4 py-3 border border-line rounded-md bg-surface min-h-[56px]";

export default function JoinPage() {
  const router = useRouter();
  const [sessionId, setSessionId] = useState("");
  const [joinCode, setJoinCode] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [fromLink, setFromLink] = useState(false);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  // An invite link carries the session and code, so friends only type their name.
  useEffect(() => {
    const q = new URLSearchParams(window.location.search);
    const s = q.get("s");
    const c = q.get("c");
    if (s) setSessionId(s);
    if (c) setJoinCode(c);
    if (s && c) setFromLink(true);
  }, []);

  const handleJoin = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      // Signed-in people join with their account so their likes are saved to it.
      const me = await getMe().catch(() => null);
      const result = await joinSession(
        sessionId.trim(),
        joinCode.trim(),
        displayName,
        me ? "authenticated" : "anonymous"
      );
      rememberSession(result.session_id, {
        participantId: result.participant_id,
        joinCode: joinCode.trim().toUpperCase(),
      });
      router.push(`/session/${result.session_id}`);
    } catch (err: any) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="max-w-md mx-auto py-12 space-y-8">
      <div className="space-y-3">
        <Eyebrow>Discussion questions</Eyebrow>
        <Heading>Join a session</Heading>
      </div>
      <form onSubmit={handleJoin} className="space-y-4">
        {!fromLink && (
          <>
            <input
              type="text"
              aria-label="Session ID"
              placeholder="Session ID"
              value={sessionId}
              onChange={(e) => setSessionId(e.target.value)}
              required
              className={field}
            />
            <input
              type="text"
              aria-label="Join code"
              placeholder="Join code"
              value={joinCode}
              onChange={(e) => setJoinCode(e.target.value)}
              required
              autoCapitalize="characters"
              className={field}
            />
          </>
        )}
        <input
          type="text"
          aria-label="Your name"
          placeholder="Your name"
          value={displayName}
          onChange={(e) => setDisplayName(e.target.value)}
          required
          maxLength={40}
          className={field}
        />
        {error && (
          <p role="alert" className="text-red-500 text-sm">
            {error}
          </p>
        )}
        <PrimaryButton type="submit" disabled={loading || !displayName.trim()}>
          {loading ? "Joining…" : "Join"}
        </PrimaryButton>
      </form>
    </div>
  );
}
