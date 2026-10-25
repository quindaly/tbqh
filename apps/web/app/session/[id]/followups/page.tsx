"use client";

import { useState, useEffect } from "react";
import { useParams, useRouter } from "next/navigation";
import { getFollowups, answerFollowup, commitGroupProfile } from "@/lib/api";
import { isOtherOption, readSession, rememberSession } from "@/lib/discussionSession";
import { LoadError } from "../../../_components/LoadError";
import { Eyebrow, PrimaryButton, BackLink } from "../../../_components/ui";

interface Prompt {
  id: string;
  prompt_text: string;
  options: string[];
}

interface Answer {
  option: string | null;
  otherText: string;
}

export default function FollowupsPage() {
  const params = useParams();
  const router = useRouter();
  const sessionId = params.id as string;

  const [prompts, setPrompts] = useState<Prompt[]>([]);
  const [provisionalId, setProvisionalId] = useState<string | null>(null);
  const [participantId, setParticipantId] = useState<string | undefined>();
  const [currentIdx, setCurrentIdx] = useState(0);
  const [answers, setAnswers] = useState<Record<string, Answer>>({});
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [loadError, setLoadError] = useState("");
  const [reloadKey, setReloadKey] = useState(0);

  useEffect(() => {
    const mem = readSession(sessionId);
    setParticipantId(mem.participantId);
    setLoading(true);
    setLoadError("");
    getFollowups(sessionId)
      .then((data) => {
        setPrompts(data.prompts);
        setProvisionalId(data.provisional_group_profile_id ?? mem.provisionalProfileId ?? null);
      })
      .catch((err) => setLoadError(err.message || "Couldn't load the follow-ups."))
      .finally(() => setLoading(false));
  }, [sessionId, reloadKey]);

  const total = prompts.length;
  const prompt = prompts[currentIdx];
  const answer: Answer = (prompt && answers[prompt.id]) || { option: null, otherText: "" };
  const wantsOther = isOtherOption(answer.option);
  const ready = !!answer.option && (!wantsOther || answer.otherText.trim().length > 0);
  const isLast = currentIdx >= total - 1;

  const setAnswer = (patch: Partial<Answer>) =>
    setAnswers((prev) => ({ ...prev, [prompt.id]: { ...answer, ...patch } }));

  async function buildProfile() {
    if (!provisionalId) {
      throw new Error("We lost track of your description. Go back and describe your group again.");
    }
    const result = await commitGroupProfile(sessionId, provisionalId);
    rememberSession(sessionId, {
      groupProfileId: result.group_profile_id,
      experienceId: undefined, // a new profile starts fresh questions
    });
    router.push(`/session/${sessionId}/questions`);
  }

  async function handleNext(skip = false) {
    if (!prompt || !participantId) return;
    setBusy(true);
    setError("");
    try {
      if (!skip) {
        await answerFollowup(
          sessionId,
          prompt.id,
          participantId,
          wantsOther ? null : answer.option,
          wantsOther ? answer.otherText.trim() : null
        );
      }
      if (isLast) await buildProfile();
      else setCurrentIdx((i) => i + 1);
    } catch (err: any) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  if (loading) return <p className="text-center py-16 text-muted">Loading follow-ups…</p>;
  if (loadError) {
    return <LoadError message={loadError} onRetry={() => setReloadKey((n) => n + 1)} />;
  }
  if (!participantId) {
    return (
      <div className="max-w-md mx-auto py-12 space-y-4 text-center">
        <p className="text-muted">This browser isn&rsquo;t part of the session yet.</p>
        <PrimaryButton onClick={() => router.push(`/join?s=${sessionId}`)}>Join</PrimaryButton>
      </div>
    );
  }
  if (!total) {
    return (
      <div className="max-w-md mx-auto py-16 space-y-5 text-center">
        <p className="text-muted">No follow-up questions this time. We have enough to go on.</p>
        {error && (
          <p role="alert" className="text-red-500 text-sm">
            {error}
          </p>
        )}
        <PrimaryButton
          disabled={busy}
          onClick={async () => {
            setBusy(true);
            setError("");
            try {
              await buildProfile();
            } catch (e: any) {
              setError(e.message);
            } finally {
              setBusy(false);
            }
          }}
        >
          {busy ? "Building…" : "Get questions"}
        </PrimaryButton>
      </div>
    );
  }

  return (
    <div className="max-w-md mx-auto py-8 space-y-6">
      <div className="space-y-3">
        <Eyebrow>
          Step 2 of 3 · Question {currentIdx + 1} of {total}
        </Eyebrow>
        <div className="w-full bg-soft rounded-full h-1.5" aria-hidden>
          <div
            className="bg-accent h-1.5 rounded-full transition-all"
            style={{ width: `${((currentIdx + 1) / total) * 100}%` }}
          />
        </div>
      </div>

      <h1 className="font-serif text-[28px] leading-[1.15] font-normal">{prompt.prompt_text}</h1>

      <div className="space-y-2" role="radiogroup" aria-label={prompt.prompt_text}>
        {prompt.options.map((opt) => {
          const selected = answer.option === opt;
          return (
            <button
              key={opt}
              role="radio"
              aria-checked={selected}
              onClick={() => setAnswer({ option: opt })}
              className={`w-full text-left px-4 py-3 min-h-[52px] rounded-md border transition ${
                selected ? "border-accent bg-selected" : "border-soft hover:bg-soft"
              }`}
            >
              {opt}
            </button>
          );
        })}
      </div>

      {wantsOther && (
        <input
          type="text"
          autoFocus
          aria-label="Your answer"
          placeholder="Type your own…"
          maxLength={200}
          value={answer.otherText}
          onChange={(e) => setAnswer({ otherText: e.target.value })}
          className="w-full px-4 py-3 border border-line rounded-md bg-surface min-h-[56px]"
        />
      )}

      {error && (
        <p role="alert" className="text-red-500 text-sm">
          {error}
        </p>
      )}

      <div className="space-y-3">
        <PrimaryButton onClick={() => handleNext(false)} disabled={busy || !ready}>
          {busy ? (isLast ? "Building your profile…" : "Saving…") : isLast ? "Get my questions" : "Next"}
        </PrimaryButton>
        <div className="flex justify-between">
          {currentIdx > 0 ? (
            <BackLink onClick={() => setCurrentIdx((i) => i - 1)} />
          ) : (
            <BackLink onClick={() => router.push(`/session/${sessionId}`)}>← Edit description</BackLink>
          )}
          <button
            onClick={() => handleNext(true)}
            disabled={busy}
            className="text-sm text-muted hover:underline disabled:opacity-50"
          >
            {isLast ? "Skip and finish" : "Skip"}
          </button>
        </div>
      </div>
    </div>
  );
}
