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
  skipped: boolean;
  current: boolean;
}

const MIN_ANSWER_LEN = 3;

export default function AnswerPage() {
  const { experienceId } = useParams<{ experienceId: string }>();
  const router = useRouter();
  const lobbyPath = `/games/experience/${experienceId}/hwdyk-lobby`;

  const [questions, setQuestions] = useState<Question[]>([]);
  // The server decides which question is up; each one has its own 20 seconds.
  const [currentIdx, setCurrentIdx] = useState(0);
  const [answer, setAnswer] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [loadError, setLoadError] = useState("");
  const [loaded, setLoaded] = useState(false);
  const [phase, setPhase] = useState<PhaseInfo | null>(null);
  const [phaseReceivedAt, setPhaseReceivedAt] = useState(0);
  // Which question we've already made a last-second save attempt for.
  const lastGaspFor = useRef(-1);
  const idxRef = useRef(0);
  idxRef.current = currentIdx;

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

  // Move to the question the server says is up. If it is further on than the
  // one on screen, the one we were on ran out of time (or was answered elsewhere).
  const goToQuestion = useCallback(
    (index: number, p: PhaseInfo | null, byTimeout: boolean) => {
      if (index !== idxRef.current) {
        setAnswer("");
        setError("");
        if (byTimeout) setNotice("Time's up for that one. On to the next!");
        setCurrentIdx(index);
      }
      applyPhase(p);
    },
    [applyPhase]
  );

  const loadQuestions = useCallback(async () => {
    setLoadError("");
    try {
      const res = await getMainPersonQuestions(experienceId);
      if (res.game_state !== "main_person_answering") {
        router.replace(lobbyPath);
        return;
      }
      setQuestions(res.questions);
      if (!loaded) {
        setCurrentIdx(res.current_index);
        idxRef.current = res.current_index;
        applyPhase(res.phase);
      } else {
        goToQuestion(res.current_index, res.phase, true);
      }
      setLoaded(true);
    } catch (e: any) {
      if (!loaded) setLoadError(e.message || "Couldn't load your questions.");
    }
  }, [experienceId, router, lobbyPath, applyPhase, goToQuestion, loaded]);

  useEffect(() => {
    loadQuestions();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Keep the clock honest and notice when the game moves on without us (a
  // question timed out, or answering is over).
  const { fatal, gaveUp, retry } = usePolling(
    useCallback(async () => {
      const lobby = await getHWDYKLobby(experienceId);
      if (lobby.game_state !== "main_person_answering") {
        router.replace(lobbyPath);
        return;
      }
      if (lobby.progress) goToQuestion(lobby.progress.current_index, lobby.phase, true);
      else applyPhase(lobby.phase);
    }, [experienceId, router, lobbyPath, applyPhase, goToQuestion]),
    { baseMs: 3000 }
  );

  const currentQuestion = questions[currentIdx];
  const isLast = currentIdx === questions.length - 1;

  const submitCurrent = useCallback(
    async (text: string): Promise<"done" | "next" | "stale" | "error"> => {
      const q = questions[currentIdx];
      if (!q) return "error";
      try {
        const res = await submitMainPersonAnswer(experienceId, q.id, participantId, text);
        if (res.all_answered) return "done";
        setQuestions((prev) =>
          prev.map((x) => (x.id === q.id ? { ...x, answered: true } : x))
        );
        goToQuestion(res.current_index ?? currentIdx + 1, res.phase, false);
        return "next";
      } catch (e: any) {
        if (e instanceof ApiError && e.status === 409) {
          // Too late (that question was skipped) or setup moved on.
          if (e.code === "answering_closed") return "done";
          if (e.code === "already_answered") return "next";
          return "stale";
        }
        setError(e.message || "Couldn't save that answer. Try again.");
        return "error";
      }
    },
    [questions, currentIdx, experienceId, participantId, goToQuestion]
  );

  async function handleSubmit() {
    const text = answer.trim();
    if (text.length < MIN_ANSWER_LEN) {
      setError(`Answer must be at least ${MIN_ANSWER_LEN} characters`);
      return;
    }
    if (submitting) return;
    setSubmitting(true);
    setError("");
    setNotice("");
    const result = await submitCurrent(text);
    setSubmitting(false);
    if (result === "done") router.push(lobbyPath);
    else if (result === "stale") loadQuestions();
  }

  // This question's time is up: one last attempt to save what is in the box
  // (the server takes it only if it lands inside its short grace window), then
  // keep asking the server which question is up until it moves on.
  useEffect(() => {
    if (!loaded || remaining === null || remaining > 0) return;
    const idx = currentIdx;
    if (lastGaspFor.current !== idx) {
      lastGaspFor.current = idx;
      const text = answer.trim();
      if (text.length >= MIN_ANSWER_LEN) {
        submitCurrent(text).then((r) => {
          if (r === "done") router.push(lobbyPath);
        });
      }
    }
    const timer = setInterval(() => loadQuestions(), 1000);
    return () => clearInterval(timer);
  }, [remaining, loaded, currentIdx, answer, submitCurrent, loadQuestions, router, lobbyPath]);

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

  const low = remaining !== null && remaining <= 5;
  const perQuestion = phase?.duration_seconds || 20;

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

      {/* Progress + this question's clock */}
      <div className="flex items-center justify-between text-sm text-gray-500">
        <span>
          Question {currentIdx + 1} of {questions.length}
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
          style={{ width: `${(currentIdx / questions.length) * 100}%` }}
        />
      </div>
      {/* The clock bar for this question */}
      {remaining !== null && (
        <div className="w-full bg-gray-100 dark:bg-gray-800 rounded-full h-1" aria-hidden="true">
          <div
            className={`h-1 rounded-full ${low ? "bg-red-500" : "bg-purple-400"}`}
            style={{ width: `${Math.min(100, (remaining / perQuestion) * 100)}%` }}
          />
        </div>
      )}
      <p className="text-xs text-gray-400">
        You have {perQuestion} seconds for each question. Press{" "}
        {isLast ? "Finish" : "Next"} to save; if time runs out, that question is
        skipped.
      </p>

      {notice && (
        <p role="status" className="text-sm text-yellow-700 dark:text-yellow-300">
          {notice}
        </p>
      )}

      {/* Question */}
      <h2 className="text-xl font-semibold">{currentQuestion.prompt_text}</h2>

      {/* Answer input */}
      <textarea
        key={currentQuestion.id}
        autoFocus
        value={answer}
        onChange={(e) => setAnswer(e.target.value)}
        onKeyDown={(e) => {
          // Enter saves (Shift+Enter makes a new line): quicker against the clock.
          if (e.key === "Enter" && !e.shiftKey) {
            e.preventDefault();
            handleSubmit();
          }
        }}
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
        {submitting ? "Saving…" : isLast ? "Finish" : "Next"}
      </button>
    </div>
  );
}
