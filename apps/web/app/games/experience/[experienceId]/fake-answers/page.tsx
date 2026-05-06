"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import {
  getFakeAnswerQuestions,
  submitFakeAnswer,
  getHWDYKState,
} from "@/lib/api";

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

  const participantId =
    typeof window !== "undefined"
      ? localStorage.getItem(`game_pid_${experienceId}`) || ""
      : "";

  useEffect(() => {
    getFakeAnswerQuestions(experienceId, participantId).then((res) => {
      setQuestions(res.questions);
      // Skip already submitted
      const firstUnanswered = res.questions.findIndex((q) => !q.already_submitted);
      if (firstUnanswered === -1) {
        setAllDone(true);
      } else {
        setCurrentIdx(firstUnanswered);
      }
    });
  }, [experienceId, participantId]);

  // Poll for game start after done
  useEffect(() => {
    if (!allDone) return;
    const interval = setInterval(async () => {
      try {
        const state = await getHWDYKState(experienceId);
        if (state.game_state === "ready_to_start") {
          router.push(`/games/experience/${experienceId}/lobby`);
        } else if (state.game_state === "round_active") {
          router.push(`/games/experience/${experienceId}/hwdyk-play`);
        }
      } catch {}
    }, 3000);
    return () => clearInterval(interval);
  }, [allDone, experienceId, router]);

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

  if (questions.length === 0) {
    return <div className="py-12 text-center text-gray-500">Loading…</div>;
  }

  if (allDone) {
    return (
      <div className="py-12 text-center space-y-4">
        <h2 className="text-2xl font-bold">All fake answers submitted! 🎭</h2>
        <p className="text-gray-500">Waiting for the host to start the game…</p>
        <div className="animate-pulse text-purple-500">●●●</div>
      </div>
    );
  }

  const q = questions[currentIdx];
  const answeredCount = questions.filter((q) => q.already_submitted).length + (currentIdx > 0 ? 1 : 0);

  return (
    <div className="max-w-lg mx-auto py-12 space-y-6">
      {/* Progress */}
      <div className="flex items-center justify-between text-sm text-gray-500">
        <span>Question {currentIdx + 1} of {questions.length}</span>
      </div>
      <div className="w-full bg-gray-200 dark:bg-gray-700 rounded-full h-2">
        <div
          className="bg-purple-600 h-2 rounded-full transition-all"
          style={{ width: `${((currentIdx + 1) / questions.length) * 100}%` }}
        />
      </div>

      {/* Question */}
      <div className="space-y-2">
        <h2 className="text-xl font-semibold">{q.question_text}</h2>
        <p className="text-sm text-gray-500">
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
          className="w-full px-4 py-3 border rounded-lg bg-white dark:bg-gray-800 focus:ring-2 focus:ring-purple-500 outline-none resize-none"
        />
        <span className="absolute bottom-2 right-3 text-xs text-gray-400">
          {fakeText.length}/80
        </span>
      </div>

      {error && <p className="text-red-500 text-sm">{error}</p>}

      <button
        onClick={handleSubmit}
        disabled={loading || !fakeText.trim()}
        className="w-full px-6 py-3 bg-purple-600 text-white rounded-lg hover:bg-purple-700 transition disabled:opacity-50"
      >
        {loading ? "Submitting…" : "Submit Fake Answer"}
      </button>
    </div>
  );
}
