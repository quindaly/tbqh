"use client";

import { useCallback, useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import {
  getFakeAnswerQuestions,
  submitFakeAnswer,
  getHWDYKState,
} from "@/lib/api";
import { usePolling } from "@/lib/usePolling";
import { ConnectionBanner, LobbyNotFound } from "../../../_components/LobbyStatus";

interface FakeQuestion {
  round_id: string;
  question_text: string;
  round_number: number;
  already_submitted: boolean;
}

export default function FakeAnswersPage() {
  const { experienceId } = useParams<{ experienceId: string }>();
  const router = useRouter();

  const [questions, setQuestions] = useState<FakeQuestion[]>([]);
  const [currentIdx, setCurrentIdx] = useState(0);
  const [fakeText, setFakeText] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [allDone, setAllDone] = useState(false);
  const [loadError, setLoadError] = useState("");
  const [reloadKey, setReloadKey] = useState(0);

  const participantId =
    typeof window !== "undefined"
      ? localStorage.getItem(`game_pid_${experienceId}`) || ""
      : "";

  useEffect(() => {
    setLoadError("");
    getFakeAnswerQuestions(experienceId, participantId)
      .then((res) => {
        setQuestions(res.questions);
        // Skip already submitted
        const firstUnanswered = res.questions.findIndex((q) => !q.already_submitted);
        if (firstUnanswered === -1) {
          setAllDone(true);
        } else {
          setCurrentIdx(firstUnanswered);
        }
      })
      .catch((e: any) => setLoadError(e.message || "Couldn't load the questions."));
  }, [experienceId, participantId, reloadKey]);

  // Poll for game start after done. Throws on failure so usePolling can back off.
  const pollStart = useCallback(async () => {
    if (!allDone) return;
    const state = await getHWDYKState(experienceId);
    if (state.game_state === "ready_to_start") {
      router.push(`/games/experience/${experienceId}/hwdyk-lobby`);
    } else if (state.game_state === "round_active") {
      router.push(`/games/experience/${experienceId}/hwdyk-play`);
    }
  }, [allDone, experienceId, router]);

  const { failures, fatal, gaveUp, retry } = usePolling(pollStart);

  async function handleSubmit() {
    if (!fakeText.trim()) {
      setError("Enter a fake answer");
      return;
    }
    if (fakeText.trim().length > 80) {
      setError("Must be 80 characters or fewer");
      return;
    }
    setLoading(true);
    setError("");
    try {
      const q = questions[currentIdx];
      await submitFakeAnswer(experienceId, q.round_id, participantId, fakeText.trim());
      setFakeText("");

      // Find next unanswered
      const remaining = questions.slice(currentIdx + 1).findIndex((q) => !q.already_submitted);
      if (remaining === -1) {
        setAllDone(true);
      } else {
        setCurrentIdx(currentIdx + 1 + remaining);
      }
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }

  if (fatal) {
    return <LobbyNotFound />;
  }

  if (loadError && questions.length === 0) {
    return (
      <div className="py-12 text-center space-y-4">
        <p className="text-muted">{loadError}</p>
        <button
          onClick={() => setReloadKey((k) => k + 1)}
          className="min-h-[56px] px-6 bg-btn text-btn-text rounded-md font-medium hover:opacity-90 transition"
        >
          Try again
        </button>
      </div>
    );
  }

  if (questions.length === 0) {
    return <div className="py-12 text-center text-muted">Loading…</div>;
  }

  if (allDone) {
    return (
      <div className="py-12 text-center space-y-4">
        <h2 className="font-serif text-[34px] leading-[1.1] tracking-[-0.01em] font-normal">All fake answers submitted</h2>
        <p className="text-muted">Waiting for the host to start the game…</p>
        <div aria-hidden="true" className="mx-auto h-2 w-2 rounded-full bg-accent animate-pulse" />
        {failures > 0 && (
          <div className="max-w-md mx-auto text-left">
            <ConnectionBanner gaveUp={gaveUp} onRetry={retry} />
          </div>
        )}
      </div>
    );
  }

  const q = questions[currentIdx];
  const answeredCount = questions.filter((q) => q.already_submitted).length + (currentIdx > 0 ? 1 : 0);

  return (
    <div className="max-w-lg mx-auto py-12 space-y-6">
      {/* Progress */}
      <div className="flex items-center justify-between text-sm text-muted">
        <span>Question {currentIdx + 1} of {questions.length}</span>
      </div>
      <div className="w-full bg-soft rounded-md h-2">
        <div
          className="bg-accent h-2 rounded-md transition-all"
          style={{ width: `${((currentIdx + 1) / questions.length) * 100}%` }}
        />
      </div>

      {/* Question */}
      <div className="space-y-2">
        <h2 className="font-serif text-[32px] leading-[1.15] tracking-[-0.01em] font-normal">{q.question_text}</h2>
        <p className="text-sm text-muted">
          Write a believable but <span className="font-medium">wrong</span> answer to fool other players!
        </p>
      </div>

      {/* Fake answer input */}
      <div className="relative">
        <textarea
          value={fakeText}
          onChange={(e) => setFakeText(e.target.value)}
          placeholder="Your fake answer…"
          rows={2}
          maxLength={80}
          className="w-full px-4 py-3 border border-line rounded-md bg-surface text-ink resize-none"
        />
        <span className="absolute bottom-2 right-3 text-xs text-muted">
          {fakeText.length}/80
        </span>
      </div>

      {error && <p className="text-red-500 text-sm">{error}</p>}

      <button
        onClick={handleSubmit}
        disabled={loading || !fakeText.trim()}
        className="w-full min-h-[56px] px-6 bg-btn text-btn-text rounded-md font-medium hover:opacity-90 transition disabled:opacity-50"
      >
        {loading ? "Submitting…" : "Submit Fake Answer"}
      </button>
    </div>
  );
}
