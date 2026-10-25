"use client";

import { useState, useEffect } from "react";
import { useParams, useRouter } from "next/navigation";
import { getSession, submitGroupText } from "@/lib/api";
import { inviteLink, readSession, rememberSession } from "@/lib/discussionSession";
import { LoadError } from "../../_components/LoadError";
import { Eyebrow, Heading, PrimaryButton, SecondaryButton } from "../../_components/ui";

const MAX_TEXT = 2000;

export default function SessionLobbyPage() {
  const params = useParams();
  const router = useRouter();
  const sessionId = params.id as string;

  const [session, setSession] = useState<any>(null);
  const [participantId, setParticipantId] = useState<string | undefined>();
  const [joinCode, setJoinCode] = useState<string | undefined>();
  const [groupText, setGroupText] = useState("");
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [copied, setCopied] = useState(false);
  const [error, setError] = useState("");
  const [loadError, setLoadError] = useState("");
  const [reloadKey, setReloadKey] = useState(0);

  useEffect(() => {
    const mem = readSession(sessionId);
    setParticipantId(mem.participantId);
    setJoinCode(mem.joinCode);
  }, [sessionId]);

  useEffect(() => {
    setLoading(true);
    setLoadError("");
    getSession(sessionId)
      .then(setSession)
      .catch((err) => setLoadError(err.message || "Couldn't load the session."))
      .finally(() => setLoading(false));
  }, [sessionId, reloadKey]);

  const handleSubmitGroupText = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!participantId) return;
    setSubmitting(true);
    setError("");
    try {
      const result = await submitGroupText(sessionId, groupText.trim(), participantId);
      rememberSession(sessionId, { provisionalProfileId: result.provisional_group_profile_id });
      router.push(`/session/${sessionId}/followups`);
    } catch (err: any) {
      setError(err.message);
    } finally {
      setSubmitting(false);
    }
  };

  async function copyInvite() {
    try {
      await navigator.clipboard.writeText(inviteLink(sessionId, joinCode));
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      setError("Couldn't copy the link. Share this page's address instead.");
    }
  }

  if (loading) return <p className="text-center py-16 text-muted">Loading session…</p>;
  if (loadError || !session) {
    return <LoadError message={loadError} onRetry={() => setReloadKey((n) => n + 1)} />;
  }

  // Opened on a device that never joined (e.g. a link shared without the code).
  if (!participantId) {
    return (
      <div className="max-w-md mx-auto py-12 space-y-6">
        <Eyebrow>Discussion questions</Eyebrow>
        <Heading>Join this session first</Heading>
        <p className="text-muted">
          This browser hasn&rsquo;t joined the session yet. Join with the code from whoever started it.
        </p>
        <PrimaryButton onClick={() => router.push(`/join?s=${sessionId}`)}>Join</PrimaryButton>
      </div>
    );
  }

  const people = session?.participants?.length || 0;

  return (
    <div className="max-w-md mx-auto py-8 space-y-8">
      <div className="space-y-3">
        <Eyebrow>Step 1 of 3 · Your group</Eyebrow>
        <Heading>Who&rsquo;s in the room?</Heading>
        <p className="text-muted">
          A few sentences is plenty: who you are, the mood, anything to steer toward or away from.
        </p>
      </div>

      <form onSubmit={handleSubmitGroupText} className="space-y-3">
        <textarea
          value={groupText}
          onChange={(e) => setGroupText(e.target.value)}
          rows={5}
          maxLength={MAX_TEXT}
          required
          aria-label="Describe your group"
          placeholder="College friends catching up after 5 years. We like deep conversations, humor and nostalgia. Keep it PG."
          className="w-full px-4 py-3 border border-line rounded-md bg-surface resize-none"
        />
        <div className="flex justify-between text-xs text-muted">
          <span>{submitting ? "Reading your description. This takes a few seconds." : ""}</span>
          <span>
            {groupText.length}/{MAX_TEXT}
          </span>
        </div>
        {error && (
          <p role="alert" className="text-red-500 text-sm">
            {error}
          </p>
        )}
        <PrimaryButton type="submit" disabled={submitting || !groupText.trim()}>
          {submitting ? "Thinking…" : "Continue"}
        </PrimaryButton>
      </form>

      <section className="bg-surface border border-soft rounded-md p-5 space-y-3">
        <div className="flex items-baseline justify-between">
          <h2 className="font-serif text-xl">
            {people === 1 ? "Just you so far" : `${people} people`}
          </h2>
          {joinCode && (
            <span className="text-sm text-muted">
              Code <span className="font-mono font-semibold text-ink">{joinCode}</span>
            </span>
          )}
        </div>
        <ul className="text-sm space-y-1">
          {session?.participants?.map((p: any) => (
            <li key={p.id} className="flex items-center gap-2">
              {p.display_name}
              {p.role === "host" && <span className="text-xs text-accent">host</span>}
            </li>
          ))}
        </ul>
        {joinCode && (
          <SecondaryButton type="button" onClick={copyInvite} className="min-h-[44px] text-base">
            {copied ? "Link copied" : "Copy invite link"}
          </SecondaryButton>
        )}
      </section>
    </div>
  );
}
