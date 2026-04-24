"use client";

import { useState, useEffect } from "react";
import { useParams, useRouter } from "next/navigation";
import { getFollowups, answerFollowup, commitGroupProfile } from "@/lib/api";

export default function FollowupsPage() {
  const params = useParams();
  const router = useRouter();
  const sessionId = params.id as string;

  const [prompts, setPrompts] = useState<any[]>([]);
  const [currentIdx, setCurrentIdx] = useState(0);
  const [selectedOption, setSelectedOption] = useState<string | null>(null);
  const [otherText, setOtherText] = useState("");
  const [loading, setLoading] = useState(true);
  const [answering, setAnswering] = useState(false);
  const [committing, setCommitting] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    getFollowups(sessionId)
      .then((data) => setPrompts(data.prompts))
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false));
  }, [sessionId]);

  const currentPrompt = prompts[currentIdx];

  const handleAnswer = async () => {
    if (!currentPrompt) return;
    setAnswering(true);
    setError("");
    try {
      const participantId = localStorage.getItem("participant_id")!;
      const isOther = selectedOption?.toLowerCase().includes("other");

      await answerFollowup(
        sessionId,
        currentPrompt.id,
        participantId,
        isOther ? null : selectedOption,
        isOther ? otherText : null
      );

      setSelectedOption(null);
      setOtherText("");

      if (currentIdx < prompts.length - 1) {
        setCurrentIdx(currentIdx + 1);
      } else {
        // All answered — commit profile
        await handleCommitProfile();
      }
    } catch (err: any) {
      setError(err.message);
    } finally {
      setAnswering(false);
    }
  };

  const handleCommitProfile = async () => {
    setCommitting(true);
    try {
      const provisionalId = localStorage.getItem("provisional_group_profile_id")!;
      const result = await commitGroupProfile(sessionId, provisionalId);
      localStorage.setItem("group_profile_id", result.group_profile_id);
      router.push(`/session/${sessionId}/questions`);
    } catch (err: any) {
      setError(err.message);
    } finally {
      setCommitting(false);
    }
  };

  if (loading) return <p className="text-center py-16">Loading follow-ups...</p>;
  if (!prompts.length) {
    return (
      <div className="text-center py-16 space-y-4">
        <p>No follow-up questions generated.</p>
        <button
          onClick={handleCommitProfile}
          disabled={committing}
          className="px-6 py-3 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50"
        >
          {committing ? "Building profile..." : "Skip → Get Questions"}
        </button>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold">Follow-up Questions</h1>
        <p className="text-sm text-gray-500">
          Question {currentIdx + 1} of {prompts.length}
        </p>
      </div>

      {/* Progress bar */}
      <div className="w-full bg-gray-200 dark:bg-gray-700 rounded-full h-2">
        <div
          className="bg-blue-600 h-2 rounded-full transition-all"
          style={{ width: `${((currentIdx + 1) / prompts.length) * 100}%` }}
        />
      </div>

      {currentPrompt && (
        <div className="bg-white dark:bg-gray-800 rounded-xl p-6 border border-gray-200 dark:border-gray-700 space-y-4">
          <h2 className="text-lg font-semibold">{currentPrompt.prompt_text}</h2>
          <div className="space-y-2">
            {currentPrompt.options.map((opt: string) => (
              <button
                key={opt}
                onClick={() => setSelectedOption(opt)}
                className={`w-full text-left px-4 py-3 rounded-lg border transition ${
                  selectedOption === opt
                    ? "border-blue-500 bg-blue-50 dark:bg-blue-900/30"
                    : "border-gray-200 dark:border-gray-600 hover:bg-gray-50 dark:hover:bg-gray-700"
                }`}
              >
                {opt}
              </button>
            ))}
          </div>

          {/* Other text input */}
          {selectedOption?.toLowerCase().includes("other") && (
            <input
              type="text"
              placeholder="Type your own..."
              value={otherText}
              onChange={(e) => setOtherText(e.target.value)}
              className="w-full px-4 py-3 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-800"
            />
          )}
        </div>
      )}

      {error && <p className="text-red-500 text-sm">{error}</p>}

      <button
        onClick={handleAnswer}
        disabled={answering || !selectedOption}
        className="w-full px-4 py-3 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 transition"
      >
        {answering
          ? "Saving..."
          : currentIdx < prompts.length - 1
          ? "Next →"
          : committing
          ? "Building your profile..."
          : "Finish & Get Questions →"}
      </button>
    </div>
  );
}
