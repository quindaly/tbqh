"use client";

import { useEffect, useState, useCallback } from "react";
import { useParams, useRouter } from "next/navigation";
import { getLobby, startCollection } from "@/lib/api";

interface Participant {
  id: string;
  display_name: string;
  role: string;
}

export default function LobbyPage() {
  const { experienceId } = useParams<{ experienceId: string }>();
  const router = useRouter();

  const [lobby, setLobby] = useState<{
    game_state: string;
    join_code: string;
    share_url: string;
    host_id: string | null;
    participants: Participant[];
  } | null>(null);
  const [loading, setLoading] = useState(true);
  const [starting, setStarting] = useState(false);
  const [error, setError] = useState("");
  const [copied, setCopied] = useState(false);
  const [participantId, setParticipantId] = useState<string | null>(null);

  useEffect(() => {
    setParticipantId(localStorage.getItem(`game_pid_${experienceId}`));
  }, [experienceId]);

  const fetchLobby = useCallback(async () => {
    try {
      const data = await getLobby(experienceId);
      setLobby(data);
      // Auto-navigate when state advances past lobby
      if (data.game_state === "question_collection" || data.game_state === "ready_to_start") {
        router.push(`/games/experience/${experienceId}/questions`);
      } else if (data.game_state === "round_active" || data.game_state === "round_reveal") {
        router.push(`/games/experience/${experienceId}/play`);
      }
    } catch {
    } finally {
      setLoading(false);
    }
  }, [experienceId, router]);

  useEffect(() => {
    fetchLobby();
    const interval = setInterval(fetchLobby, 3000);
    return () => clearInterval(interval);
  }, [fetchLobby]);

  async function handleStart() {
    if (!participantId) return;
    setStarting(true);
    setError("");
    try {
      await startCollection(experienceId, participantId);
      router.push(`/games/experience/${experienceId}/questions`);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setStarting(false);
    }
  }

  function copyCode() {
    if (lobby?.join_code) {
      navigator.clipboard.writeText(lobby.join_code);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  }

  if (loading || !lobby) {
    return <p className="text-center py-16 text-gray-500">Loading lobby…</p>;
  }

  const isHost = participantId === lobby.host_id;

  return (
    <div className="max-w-md mx-auto space-y-6 py-8">
      <h1 className="text-2xl font-bold text-center">Game Lobby</h1>

      {/* Join code */}
      <div className="rounded-xl border p-4 text-center space-y-2">
        <p className="text-sm text-gray-500 dark:text-gray-400">Share this code to invite players</p>
        <p className="text-3xl font-mono font-bold tracking-widest">
          {lobby.join_code}
        </p>
        <button
          onClick={copyCode}
          className="text-sm text-purple-600 hover:underline"
        >
          {copied ? "Copied!" : "Copy code"}
        </button>
      </div>

      {/* Participants */}
      <div className="space-y-2">
        <h2 className="font-semibold">
          Players ({lobby.participants.length})
        </h2>
        <ul className="space-y-1">
          {lobby.participants.map((p) => (
            <li
              key={p.id}
              className="flex items-center gap-2 rounded-lg border px-3 py-2"
            >
              <span>{p.display_name}</span>
              {p.role === "host" && (
                <span className="text-xs bg-blue-100 dark:bg-blue-900 text-blue-700 dark:text-blue-300 px-2 py-0.5 rounded-full">
                  Host
                </span>
              )}
            </li>
          ))}
        </ul>
      </div>

      {error && <p className="text-red-500 text-sm">{error}</p>}

      {/* Host controls */}
      {isHost ? (
        <button
          onClick={handleStart}
          disabled={starting || lobby.participants.length < 2}
          className="w-full px-6 py-3 bg-purple-600 text-white rounded-lg hover:bg-purple-700 transition disabled:opacity-50"
        >
          {starting
            ? "Starting…"
            : lobby.participants.length < 2
            ? "Need at least 2 players"
            : "Start Game"}
        </button>
      ) : (
        <p className="text-center text-gray-500 dark:text-gray-400">
          Waiting for the host to start the game…
        </p>
      )}
    </div>
  );
}
