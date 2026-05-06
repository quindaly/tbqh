"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import {
  getReviewChoices,
  editChoice,
  regenerateChoice,
  confirmChoices,
} from "@/lib/api";

interface Choice {
  id: string;
  text: string;
  is_correct: boolean;
  source_type: string;
}

interface Round {
  round_id: string;
  round_number: number;
  question_text: string;
  choices: Choice[];
}

export default function ReviewPage() {
  const { experienceId } = useParams<{ experienceId: string }>();
  const router = useRouter();

  const [rounds, setRounds] = useState<Round[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [editingChoiceId, setEditingChoiceId] = useState<string | null>(null);
  const [editText, setEditText] = useState("");
  const [confirming, setConfirming] = useState(false);
  const [regenCounts, setRegenCounts] = useState<Record<string, number>>({});

  const participantId =
    typeof window !== "undefined"
      ? localStorage.getItem(`game_pid_${experienceId}`) || ""
      : "";

  async function loadData() {
    try {
      const res = await getReviewChoices(experienceId, participantId);
      setRounds(res.rounds);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadData();
  }, [experienceId]);

  async function handleEdit(choiceId: string) {
    if (!editText.trim()) return;
    try {
      await editChoice(experienceId, choiceId, participantId, editText.trim());
      setEditingChoiceId(null);
      setEditText("");
      await loadData();
    } catch (e: any) {
      setError(e.message);
    }
  }

  async function handleRegenerate(choiceId: string) {
    try {
      const res = await regenerateChoice(experienceId, choiceId, participantId);
      setRegenCounts((prev) => ({
        ...prev,
        [choiceId]: (prev[choiceId] || 0) + 1,
      }));
      // Update the choice text in-place without reloading (preserves order)
      setRounds((prev) =>
        prev.map((round) => ({
          ...round,
          choices: round.choices.map((c) =>
            c.id === choiceId ? { ...c, text: res.new_text } : c
          ),
        }))
      );
    } catch (e: any) {
      if (e.message?.includes("Limit of 3")) {
        setRegenCounts((prev) => ({ ...prev, [choiceId]: 3 }));
      }
      setError(e.message);
    }
  }

  async function handleConfirm() {
    setConfirming(true);
    setError("");
    try {
      await confirmChoices(experienceId, participantId);
      router.push(`/games/experience/${experienceId}/hwdyk-lobby`);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setConfirming(false);
    }
  }

  if (loading) {
    return <div className="py-12 text-center text-gray-500">Loading choices…</div>;
  }

  return (
    <div className="max-w-2xl mx-auto py-12 space-y-8">
      <div className="text-center space-y-2">
        <h1 className="text-2xl font-bold">Review Answer Choices</h1>
        <p className="text-gray-500">
          Check the AI-generated wrong answers. Edit or regenerate any that don't look right.
        </p>
      </div>

      {error && <p className="text-red-500 text-sm text-center">{error}</p>}

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
            {round.choices.map((choice) => (
              <div
                key={choice.id}
                className={`flex items-center justify-between px-4 py-3 rounded-lg border ${
                  choice.is_correct
                    ? "border-green-300 bg-green-50 dark:bg-green-900/20 dark:border-green-800"
                    : "border-gray-200 dark:border-gray-700"
                }`}
              >
                <div className="flex-1">
                  {editingChoiceId === choice.id ? (
                    <div className="flex gap-2">
                      <input
                        type="text"
                        value={editText}
                        onChange={(e) => setEditText(e.target.value)}
                        className="flex-1 px-3 py-1 border rounded bg-white dark:bg-gray-800 text-sm"
                        autoFocus
                      />
                      <button
                        onClick={() => handleEdit(choice.id)}
                        className="text-sm text-purple-600 hover:underline"
                      >
                        Save
                      </button>
                      <button
                        onClick={() => setEditingChoiceId(null)}
                        className="text-sm text-gray-500 hover:underline"
                      >
                        Cancel
                      </button>
                    </div>
                  ) : (
                    <span className="text-sm">{choice.text}</span>
                  )}
                </div>

                {choice.is_correct ? (
                  <span className="text-xs text-green-600 font-medium ml-2">
                    ✓ Your answer
                  </span>
                ) : (
                  <div className="flex gap-2 ml-2">
                    <button
                      onClick={() => {
                        setEditingChoiceId(choice.id);
                        setEditText(choice.text);
                      }}
                      className="text-xs text-gray-500 hover:text-purple-600"
                      title="Edit"
                    >
                      ✏️
                    </button>
                    {(regenCounts[choice.id] || 0) >= 3 ? (
                      <span
                        className="text-xs text-gray-300 cursor-not-allowed"
                        title="Limit of 3 AI regenerations per answer"
                      >
                        🔄
                      </span>
                    ) : (
                      <button
                        onClick={() => handleRegenerate(choice.id)}
                        className="text-xs text-gray-500 hover:text-purple-600"
                        title={`Regenerate (${3 - (regenCounts[choice.id] || 0)} left)`}
                      >
                        🔄
                      </button>
                    )}
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      ))}

      <button
        onClick={handleConfirm}
        disabled={confirming}
        className="w-full px-6 py-3 bg-purple-600 text-white rounded-lg hover:bg-purple-700 transition disabled:opacity-50 text-lg font-medium"
      >
        {confirming ? "Locking choices…" : "Confirm All & Lock Game"}
      </button>
    </div>
  );
}
