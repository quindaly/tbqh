"use client";

import { useCallback, useEffect, useMemo, useRef, useState, useSyncExternalStore } from "react";
import { useParams, useRouter } from "next/navigation";
import {
  ApiError,
  PhaseInfo,
  getHWDYKLobby,
  getReviewChoices,
  editChoice,
  regenerateChoice,
  confirmChoices,
} from "@/lib/api";
import { ChoiceSaver, ChoiceState, SaveFailure } from "@/lib/choiceSaver";
import { formatClock, useCountdown } from "@/lib/countdown";
import { usePolling } from "@/lib/usePolling";

const MAX_REGENERATIONS = 3;
const MAX_CHOICE_LEN = 120;

interface Choice {
  id: string;
  text: string;
  is_correct: boolean;
  source_type: string;
  revision: number;
  regenerations_used: number;
}

interface Round {
  round_id: string;
  round_number: number;
  question_text: string;
  choices: Choice[];
}

function classify(err: unknown): SaveFailure {
  if (err instanceof ApiError) {
    return { status: err.status, code: err.code, message: err.message };
  }
  return { status: 0, message: "Couldn't save. Check your connection." };
}

function statusLabel(s: ChoiceState | undefined): { text: string; tone: string } | null {
  if (!s) return null;
  switch (s.status) {
    case "dirty":
      return { text: "Unsaved…", tone: "text-gray-400" };
    case "saving":
      return { text: "Saving…", tone: "text-gray-400" };
    case "saved":
      return s.revision > 0 ? { text: "Saved", tone: "text-green-600" } : null;
    case "invalid":
      return { text: s.message || "That answer can't be used", tone: "text-red-500" };
    case "stale":
      return { text: s.message || "This answer changed elsewhere", tone: "text-red-500" };
    case "error":
      return { text: s.message || "Couldn't save", tone: "text-red-500" };
  }
}

export default function ReviewPage() {
  const { experienceId } = useParams<{ experienceId: string }>();
  const router = useRouter();

  const [rounds, setRounds] = useState<Round[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState("");
  const [error, setError] = useState("");
  const [confirming, setConfirming] = useState(false);
  const [regenerating, setRegenerating] = useState<Record<string, boolean>>({});
  const [regenUsed, setRegenUsed] = useState<Record<string, number>>({});
  const [phase, setPhase] = useState<PhaseInfo | null>(null);
  const [phaseReceivedAt, setPhaseReceivedAt] = useState(0);
  const [timeUp, setTimeUp] = useState(false);
  const timeUpHandled = useRef(false);
  const [participantId] = useState(() =>
    typeof window !== "undefined"
      ? localStorage.getItem(`game_pid_${experienceId}`) || ""
      : ""
  );

  const saver = useMemo(
    () =>
      new ChoiceSaver(async (choiceId, text, expectedRevision) => {
        const res = await editChoice(
          experienceId,
          choiceId,
          participantId,
          text,
          expectedRevision
        );
        return { text: res.text, revision: res.revision };
      }, classify),
    [experienceId, participantId]
  );
  const choiceStates = useSyncExternalStore(
    (cb) => saver.subscribe(cb),
    () => saver.getAll(),
    () => saver.getAll()
  );

  useEffect(() => () => saver.dispose(), [saver]);

  const remaining = useCountdown(phase, phaseReceivedAt);
  const lobbyPath = `/games/experience/${experienceId}/hwdyk-lobby`;

  const applyPhase = useCallback((p: PhaseInfo | null) => {
    setPhase(p);
    setPhaseReceivedAt(Date.now());
  }, []);

  const loadData = useCallback(async () => {
    setLoadError("");
    try {
      const res = await getReviewChoices(experienceId, participantId);
      // The game moved on (confirmed from another tab, or the phase ended).
      if (res.game_state !== "main_person_reviewing_choices") {
        router.replace(`/games/experience/${experienceId}/hwdyk-lobby`);
        return;
      }
      applyPhase(res.phase);
      setRounds(res.rounds);
      saver.load(
        res.rounds.flatMap((r) =>
          r.choices.map((c) => ({ id: c.id, text: c.text, revision: c.revision }))
        )
      );
      setRegenUsed(
        Object.fromEntries(
          res.rounds.flatMap((r) => r.choices.map((c) => [c.id, c.regenerations_used]))
        )
      );
    } catch (e: any) {
      setLoadError(e.message || "Couldn't load your answer choices.");
    } finally {
      setLoading(false);
    }
  }, [experienceId, participantId, router, saver, applyPhase]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  // Keep the clock honest, and leave when the game moves on without us
  // (time ran out and the server locked the saved choices, or setup was reset).
  usePolling(
    useCallback(async () => {
      const lobby = await getHWDYKLobby(experienceId);
      if (lobby.game_state !== "main_person_reviewing_choices") {
        router.replace(lobbyPath);
        return;
      }
      applyPhase(lobby.phase);
    }, [experienceId, router, lobbyPath, applyPhase]),
    { baseMs: 3000 }
  );

  // Time's up: send anything still being typed (the server takes it only if it
  // lands inside its short grace window), then hand over to the lobby.
  useEffect(() => {
    if (remaining === null || remaining > 0 || timeUpHandled.current) return;
    timeUpHandled.current = true;
    setTimeUp(true);
    (async () => {
      await saver.flush();
      router.push(lobbyPath);
    })();
  }, [remaining, saver, router, lobbyPath]);

  async function handleRegenerate(choice: Choice) {
    const st = saver.get(choice.id);
    if (!st) return;
    setError("");
    setRegenerating((p) => ({ ...p, [choice.id]: true }));
    try {
      // Anything typed must be saved first so the AI never replaces unsaved text.
      await saver.flushOne(choice.id);
      const after = saver.get(choice.id)!;
      if (after.status !== "saved") {
        setError("Fix this answer before asking for a new one.");
        return;
      }
      const res = await regenerateChoice(
        experienceId,
        choice.id,
        participantId,
        after.revision
      );
      saver.adopt(choice.id, res.text, res.revision);
      setRegenUsed((p) => ({ ...p, [choice.id]: res.regenerations_used }));
    } catch (e: any) {
      if (e instanceof ApiError && e.code === "stale_revision") {
        setError(e.message);
        await loadData();
      } else {
        if (e?.status === 429) setRegenUsed((p) => ({ ...p, [choice.id]: MAX_REGENERATIONS }));
        setError(e.message || "Couldn't generate a new answer.");
      }
    } finally {
      setRegenerating((p) => ({ ...p, [choice.id]: false }));
    }
  }

  async function handleConfirm() {
    setConfirming(true);
    setError("");
    try {
      // Push out anything still being typed, then verify the screen == database.
      const clean = await saver.flush();
      if (!clean) {
        setError("Some answers couldn't be saved. Fix the highlighted ones and try again.");
        return;
      }
      await confirmChoices(experienceId, participantId, saver.revisions());
      router.push(`/games/experience/${experienceId}/hwdyk-lobby`);
    } catch (e: any) {
      if (e instanceof ApiError && e.code === "stale_revision") {
        setError(e.message);
        await loadData();
      } else if (e instanceof ApiError && e.code === "choices_locked") {
        router.replace(`/games/experience/${experienceId}/hwdyk-lobby`);
      } else {
        setError(e.message || "Couldn't lock your choices. Try again.");
      }
    } finally {
      setConfirming(false);
    }
  }

  if (!participantId) {
    return (
      <div className="py-12 text-center text-gray-500">
        We couldn't tell who you are in this game. Open the game from the link you used to join.
      </div>
    );
  }

  if (loading) {
    return <div className="py-12 text-center text-gray-500">Loading choices…</div>;
  }

  if (loadError && rounds.length === 0) {
    return (
      <div className="py-12 text-center space-y-4">
        <p className="text-gray-500">{loadError}</p>
        <button
          onClick={() => {
            setLoading(true);
            loadData();
          }}
          className="px-6 py-3 bg-purple-600 text-white rounded-lg hover:bg-purple-700 transition"
        >
          Try again
        </button>
      </div>
    );
  }

  const states = Object.values(choiceStates);
  const anyBusy =
    states.some((s) => s.status === "saving" || s.status === "dirty") ||
    Object.values(regenerating).some(Boolean);
  const anyProblem = states.some(
    (s) => s.status === "invalid" || s.status === "error" || s.status === "stale"
  );
  const confirmDisabled = confirming || anyBusy || anyProblem || timeUp;
  const confirmLabel = timeUp
    ? "Time's up — locking in your saved changes…"
    : confirming
    ? "Locking choices…"
    : anyBusy
    ? "Saving your changes…"
    : anyProblem
    ? "Fix the highlighted answers"
    : "Confirm All & Lock Game";

  return (
    <div className="max-w-2xl mx-auto py-12 space-y-8">
      <div className="text-center space-y-2">
        {remaining !== null && (
          <p
            className={`text-lg font-mono font-bold ${
              remaining <= 10 ? "text-red-500" : "text-gray-700 dark:text-gray-300"
            }`}
            aria-label={`${Math.ceil(remaining)} seconds left`}
          >
            {formatClock(remaining)}
          </p>
        )}
        <h1 className="text-2xl font-bold">Review Answer Choices</h1>
        <p className="text-gray-500">
          Check the AI-generated wrong answers. Change any that don't look right — your
          edits save automatically. When time runs out, the game uses what's saved.
        </p>
      </div>

      {error && (
        <p role="alert" className="text-red-500 text-sm text-center">
          {error}
        </p>
      )}

      {rounds.map((round) => (
        <div
          key={round.round_id}
          className="border rounded-xl p-6 space-y-4 bg-white dark:bg-gray-900"
        >
          <div className="flex items-center gap-2">
            <span className="text-xs bg-purple-100 dark:bg-purple-900/30 text-purple-700 dark:text-purple-300 px-2 py-1 rounded-full">
              Q{round.round_number}
            </span>
            <h3 className="font-medium">{round.question_text}</h3>
          </div>

          <div className="space-y-2">
            {round.choices.map((choice) => {
              const st = choiceStates[choice.id];
              const label = statusLabel(st);
              const used = regenUsed[choice.id] ?? choice.regenerations_used;
              const isRegenerating = !!regenerating[choice.id];
              const regenDisabled =
                isRegenerating || used >= MAX_REGENERATIONS || st?.status === "stale";

              return (
                <div
                  key={choice.id}
                  className={`px-4 py-3 rounded-lg border ${
                    choice.is_correct
                      ? "border-green-300 bg-green-50 dark:bg-green-900/20 dark:border-green-800"
                      : st?.status === "invalid" || st?.status === "error" || st?.status === "stale"
                      ? "border-red-300 dark:border-red-800"
                      : "border-gray-200 dark:border-gray-700"
                  }`}
                >
                  {choice.is_correct ? (
                    <div className="flex items-center justify-between">
                      <span className="text-sm">{choice.text}</span>
                      <span className="text-xs text-green-600 font-medium ml-2">
                        ✓ Your answer
                      </span>
                    </div>
                  ) : (
                    <>
                      <div className="flex items-center gap-2">
                        <input
                          type="text"
                          value={st?.draft ?? choice.text}
                          maxLength={MAX_CHOICE_LEN}
                          aria-label={`Wrong answer for question ${round.round_number}`}
                          onChange={(e) => saver.setDraft(choice.id, e.target.value)}
                          onBlur={() => void saver.flushOne(choice.id)}
                          onKeyDown={(e) => {
                            if (e.key === "Enter") {
                              e.preventDefault();
                              void saver.flushOne(choice.id);
                              (e.target as HTMLInputElement).blur();
                            }
                          }}
                          disabled={isRegenerating}
                          className="flex-1 min-w-0 px-3 py-1.5 border rounded bg-white dark:bg-gray-800 text-sm disabled:opacity-60"
                        />
                        <button
                          onClick={() => handleRegenerate(choice)}
                          disabled={regenDisabled}
                          className="text-xs px-2 py-1.5 rounded border text-gray-600 dark:text-gray-300 hover:text-purple-600 disabled:opacity-40 disabled:cursor-not-allowed shrink-0"
                          title={
                            used >= MAX_REGENERATIONS
                              ? "Limit of 3 AI regenerations per answer"
                              : `Get a new AI suggestion (${MAX_REGENERATIONS - used} left)`
                          }
                        >
                          {isRegenerating ? "…" : "🔄 New"}
                        </button>
                      </div>
                      <p
                        className={`mt-1 text-xs min-h-[1rem] ${label?.tone ?? ""}`}
                        aria-live="polite"
                      >
                        {isRegenerating ? "Thinking of a new answer…" : label?.text ?? ""}
                      </p>
                    </>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      ))}

      <button
        onClick={handleConfirm}
        disabled={confirmDisabled}
        className="w-full px-6 py-3 bg-purple-600 text-white rounded-lg hover:bg-purple-700 transition disabled:opacity-50 text-lg font-medium"
      >
        {confirmLabel}
      </button>
    </div>
  );
}
