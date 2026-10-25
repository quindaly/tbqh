"use client";

import { useState, useEffect, useRef } from "react";
import { useParams, useRouter } from "next/navigation";
import {
  ApiError,
  createExperience,
  getRecommendations,
  getMoreRecommendations,
  listExperienceItems,
  submitFeedback,
} from "@/lib/api";
import { adoptResume, readSession, rememberSession } from "@/lib/discussionSession";
import { isSignedIn, useMe } from "../../../_components/Me";
import { LoadError } from "../../../_components/LoadError";
import { Eyebrow, PrimaryButton, SecondaryButton } from "../../../_components/ui";

type Rating = "like" | "dislike" | "skip";

interface ContentItem {
  id: string;
  content_type: string;
  text: string;
  metadata: Record<string, unknown>;
  feedback?: Rating | null;
}

const RATING_NOTE: Record<Rating, string> = {
  like: "Saved to your favorites.",
  dislike: "Got it. We won't suggest this one again.",
  skip: "Skipped.",
};

export default function QuestionsPage() {
  const params = useParams();
  const router = useRouter();
  const sessionId = params.id as string;
  const { me, loaded: meLoaded } = useMe();

  const [experienceId, setExperienceId] = useState<string | null>(null);
  const [participantId, setParticipantId] = useState<string | undefined>();
  const [items, setItems] = useState<ContentItem[]>([]);
  const [ratings, setRatings] = useState<Record<string, Rating>>({});
  const [currentIdx, setCurrentIdx] = useState(0);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [exhausted, setExhausted] = useState(false);
  const [missingProfile, setMissingProfile] = useState(false);
  const [error, setError] = useState("");
  // Loving or blocking a question needs an account; this explains and offers to sign in.
  const [askToSignIn, setAskToSignIn] = useState(false);
  const started = useRef(false);

  useEffect(() => {
    // Strict mode runs effects twice in dev; one batch is enough.
    if (started.current) return;
    started.current = true;
    void initExperience();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function showItems(list: ContentItem[]) {
    setItems(list);
    const done: Record<string, Rating> = {};
    for (const it of list) if (it.feedback) done[it.id] = it.feedback;
    setRatings(done);
    // Resume at the first question nobody has rated yet.
    const firstOpen = list.findIndex((it) => !it.feedback);
    setCurrentIdx(firstOpen === -1 ? Math.max(0, list.length - 1) : firstOpen);
  }

  async function initExperience() {
    setLoading(true);
    setError("");
    try {
      // Coming back from a sign-in link opened in another browser carries the session along.
      adoptResume(sessionId);
      const mem = readSession(sessionId);
      setParticipantId(mem.participantId);
      if (!mem.groupProfileId) {
        setMissingProfile(true);
        return;
      }

      // Reloading continues the same set instead of using up fresh questions.
      if (mem.experienceId) {
        try {
          setExperienceId(mem.experienceId);
          const existing = await listExperienceItems(mem.experienceId, mem.participantId);
          if (existing.content_items.length > 0) {
            showItems(existing.content_items);
            return;
          }
        } catch {
          /* that set is gone; start a new one below */
        }
      }

      const exp = await createExperience(sessionId, mem.groupProfileId);
      setExperienceId(exp.experience_instance_id);
      rememberSession(sessionId, { experienceId: exp.experience_instance_id });

      const recs = await getRecommendations(exp.experience_instance_id);
      showItems(recs.content_items);
      setExhausted(recs.content_items.length === 0);
    } catch (err: any) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  const handleRate = async (rating: Rating) => {
    const item = items[currentIdx];
    if (!item || !experienceId || !participantId) return;
    setError("");
    // Skip is just "next". Love it and Not for us build a profile, which needs an account.
    if (rating !== "skip" && meLoaded && !isSignedIn(me)) {
      setAskToSignIn(true);
      return;
    }
    try {
      const res = await submitFeedback(item.id, experienceId, participantId, rating);
      // Signed in, the account has its own place in the session; keep using it.
      if (res.participant_id && res.participant_id !== participantId) {
        setParticipantId(res.participant_id);
        rememberSession(sessionId, { participantId: res.participant_id });
      }
      setAskToSignIn(false);
      setRatings((prev) => ({ ...prev, [item.id]: rating }));
      if (currentIdx < items.length - 1) setCurrentIdx(currentIdx + 1);
    } catch (err: any) {
      if (err instanceof ApiError && err.status === 401) {
        setAskToSignIn(true);
      } else {
        setError(err.message);
      }
    }
  };

  const goSignIn = () => {
    router.push(`/login?next=${encodeURIComponent(`/session/${sessionId}/questions`)}`);
  };

  const handleGetMore = async () => {
    if (!experienceId) return;
    setLoadingMore(true);
    setError("");
    try {
      const recs = await getMoreRecommendations(experienceId);
      if (recs.content_items.length === 0) {
        setExhausted(true);
      } else {
        setItems((prev) => [...prev, ...recs.content_items]);
        setCurrentIdx(items.length); // first new question
      }
    } catch (err: any) {
      setError(err.message);
    } finally {
      setLoadingMore(false);
    }
  };

  if (loading) {
    return (
      <div className="max-w-md mx-auto text-center py-20 space-y-3">
        <p className="font-serif text-2xl">Picking your questions…</p>
        <p className="text-muted text-sm">This usually takes a moment.</p>
      </div>
    );
  }

  if (missingProfile) {
    return (
      <div className="max-w-md mx-auto text-center py-16 space-y-5">
        <p className="text-muted">Tell us about your group first, and we&rsquo;ll pick questions to match.</p>
        <PrimaryButton onClick={() => router.push(`/session/${sessionId}`)}>Describe your group</PrimaryButton>
      </div>
    );
  }

  if (error && items.length === 0) {
    return <LoadError message={error} onRetry={() => { started.current = false; void initExperience(); }} />;
  }

  // Nothing at all came back (no questions fit, or none have been loaded yet).
  if (items.length === 0) {
    return (
      <div className="max-w-md mx-auto text-center py-16 space-y-5">
        <h1 className="font-serif text-[28px] leading-[1.15] font-normal">No questions to show yet</h1>
        <p className="text-muted">
          We couldn&rsquo;t find questions that fit this group. Try describing the group a little differently.
        </p>
        <PrimaryButton onClick={() => router.push(`/session/${sessionId}`)}>Describe your group again</PrimaryButton>
      </div>
    );
  }

  const item = items[currentIdx];
  const rated = item ? ratings[item.id] : undefined;
  const isAtEnd = currentIdx >= items.length - 1;

  return (
    <div className="max-w-md mx-auto py-8 space-y-6">
      <div className="space-y-3">
        <div className="flex items-center justify-between">
          <Eyebrow>Step 3 of 3 · Your questions</Eyebrow>
          <span className="text-sm text-muted">
            {currentIdx + 1} / {items.length}
          </span>
        </div>
        <div className="w-full bg-soft rounded-full h-1.5" aria-hidden>
          <div
            className="bg-accent h-1.5 rounded-full transition-all"
            style={{ width: `${((currentIdx + 1) / items.length) * 100}%` }}
          />
        </div>
      </div>

      {error && (
        <p role="alert" className="text-red-500 text-sm">
          {error}
        </p>
      )}

      <div className="bg-surface rounded-md p-8 border border-soft min-h-[220px] flex items-center justify-center">
        <p className="font-serif text-[26px] leading-[1.3] text-center">{item.text}</p>
      </div>

      {askToSignIn && !rated && (
        <div
          role="status"
          className="rounded-md border border-soft bg-surface p-4 space-y-3 text-center"
        >
          <p className="font-medium">Sign in to leave feedback</p>
          <p className="text-sm text-muted">
            Your favorites and blocked questions are saved to your account. We&rsquo;ll bring you
            right back to this question.
          </p>
          <PrimaryButton onClick={goSignIn}>Sign in with email</PrimaryButton>
          <button
            onClick={() => setAskToSignIn(false)}
            className="text-sm text-muted hover:underline min-h-[44px]"
          >
            Not now
          </button>
        </div>
      )}

      {!rated ? (
        <div className="grid grid-cols-3 gap-2">
          <SecondaryButton
            className="px-2 text-base"
            onClick={() => handleRate("dislike")}
            title="Don't suggest this again"
          >
            Not for us
          </SecondaryButton>
          <SecondaryButton className="px-2 text-base" onClick={() => handleRate("skip")}>
            Skip
          </SecondaryButton>
          <PrimaryButton className="px-2 text-base" onClick={() => handleRate("like")} title="Save to favorites">
            Love it
          </PrimaryButton>
        </div>
      ) : (
        <div className="text-center space-y-3">
          <p className="text-muted">{RATING_NOTE[rated]}</p>
          {!isAtEnd && <PrimaryButton onClick={() => setCurrentIdx(currentIdx + 1)}>Next question</PrimaryButton>}
        </div>
      )}

      {isAtEnd && (rated || exhausted) && (
        <div className="space-y-3">
          {exhausted ? (
            <p className="text-center text-muted">
              That&rsquo;s every question we have for this group.{" "}
              <button
                onClick={() => router.push(`/session/${sessionId}`)}
                className="underline hover:text-ink"
              >
                Describe the group differently
              </button>{" "}
              for more.
            </p>
          ) : (
            <SecondaryButton onClick={handleGetMore} disabled={loadingMore}>
              {loadingMore ? "Finding more…" : "Get 10 more"}
            </SecondaryButton>
          )}
        </div>
      )}

      <div className="flex justify-between items-center pt-4 border-t border-soft">
        <button
          onClick={() => setCurrentIdx(Math.max(0, currentIdx - 1))}
          disabled={currentIdx === 0}
          className="text-sm text-muted hover:text-ink disabled:opacity-30"
        >
          ← Previous
        </button>
        <button
          onClick={() => setCurrentIdx(Math.min(items.length - 1, currentIdx + 1))}
          disabled={isAtEnd}
          className="text-sm text-muted hover:text-ink disabled:opacity-30"
        >
          Next →
        </button>
      </div>
    </div>
  );
}
