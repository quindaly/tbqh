"use client";

import { useEffect, useState, useCallback } from "react";
import { useParams, useRouter } from "next/navigation";
import { ApiError, getGamePrompts, submitGameAnswer, getGameState } from "@/lib/api";
import { usePolling } from "@/lib/usePolling";
import {
  ConnectionBanner,
  LobbyNotFound,
  LobbyUnreachable,
} from "../../../_components/LobbyStatus";

interface Prompt {
  id: string;
  prompt_text: string;
}

export default function QuestionsPage() {
  const { experienceId } = useParams<{ experienceId: string }>();
  const router = useRouter();

  const [prompts, setPrompts] = useState<Prompt[]>([]);
  const [currentIdx, setCurrentIdx] = useState(0);
  const [answer, setAnswer] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [done, setDone] = useState(false);
  const [waitingForOthers, setWaitingForOthers] = useState(false);
  const [loadFailed, setLoadFailed] = useState(false);
  const [notFound, setNotFound] = useState(false);
  const [reloadKey, setReloadKey] = useState(0);

  const [participantId, setParticipantId] = useState<string | null>(null);

  useEffect(() => {
    setParticipantId(localStorage.getItem(`game_pid_${experienceId}`));
  }, [experienceId]);

  useEffect(() => {
    setLoading(true);
    setLoadFailed(false);
    getGamePrompts(experienceId)
      .then((data) => setPrompts(data.prompts))
      .catch((e: any) => {
        if (e instanceof ApiError && (e.status === 404 || e.status === 410)) {
          setNotFound(true);
        } else {
          setLoadFailed(true);
        }
      })
      .finally(() => setLoading(false));
  }, [experienceId, reloadKey]);

  // Poll for state transition once all our answers are in
  // Throws on failure so usePolling can back off and surface outages.
  const pollState = useCallback(async () => {
    if (!waitingForOthers) return;
    const state = await getGameState(experienceId);
    if (
      state.game_state === "round_active" ||
      state.game_state === "ready_to_start"
    ) {
      router.push(`/games/experience/${experienceId}/play`);
    }
  }, [experienceId, router, waitingForOthers]);

  const { failures, fatal, gaveUp, retry } = usePolling(pollState);

  async function handleSubmit() {
    if (!participantId || !answer.trim()) return;
    setSubmitting(true);
    setError("");
    try {
      const res = await submitGameAnswer(
        experienceId,
        prompts[currentIdx].id,
        participantId,
        answer.trim()
      );
      setAnswer("");
      if (currentIdx + 1 < prompts.length) {
        setCurrentIdx(currentIdx + 1);
      } else {
        setDone(true);
        if (res.all_submitted) {
          router.push(`/games/experience/${experienceId}/play`);
        } else {
          setWaitingForOthers(true);
        }
      }
    } catch (e: any) {
      setError(e.message);
    } finally {
      setSubmitting(false);
    }
  }

  if (notFound || fatal) {
    return <LobbyNotFound />;
  }

  if (loading) {
    return <p className="text-center py-16 text-muted">Loading questions…</p>;
  }

  if (loadFailed || prompts.length === 0) {
    return <LobbyUnreachable onRetry={() => setReloadKey((n) => n + 1)} />;
  }

  if (done) {
    return (
      <div className="text-center py-16 space-y-4">
        <h2 className="text-2xl font-bold">All done!</h2>
        <p className="text-muted">
          Waiting for other players to finish their answers…
        </p>
        <div className="animate-pulse text-accent text-lg">⏳</div>
        {failures > 0 && (
          <div className="max-w-md mx-auto text-left">
            <ConnectionBanner gaveUp={gaveUp} onRetry={retry} />
          </div>
        )}
      </div>
    );
  }

  const prompt = prompts[currentIdx];
  const progress = prompts.length > 0 ? ((currentIdx) / prompts.length) * 100 : 0;

  return (
    <div className="max-w-md mx-auto space-y-6 py-8">
      <h1 className="text-2xl font-bold text-center">About You</h1>

      {/* Progress bar */}
      <div className="w-full h-2 bg-soft rounded-full overflow-hidden">
        <div
          className="h-full bg-accent transition-all"
          style={{ width: `${progress}%` }}
        />
      </div>
      <p className="text-sm text-muted text-center">
        Question {currentIdx + 1} of {prompts.length}
      </p>

      {/* Question card */}
      <div className="rounded-md border p-6 space-y-4">
        <p className="text-lg font-medium">{prompt?.prompt_text}</p>
        <textarea
          value={answer}
          onChange={(e) => setAnswer(e.target.value)}
          placeholder="Type your answer…"
          rows={3}
          className="w-full px-4 py-3 border rounded-md bg-surface resize-none"
        />
      </div>

      {error && <p className="text-red-500 text-sm">{error}</p>}

      <button
        onClick={handleSubmit}
        disabled={submitting || !answer.trim()}
        className="w-full px-6 py-3 bg-btn text-btn-text rounded-md hover:opacity-90 transition disabled:opacity-50 min-h-[56px] font-medium"
      >
        {submitting ? "Submitting…" : currentIdx + 1 < prompts.length ? "Next" : "Finish"}
      </button>
    </div>
  );
}
