"use client";

import { useEffect, useState, useCallback } from "react";
import { useParams, useRouter } from "next/navigation";
import {
  ApiError,
  AnswerProgress,
  getAnswerProgress,
  getGamePrompts,
  getGameState,
  startWithFinished,
  submitGameAnswer,
} from "@/lib/api";
import { usePolling } from "@/lib/usePolling";
import { Eyebrow, Heading, PrimaryButton } from "../../../../_components/ui";
import {
  ConnectionBanner,
  LobbyNotFound,
  LobbyUnreachable,
} from "../../../_components/LobbyStatus";

interface Prompt {
  id: string;
  prompt_text: string;
  answered?: boolean;
}

const MAX_ANSWER = 280;

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
  const [others, setOthers] = useState<AnswerProgress | null>(null);
  const [starting, setStarting] = useState(false);

  // Read straight away (not in an effect) so the first load already knows who
  // is looking. null if this device never joined.
  const [participantId] = useState<string | null>(() =>
    typeof window === "undefined" ? null : localStorage.getItem(`game_pid_${experienceId}`)
  );

  useEffect(() => {
    setLoading(true);
    setLoadFailed(false);
    getGamePrompts(experienceId, participantId)
      .then((data) => {
        const list = data.prompts;
        setPrompts(list);
        // Pick up where this person left off after a reload or a dropped connection.
        const firstOpen = list.findIndex((p) => !p.answered);
        if (list.length > 0 && firstOpen === -1) {
          setDone(true);
          setWaitingForOthers(true);
        } else {
          setCurrentIdx(Math.max(firstOpen, 0));
        }
      })
      .catch((e: any) => {
        if (e instanceof ApiError && (e.status === 404 || e.status === 410)) {
          setNotFound(true);
        } else {
          setLoadFailed(true);
        }
      })
      .finally(() => setLoading(false));
  }, [experienceId, participantId, reloadKey]);

  // Poll for state transition once all our answers are in
  // Throws on failure so usePolling can back off and surface outages.
  const pollState = useCallback(async () => {
    if (!waitingForOthers) return;
    const state = await getGameState(experienceId, participantId);
    // Who has finished, so nobody is left guessing why the game has not started.
    // A hiccup here must not look like an outage, the state check above is what counts.
    getAnswerProgress(experienceId, participantId).then(setOthers).catch(() => {});
    if (
      state.game_state === "round_active" ||
      state.game_state === "ready_to_start"
    ) {
      router.push(`/games/experience/${experienceId}/play`);
    }
  }, [experienceId, router, waitingForOthers, participantId]);

  const { failures, fatal, gaveUp, retry } = usePolling(pollState);

  // Show who is still answering as soon as we start waiting, not three seconds later.
  useEffect(() => {
    if (!waitingForOthers) return;
    getAnswerProgress(experienceId, participantId).then(setOthers).catch(() => {});
  }, [waitingForOthers, experienceId, participantId]);

  function afterAnswer(allSubmitted?: boolean) {
    setAnswer("");
    if (currentIdx + 1 < prompts.length) {
      setCurrentIdx(currentIdx + 1);
    } else {
      setDone(true);
      if (allSubmitted) {
        router.push(`/games/experience/${experienceId}/play`);
      } else {
        setWaitingForOthers(true);
      }
    }
  }

  async function handleStartNow() {
    if (!participantId) return;
    setStarting(true);
    setError("");
    try {
      await startWithFinished(experienceId, participantId);
      router.push(`/games/experience/${experienceId}/play`);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setStarting(false);
    }
  }

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
      afterAnswer(res.all_submitted);
    } catch (e: any) {
      // Answered already (another tab, or a retry): just move on.
      if (e instanceof ApiError && e.status === 409 && /already answered/i.test(e.message)) {
        afterAnswer(false);
      } else {
        setError(e.message);
      }
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

  if (!participantId) {
    return (
      <div className="max-w-md mx-auto py-16 text-center space-y-2">
        <Heading size={28}>You&apos;re not in this game</Heading>
        <p className="text-muted">Ask the host for the join code to take part.</p>
      </div>
    );
  }

  if (done) {
    const waiting = others ? others.players.filter((p) => !p.finished) : [];
    return (
      <div className="max-w-md mx-auto py-16 space-y-6 text-center">
        <div className="space-y-4">
          <Heading>All done</Heading>
          <p className="text-muted">Waiting for the other players to finish their answers…</p>
          <div className="animate-pulse text-accent text-lg">⏳</div>
        </div>

        {others && others.players.length > 0 && (
          <ul className="border-t border-soft text-left" aria-label="Who has finished">
            {others.players.map((p) => (
              <li
                key={p.id}
                className="flex items-center justify-between border-b border-soft min-h-[52px] text-[17px]"
              >
                <span className={p.finished ? "" : "text-muted"}>{p.display_name}</span>
                <span className="text-sm text-muted tabular-nums">
                  {p.finished
                    ? "Done"
                    : `${p.answered} of ${others.total_questions}${p.away ? " · away" : ""}`}
                </span>
              </li>
            ))}
          </ul>
        )}

        {others?.can_start_now && (
          <div className="space-y-2 text-left">
            <PrimaryButton onClick={handleStartNow} disabled={starting}>
              {starting
                ? "Starting…"
                : `Start with the ${others.finished_count} who have finished`}
            </PrimaryButton>
            <p className="text-xs text-muted text-center">
              {waiting.map((p) => p.display_name).join(", ")} won&apos;t be in this game but can join
              the next one.
            </p>
          </div>
        )}
        {error && (
          <p role="alert" className="text-red-500 text-sm">
            {error}
          </p>
        )}

        {failures > 0 && (
          <div className="text-left">
            <ConnectionBanner gaveUp={gaveUp} onRetry={retry} />
          </div>
        )}
      </div>
    );
  }

  const prompt = prompts[currentIdx];
  const progress = (currentIdx / prompts.length) * 100;
  const last = currentIdx + 1 >= prompts.length;

  return (
    <div className="max-w-md mx-auto flex flex-col gap-6 py-8">
      <div className="flex flex-col gap-3">
        <div className="flex items-baseline justify-between">
          <Eyebrow>About you</Eyebrow>
          <span className="text-sm text-muted tabular-nums">
            {currentIdx + 1} of {prompts.length}
          </span>
        </div>
        <div className="h-[3px] bg-soft">
          <div className="h-[3px] bg-accent transition-all" style={{ width: `${progress}%` }} />
        </div>
      </div>

      <Heading size={28}>{prompt?.prompt_text}</Heading>

      <textarea
        key={prompt?.id}
        value={answer}
        onChange={(e) => setAnswer(e.target.value)}
        placeholder="Type your answer…"
        aria-label="Your answer"
        rows={4}
        maxLength={MAX_ANSWER}
        className="w-full px-4 py-3 border rounded-md bg-surface text-[17px] resize-none"
      />

      {error && (
        <p role="alert" className="text-red-500 text-sm">
          {error}
        </p>
      )}

      <PrimaryButton onClick={handleSubmit} disabled={submitting || !answer.trim()}>
        {submitting ? "Saving…" : last ? "Finish" : "Next"}
      </PrimaryButton>
      <p className="text-center text-xs text-muted">
        Answers are shown without names. Friends guess who wrote each one.
      </p>
    </div>
  );
}
