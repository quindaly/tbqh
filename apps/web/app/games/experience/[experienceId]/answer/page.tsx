"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import {
  getMainPersonQuestions,
  submitMainPersonAnswer,
  getHWDYKState,
} from "@/lib/api";

export default function AnswerPage() {
  const { experienceId } = useParams<{ experienceId: string }>();
  const router = useRouter();

  const [questions, setQuestions] = useState<
    { id: string; prompt_text: string; round_number: number }[]
  >([]);
  const [currentIdx, setCurrentIdx] = useState(0);
  const [answer, setAnswer] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [allDone, setAllDone] = useState(false);

  const participantId =
    typeof window !== "undefined"
      ? localStorage.getItem(`game_pid_${experienceId}`) || ""
      : "";

  useEffect(() => {
    getMainPersonQuestions(experienceId).then((res) => {
      setQuestions(res.questions);
    });
  }, [experienceId]);

  // Poll for state change after all answered
  useEffect(() => {
    if (!allDone) return;
    const interval = setInterval(async () => {
      try {
        const state = await getHWDYKState(experienceId);
        if (
          state.game_state === "main_person_reviewing_choices" ||
          state.game_state === "ready_to_start"
        ) {
          router.push(`/games/experience/${experienceId}/review`);
        } else if (state.game_state === "players_submitting_fake_answers") {
          router.push(`/games/experience/${experienceId}/lobby`);
        } else if (state.game_state === "round_active") {
          router.push(`/games/experience/${experienceId}/hwdyk-play`);
        }
      } catch {}
    }, 3000);
    return () => clearInterval(interval);
  }, [allDone, experienceId, router]);

  async function handleSubmit() {
    if (answer.trim().length < 3) {
      setError("Answer must be at least 3 characters");
      return;
    }
    setLoading(true);
    setError("");
    try {
      const q = questions[currentIdx];
      const res = await submitMainPersonAnswer(
        experienceId,
        q.id,
        participantId,
        answer.trim()
      );
      if (res.all_answered) {
        setAllDone(true);
      } else {
        setAnswer("");
        setCurrentIdx((prev) => prev + 1);
      }
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }

  if (questions.length === 0) {
    return (
      <div className="py-12 text-center text-gray-500">Loading questions…</div>
    );
  }

  if (allDone) {
    return (
      <div className="py-12 text-center space-y-4">
        <h2 className="text-2xl font-bold">All done! 🎉</h2>
        <p className="text-gray-500">
          Generating answer choices… please wait.
        </p>
        <div className="animate-pulse text-purple-500">●●●</div>
      </div>
    );
  }

  const q = questions[currentIdx];

  return (
    <div className="max-w-lg mx-auto py-12 space-y-6">
      {/* Progress */}
      <div className="flex items-center justify-between text-sm text-gray-500">
        <span>
          Question {currentIdx + 1} of {questions.length}
        </span>
      </div>
      <div className="w-full bg-gray-200 dark:bg-gray-700 rounded-full h-2">
        <div
          className="bg-purple-600 h-2 rounded-full transition-all"
          style={{ width: `${((currentIdx + 1) / questions.length) * 100}%` }}
        />
      </div>

      {/* Question */}
      <h2 className="text-xl font-semibold">{q.prompt_text}</h2>

      {/* Answer input */}
      <textarea
        value={answer}
        onChange={(e) => setAnswer(e.target.value)}
        placeholder="Type your answer…"
        rows={3}
        className="w-full px-4 py-3 border rounded-lg bg-white dark:bg-gray-800 focus:ring-2 focus:ring-purple-500 outline-none resize-none"
      />

      {error && <p className="text-red-500 text-sm">{error}</p>}

      <button
        onClick={handleSubmit}
        disabled={loading || answer.trim().length < 3}
        className="w-full px-6 py-3 bg-purple-600 text-white rounded-lg hover:bg-purple-700 transition disabled:opacity-50"
      >
        {loading
          ? "Submitting…"
          : currentIdx === questions.length - 1
          ? "Finish"
          : "Next"}
      </button>
    </div>
  );
}
