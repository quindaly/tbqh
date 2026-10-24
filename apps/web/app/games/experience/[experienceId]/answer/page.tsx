"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import {
  ApiError,
  PhaseInfo,
  getHWDYKLobby,
  getMainPersonQuestions,
  submitMainPersonAnswer,
} from "@/lib/api";
import { formatClock, useCountdown } from "@/lib/countdown";
import { usePolling } from "@/lib/usePolling";

interface Question {
  id: string;
  prompt_text: string;
  round_number: number;
  answered: boolean;
}

const MIN_ANSWER_LEN = 3;

export default function AnswerPage() {
  const { experienceId } = useParams<{ experienceId: string }>();
  const router = useRouter();
  const lobbyPath = `/games/experience/${experienceId}/hwdyk-lobby`;

  const [questions, setQuestions] = useState<Question[]>([]);
  const [currentIdx, setCurrentIdx] = useState(0);
  const [answer, setAnswer] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");
  const [loadError, setLoadError] = useState("");
  const [loaded, setLoaded] = useState(false);
  const [phase, setPhase] = useState<PhaseInfo | null>(null);
  const [phaseReceivedAt, setPhaseReceivedAt] = useState(0);
  const finalizing = useRef(false);

  const [participantId] = useState(() =>
    typeof window !== "undefined"
      ? localStorage.getItem(`game_pid_${experienceId}`) || ""
      : ""
  );

  const remaining = useCountdown(phase, phaseReceivedAt);

  const applyPhase = useCallback((p: PhaseInfo | null) => {
    setPhase(p);
    setPhaseReceivedAt(Date.now());
  }, []);

  const loadQuestions = useCallback(async () => {
    setLoadError("");
    try {
      const res = await getMainPersonQuestions(experienceId);
      if (res.game_state !== "main_person_answering") {
        router.replace(lobbyPath);
        return;
      }
      setQuestions(res.questions);
      applyPhase(res.phase);
      // Resume where we left off: answers are saved one by one.
      const next = res.questions.findIndex((q) => !q.answered);
      if (next === -1) {
        router.replace(lobbyPath);
        return;
      }
      setCurrentIdx(next);
      setLoaded(true);
    } catch (e: any) {
      setLoadError(e.message || "Couldn't load your questions.");
    }
  }, [experienceId, router, lobbyPath, applyPhase]);

  useEffect(() => {
    loadQuestions();
  }, [loadQuestions]);

  // Keep the clock honest and notice when the game moves on without us
  // (time ran out, or the host reset setup).
  const { fatal, gaveUp, retry } = usePolling(
    useCallback(async () => {
      const lobby = await getHWDYKLobby(experienceId);
      if (lobby.game_state !== "main_person_answering") {
        router.replace(lobbyPath);
        return;
      }
      applyPhase(lobby.phase);
    }, [experienceId, router, lobbyPath, applyPhase]),
    { baseMs: 3000 }
  );

  const currentQuestion = questions[currentIdx];

  const submitCurrent = useCallback(
    async (text: string): Promise<"done" | "next" | "closed" | "error"> => {
      const q = questions[currentIdx];
      if (!q) return "error";
      try {
        const res = await submitMainPersonAnswer(experienceId, q.id, participantId, text);
        if (res.all_answered) return "done";
        setQuestions((prev) =>
          prev.map((x) => (x.id === q.id ? { ...x, answered: true } : x))
        );
        return "next";
      } catch (e: any) {
        if (e instanceof ApiError && e.code === "answering_closed") return "closed";
        if (e instanceof ApiError && e.code === "already_answered") {
          setQuestions((prev) =>
            prev.map((x) => (x.id === q.id ? { ...x, answered: true } : x))
          );
          return "next";
        }
        setError(e.message || "Couldn't save that answer. Try again.");
        return "error";
      }
    },
    [questions, currentIdx, experienceId, participantId]
  );

  async function handleSubmit() {
    const text = answer.trim();
    if (text.length < MIN_ANSWER_LEN) {
      setError(`Answer must be at least ${MIN_ANSWER_LEN} characters`);
      return;
    }
    setSubmitting(true);
    setError("");
    const result = await submitCurrent(text);
    setSubmitting(false);
    if (result === "done" || result === "closed") {
      router.push(lobbyPath);
    } else if (result === "next") {
      setAnswer("");
      const nextIdx = questions.findIndex((q, i) => i > currentIdx && !q.answered);
      if (nextIdx === -1) router.push(lobbyPath);
      else setCurrentIdx(nextIdx);
    }
  }

  // Time's up: make one last attempt to save what is in the box (the server
  // accepts it only if it lands inside its short grace window), then leave.
  useEffect(() => {
    if (remaining === null || remaining > 0 || finalizing.current || !loaded) return;
    finalizing.current = true;
    (async () => {
      const text = answer.trim();
      if (text.length >= MIN_ANSWER_LEN) await submitCurrent(text);
      router.push(lobbyPath);
    })();
  }, [remaining, loaded, answer, submitCurrent, router, lobbyPath]);

  if (!participantId) {
    return (
      <div className="py-12 text-center text-gray-500">
        We couldn't tell who you are in this game. Open the game from the link you used to join.
      </div>
    );
  }

  if (fatal) {
    return (
      <div className="py-12 text-center text-gray-500">We couldn't find that game.</div>
    );
  }

  if (loadError && !loaded) {
    return (
      <div className="py-12 text-center space-y-4">
        <p className="text-gray-500">{loadError}</p>
        <button
          onClick={loadQuestions}
          className="px-6 py-3 bg-purple-600 text-white rounded-lg hover:bg-purple-700 transition"
        >
          Try again
        </button>
      </div>
    );
  }

  if (!loaded || !currentQuestion) {
    return <div className="py-12 text-center text-gray-500">Loading questions…</div>;
  }

  const answeredCount = questions.filter((q) => q.answered).length;
  const low = remaining !== null && remaining <= 10;

  return (
    <div className="max-w-lg mx-auto py-12 space-y-6">
      {gaveUp && (
        <div
          role="status"
          className="rounded-lg border border-yellow-300 bg-yellow-50 dark:bg-yellow-900/20 px-3 py-2 text-sm flex justify-between"
        >
          <span>Connection lost. Your saved answers are safe.</span>
          <button onClick={retry} className="font-medium underline">
            Try again
          </button>
        </div>
      )}

      {/* Progress + clock */}
      <div className="flex items-center justify-between text-sm text-gray-500">
        <span>
          Question {Math.min(answeredCount + 1, questions.length)} of {questions.length}
        </span>
        {remaining !== null && (
          <span
            className={`text-lg font-mono font-bold ${
              low ? "text-red-500" : "text-gray-700 dark:text-gray-300"
            }`}
            aria-label={`${Math.ceil(remaining)} seconds left`}
          >
            {formatClock(remaining)}
          </span>
        )}
      </div>
      <div className="w-full bg-gray-200 dark:bg-gray-700 rounded-full h-2">
        <div
          className="bg-purple-600 h-2 rounded-full transition-all"
          style={{ width: `${(answeredCount / questions.length) * 100}%` }}
        />
      </div>
      <p className="text-xs text-gray-400">
        Each answer is saved when you press {answeredCount === questions.length - 1 ? "Finish" : "Next"}.
        If time runs out, the game uses the questions you've answered.
      </p>

      {/* Question */}
      <h2 className="text-xl font-semibold">{currentQuestion.prompt_text}</h2>

      {/* Answer input */}
      <textarea
        value={answer}
        onChange={(e) => setAnswer(e.target.value)}
        placeholder="Type your answer…"
        rows={3}
        maxLength={120}
        className="w-full px-4 py-3 border rounded-lg bg-white dark:bg-gray-800 focus:ring-2 focus:ring-purple-500 outline-none resize-none"
      />

      {error && (
        <p role="alert" className="text-red-500 text-sm">
          {error}
        </p>
      )}

      <button
        onClick={handleSubmit}
        disabled={submitting || answer.trim().length < MIN_ANSWER_LEN}
        className="w-full px-6 py-3 bg-purple-600 text-white rounded-lg hover:bg-purple-700 transition disabled:opacity-50"
      >
        {submitting
          ? "Saving…"
          : answeredCount === questions.length - 1
          ? "Finish"
          : "Next"}
      </button>
    </div>
  );
}
