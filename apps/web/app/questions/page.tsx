"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { createGuestSession } from "@/lib/api";
import { rememberSession } from "@/lib/discussionSession";
import { Eyebrow, Heading, PrimaryButton, SecondaryButton } from "../_components/ui";

export default function QuestionsPage() {
  const router = useRouter();
  const [starting, setStarting] = useState(false);
  const [error, setError] = useState("");

  async function handleStart() {
    setStarting(true);
    setError("");
    try {
      const res = await createGuestSession();
      rememberSession(res.session_id, {
        participantId: res.participant_id,
        joinCode: res.join_code,
      });
      router.push(`/session/${res.session_id}`);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setStarting(false);
    }
  }

  return (
    <div className="max-w-md mx-auto py-12 space-y-8">
      <div className="space-y-3">
        <Eyebrow>Discussion questions</Eyebrow>
        <Heading>Questions that fit your group</Heading>
        <p className="text-muted">
          Tell us who&rsquo;s in the room. We&rsquo;ll pick questions that suit the mood.
        </p>
      </div>

      <div className="space-y-3">
        <PrimaryButton onClick={handleStart} disabled={starting}>
          {starting ? "Setting up…" : "Start a session"}
        </PrimaryButton>
        <p className="text-sm text-muted text-center">No account needed.</p>
        <SecondaryButton onClick={() => router.push("/join")}>Join with a code</SecondaryButton>
      </div>

      {error && (
        <p role="alert" className="text-red-500 text-sm">
          {error}
        </p>
      )}

      <a href="/" className="text-sm text-muted hover:underline inline-block">
        ← Back to home
      </a>
    </div>
  );
}
