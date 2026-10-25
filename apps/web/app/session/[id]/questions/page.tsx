"use client";

import { useState, useEffect } from "react";
import { useParams } from "next/navigation";
import {
  createExperience,
  getRecommendations,
  getMoreRecommendations,
  submitFeedback,
} from "@/lib/api";
import { LoadError } from "../../../_components/LoadError";

interface ContentItem {
  id: string;
  content_type: string;
  text: string;
  metadata: Record<string, unknown>;
}

export default function QuestionsPage() {
  const params = useParams();
  const sessionId = params.id as string;

  const [experienceId, setExperienceId] = useState<string | null>(null);
  const [items, setItems] = useState<ContentItem[]>([]);
  const [currentIdx, setCurrentIdx] = useState(0);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState("");
  const [feedbackGiven, setFeedbackGiven] = useState<Record<string, string>>({});

  useEffect(() => {
    initExperience();
  }, []);

  const initExperience = async () => {
    setLoading(true);
    setError("");
    try {
      const groupProfileId = localStorage.getItem("group_profile_id")!;
      const exp = await createExperience(sessionId, groupProfileId);
      setExperienceId(exp.experience_instance_id);

      const recs = await getRecommendations(exp.experience_instance_id);
      setItems(recs.content_items);
      setCurrentIdx(0);
    } catch (err: any) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const handleFeedback = async (feedback: "like" | "dislike" | "skip") => {
    const item = items[currentIdx];
    if (!item || !experienceId) return;

    const participantId = localStorage.getItem("participant_id")!;
    try {
      await submitFeedback(item.id, experienceId, participantId, feedback);
      setFeedbackGiven((prev) => ({ ...prev, [item.id]: feedback }));

      // Auto-advance
      if (currentIdx < items.length - 1) {
        setCurrentIdx(currentIdx + 1);
      }
    } catch (err: any) {
      setError(err.message);
    }
  };

  const handleGetMore = async () => {
    if (!experienceId) return;
    setLoadingMore(true);
    setError("");
    try {
      const recs = await getMoreRecommendations(experienceId);
      setItems((prev) => [...prev, ...recs.content_items]);
      setCurrentIdx(items.length); // Jump to first new item
    } catch (err: any) {
      setError(err.message);
    } finally {
      setLoadingMore(false);
    }
  };

  if (loading) {
    return (
      <div className="text-center py-16 space-y-4">
        <div className="animate-pulse text-4xl">🤔</div>
        <p className="text-lg">Generating your discussion questions...</p>
      </div>
    );
  }

  if (error && items.length === 0) {
    return <LoadError message={error} onRetry={initExperience} />;
  }

  const currentItem = items[currentIdx];
  const isAtEnd = currentIdx >= items.length - 1;

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Discussion Questions</h1>
        <span className="text-sm text-muted">
          {currentIdx + 1} / {items.length}
        </span>
      </div>

      {/* Progress bar */}
      <div className="w-full bg-soft rounded-full h-2">
        <div
          className="bg-accent h-2 rounded-full transition-all"
          style={{ width: `${((currentIdx + 1) / items.length) * 100}%` }}
        />
      </div>

      {error && (
        <div className="bg-red-50 dark:bg-red-900/20 text-red-600 p-3 rounded-md text-sm">
          {error}
        </div>
      )}

      {/* Question card */}
      {currentItem && (
        <div className="bg-surface rounded-md p-8 border border-soft min-h-[200px] flex items-center justify-center">
          <p className="text-xl text-center leading-relaxed">
            {currentItem.text}
          </p>
        </div>
      )}

      {/* Feedback buttons */}
      {currentItem && !feedbackGiven[currentItem.id] && (
        <div className="flex gap-3 justify-center">
          <button
            onClick={() => handleFeedback("dislike")}
            className="px-6 py-3 bg-red-100 dark:bg-red-900/30 text-red-600 dark:text-red-400 rounded-md hover:bg-red-200 dark:hover:bg-red-900/50 transition text-lg"
            title="Dislike — never show this again"
          >
            👎 Pass
          </button>
          <button
            onClick={() => handleFeedback("skip")}
            className="px-6 py-3 bg-soft text-muted rounded-md hover:bg-soft transition text-lg"
            title="Skip"
          >
            ⏭️ Skip
          </button>
          <button
            onClick={() => handleFeedback("like")}
            className="px-6 py-3 bg-green-100 dark:bg-green-900/30 text-green-600 dark:text-green-400 rounded-md hover:bg-green-200 dark:hover:bg-green-900/50 transition text-lg"
            title="Like — save to favorites"
          >
            ❤️ Love it
          </button>
        </div>
      )}

      {/* Feedback confirmation */}
      {currentItem && feedbackGiven[currentItem.id] && (
        <div className="text-center space-y-3">
          <p className="text-muted">
            {feedbackGiven[currentItem.id] === "like"
              ? "❤️ Saved to favorites!"
              : feedbackGiven[currentItem.id] === "dislike"
              ? "👎 Blocked — you won't see this again."
              : "⏭️ Skipped"}
          </p>
          {!isAtEnd && (
            <button
              onClick={() => setCurrentIdx(currentIdx + 1)}
              className="px-6 py-3 bg-btn text-btn-text rounded-md hover:opacity-90 transition font-medium"
            >
              Next Question →
            </button>
          )}
        </div>
      )}

      {/* Navigation */}
      <div className="flex justify-between items-center pt-4 border-t border-soft">
        <button
          onClick={() => setCurrentIdx(Math.max(0, currentIdx - 1))}
          disabled={currentIdx === 0}
          className="text-sm text-muted hover:text-ink disabled:opacity-30"
        >
          ← Previous
        </button>

        {isAtEnd && (
          <button
            onClick={handleGetMore}
            disabled={loadingMore}
            className="px-6 py-3 bg-btn text-btn-text rounded-md hover:opacity-90 disabled:opacity-50 transition font-medium"
          >
            {loadingMore ? "Loading..." : "🔄 Get 10 More"}
          </button>
        )}

        <button
          onClick={() =>
            setCurrentIdx(Math.min(items.length - 1, currentIdx + 1))
          }
          disabled={isAtEnd}
          className="text-sm text-muted hover:text-ink disabled:opacity-30"
        >
          Next →
        </button>
      </div>
    </div>
  );
}
