"use client";

import { useEffect, useState, useCallback } from "react";
import { useParams, useRouter } from "next/navigation";
import { getGamePrompts, submitGameAnswer, getGameState } from "@/lib/api";

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

  const [participantId, setParticipantId] = useState<string | null>(null);

  useEffect(() => {
    setParticipantId(localStorage.getItem(`game_pid_${experienceId}`));
  }, [experienceId]);

  useEffect(() => {
    getGamePrompts(experienceId)
      .then((data) => setPrompts(data.prompts))
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [experienceId]);

  // Poll for state transition once all our answers are in
  const pollState = useCallback(async () => {
    try {
      const state = await getGameState(experienceId);
      if (
        state.game_state === "round_active" ||
        state.game_state === "ready_to_start"
      ) {
        router.push(`/games/experience/${experienceId}/play`);
      }
    } catch {}
  }, [experienceId, router]);

  useEffect(() => {
    if (!waitingForOthers) return;
    const interval = setInterval(pollState, 3000);
    return () => clearInterval(interval);
  }, [waitingForOthers, pollState]);

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

  if (loading) {
    return <p className="text-center py-16 text-gray-500">Loading questions…</p>;
  }

  if (done) {
    return (
      <div className="text-center py-16 space-y-4">
        <h2 className="text-2xl font-bold">All done!</h2>
        <p className="text-gray-500 dark:text-gray-400">
          Waiting for other players to finish their answers…
        </p>
        <div className="animate-pulse text-purple-500 text-lg">⏳</div>
      </div>
    );
  }

  const prompt = prompts[currentIdx];
  const progress = prompts.length > 0 ? ((currentIdx) / prompts.length) * 100 : 0;

  return (
    <div className="max-w-md mx-auto space-y-6 py-8">
      <h1 className="text-2xl font-bold text-center">About You</h1>

      {/* Progress bar */}
      <div className="w-full h-2 bg-gray-200 dark:bg-gray-700 rounded-full overflow-hidden">
        <div
          className="h-full bg-purple-600 transition-all"
          style={{ width: `${progress}%` }}
        />
      </div>
      <p className="text-sm text-gray-500 text-center">
        Question {currentIdx + 1} of {prompts.length}
      </p>

      {/* Question card */}
      <div className="rounded-xl border p-6 space-y-4">
        <p className="text-lg font-medium">{prompt?.prompt_text}</p>
        <textarea
          value={answer}
          onChange={(e) => setAnswer(e.target.value)}
          placeholder="Type your answer…"
          rows={3}
          className="w-full px-4 py-3 border rounded-lg bg-white dark:bg-gray-800 focus:ring-2 focus:ring-purple-500 outline-none resize-none"
        />
      </div>

      {error && <p className="text-red-500 text-sm">{error}</p>}

      <button
        onClick={handleSubmit}
        disabled={submitting || !answer.trim()}
        className="w-full px-6 py-3 bg-purple-600 text-white rounded-lg hover:bg-purple-700 transition disabled:opacity-50"
      >
        {submitting ? "Submitting…" : currentIdx + 1 < prompts.length ? "Next" : "Finish"}
      </button>
    </div>
  );
}
