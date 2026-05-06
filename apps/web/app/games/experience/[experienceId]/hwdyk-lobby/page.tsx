"use client";

import { useEffect, useState, useCallback } from "react";
import { useParams, useRouter } from "next/navigation";
import {
  getHWDYKLobby,
  selectMainPerson,
  startHWDYKSetup,
  startLiveGame,
} from "@/lib/api";

interface Participant {
  id: string;
  display_name: string;
  role: string;
}

export default function HWDYKLobbyPage() {
  const { experienceId } = useParams<{ experienceId: string }>();
  const router = useRouter();

  const [lobby, setLobby] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [copied, setCopied] = useState(false);
  const [selectedMainPerson, setSelectedMainPerson] = useState<string>("");
  const [actionLoading, setActionLoading] = useState(false);

  const participantId =
    typeof window !== "undefined"
      ? localStorage.getItem(`game_pid_${experienceId}`) || ""
      : "";

  const fetchLobby = useCallback(async () => {
    try {
      const data = await getHWDYKLobby(experienceId);
      setLobby(data);

      // Route based on state
      if (data.game_state === "main_person_answering") {
        if (participantId === data.main_person_participant_id) {
          router.push(`/games/experience/${experienceId}/answer`);
        }
        // Others stay in lobby waiting
      } else if (data.game_state === "ai_generating_choices") {
        // Main person waits, then goes to review
      } else if (data.game_state === "main_person_reviewing_choices") {
        if (participantId === data.main_person_participant_id) {
          router.push(`/games/experience/${experienceId}/review`);
        }
      } else if (data.game_state === "players_submitting_fake_answers") {
        if (participantId !== data.main_person_participant_id) {
          router.push(`/games/experience/${experienceId}/fake-answers`);
        }
      } else if (data.game_state === "round_active" || data.game_state === "round_reveal") {
        router.push(`/games/experience/${experienceId}/hwdyk-play`);
      } else if (data.game_state === "completed") {
        router.push(`/games/experience/${experienceId}/hwdyk-leaderboard`);
      }
    } catch {
    } finally {
      setLoading(false);
    }
  }, [experienceId, router, participantId]);

  useEffect(() => {
    fetchLobby();
    const interval = setInterval(fetchLobby, 3000);
    return () => clearInterval(interval);
  }, [fetchLobby]);

  async function handleSelectMainPerson() {
    if (!selectedMainPerson) return;
    setActionLoading(true);
    setError("");
    try {
      await selectMainPerson(experienceId, participantId, selectedMainPerson);
      await fetchLobby();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setActionLoading(false);
    }
  }

  async function handleStartSetup() {
    setActionLoading(true);
    setError("");
    try {
      await startHWDYKSetup(experienceId, participantId);
      // Will redirect on next poll
    } catch (e: any) {
      setError(e.message);
    } finally {
      setActionLoading(false);
    }
  }

  async function handleStartLive() {
    setActionLoading(true);
    setError("");
    try {
      await startLiveGame(experienceId, participantId);
      router.push(`/games/experience/${experienceId}/hwdyk-play`);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setActionLoading(false);
    }
  }

  const [copiedLink, setCopiedLink] = useState(false);

  function copyCode() {
    if (lobby?.join_code) {
      navigator.clipboard.writeText(lobby.join_code);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  }

  function copyLink() {
    if (lobby?.share_url) {
      navigator.clipboard.writeText(lobby.share_url);
      setCopiedLink(true);
      setTimeout(() => setCopiedLink(false), 2000);
    }
  }

  if (loading || !lobby) {
    return <p className="text-center py-16 text-gray-500">Loading lobby…</p>;
  }

  const isHost = participantId === lobby.host_id;
  const isMainPerson = participantId === lobby.main_person_participant_id;
  const mainPersonName =
    lobby.participants?.find(
      (p: Participant) => p.id === lobby.main_person_participant_id
    )?.display_name || null;

  return (
    <div className="max-w-md mx-auto space-y-6 py-8">
      <div className="text-center space-y-1">
        <h1 className="text-2xl font-bold">How Well Do You Know…?</h1>
        <div className="inline-flex items-center gap-2">
          <span className="text-xs px-2 py-0.5 rounded-full bg-purple-100 dark:bg-purple-900/30 text-purple-700 dark:text-purple-300">
            {lobby.mode === "party" ? "Party Mode" : "Default Mode"}
          </span>
        </div>
      </div>

      {/* Join code & share link */}
      {lobby.game_state !== "round_active" && lobby.game_state !== "round_reveal" && lobby.game_state !== "completed" && (
        <div className="rounded-xl border p-4 text-center space-y-2">
          <p className="text-sm text-gray-500">Share this code or link to invite players</p>
          <p className="text-3xl font-mono font-bold tracking-widest">
            {lobby.join_code}
          </p>
          <div className="flex justify-center gap-3">
            <button
              onClick={copyCode}
              className="text-sm text-purple-600 hover:underline"
            >
              {copied ? "Copied!" : "Copy code"}
            </button>
            {lobby.share_url && (
              <button
                onClick={copyLink}
                className="text-sm text-purple-600 hover:underline"
              >
                {copiedLink ? "Link copied!" : "Copy link"}
              </button>
            )}
          </div>
        </div>
      )}

      {/* Main person indicator */}
      {mainPersonName && (
        <div className="rounded-xl border-2 border-purple-300 dark:border-purple-700 bg-purple-50 dark:bg-purple-900/20 p-4 text-center">
          <p className="text-sm text-gray-500 mb-1">Main Person</p>
          <p className="text-lg font-bold text-purple-700 dark:text-purple-300">
            {mainPersonName}
          </p>
        </div>
      )}

      {/* Participants */}
      <div className="space-y-2">
        <h2 className="font-semibold">
          Players ({lobby.participants?.length || 0})
        </h2>
        <ul className="space-y-1">
          {lobby.participants?.map((p: Participant) => (
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
              {p.id === lobby.main_person_participant_id && (
                <span className="text-xs bg-purple-100 dark:bg-purple-900 text-purple-700 dark:text-purple-300 px-2 py-0.5 rounded-full">
                  ⭐ Main
                </span>
              )}
            </li>
          ))}
        </ul>
      </div>

      {error && <p className="text-red-500 text-sm">{error}</p>}

      {/* STATE: lobby — host selects main person & starts */}
      {lobby.game_state === "lobby" && isHost && (
        <div className="space-y-4">
          {!lobby.main_person_participant_id && (
            <div className="space-y-2">
              <label className="text-sm font-medium">Select who's in the hot seat:</label>
              <select
                value={selectedMainPerson}
                onChange={(e) => setSelectedMainPerson(e.target.value)}
                className="w-full px-4 py-3 border rounded-lg bg-white dark:bg-gray-800"
              >
                <option value="">Choose a player…</option>
                {lobby.participants?.map((p: Participant) => (
                  <option key={p.id} value={p.id}>
                    {p.display_name}
                  </option>
                ))}
              </select>
              <button
                onClick={handleSelectMainPerson}
                disabled={!selectedMainPerson || actionLoading}
                className="w-full px-4 py-2 bg-purple-600 text-white rounded-lg hover:bg-purple-700 transition disabled:opacity-50"
              >
                {actionLoading ? "Selecting…" : "Confirm Main Person"}
              </button>
            </div>
          )}

          {lobby.main_person_participant_id && (
            <button
              onClick={handleStartSetup}
              disabled={actionLoading || (lobby.participants?.length || 0) < 2}
              className="w-full px-6 py-3 bg-purple-600 text-white rounded-lg hover:bg-purple-700 transition disabled:opacity-50"
            >
              {actionLoading
                ? "Starting…"
                : (lobby.participants?.length || 0) < 2
                ? "Need at least 2 players"
                : "Start Setup"}
            </button>
          )}
        </div>
      )}

      {/* STATE: main_person_answering — others wait */}
      {lobby.game_state === "main_person_answering" && !isMainPerson && (
        <div className="text-center py-4 space-y-2">
          <div className="animate-pulse text-purple-500 text-xl">✍️</div>
          <p className="text-gray-500">
            {mainPersonName} is answering questions…
          </p>
        </div>
      )}

      {/* STATE: ai_generating_choices — everyone waits */}
      {lobby.game_state === "ai_generating_choices" && (
        <div className="text-center py-4 space-y-2">
          <div className="animate-pulse text-purple-500">●●●</div>
          <p className="text-gray-500">
            AI is generating answer choices…
          </p>
        </div>
      )}

      {/* STATE: main_person_reviewing_choices — others wait */}
      {lobby.game_state === "main_person_reviewing_choices" && !isMainPerson && (
        <div className="text-center py-4 space-y-2">
          <div className="animate-pulse text-purple-500 text-xl">🔍</div>
          <p className="text-gray-500">
            {mainPersonName} is reviewing answer choices…
          </p>
        </div>
      )}

      {/* STATE: players_submitting_fake_answers — main person waits */}
      {lobby.game_state === "players_submitting_fake_answers" && isMainPerson && (
        <div className="text-center py-4 space-y-2">
          <div className="animate-pulse text-purple-500 text-xl">🎭</div>
          <p className="text-gray-500">
            Players are writing fake answers…
          </p>
        </div>
      )}

      {/* STATE: ready_to_start — host can launch */}
      {lobby.game_state === "ready_to_start" && (
        <div className="space-y-3">
          <p className="text-center text-green-600 font-medium">
            Everything's ready! 🎉
          </p>
          {isHost ? (
            <button
              onClick={handleStartLive}
              disabled={actionLoading}
              className="w-full px-6 py-3 bg-green-600 text-white rounded-lg hover:bg-green-700 transition disabled:opacity-50"
            >
              {actionLoading ? "Starting…" : "Start Live Game!"}
            </button>
          ) : (
            <p className="text-center text-gray-500">
              Waiting for host to start…
            </p>
          )}
        </div>
      )}

      {/* Non-host waiting message for lobby state */}
      {lobby.game_state === "lobby" && !isHost && (
        <p className="text-center text-gray-500">
          Waiting for the host to configure and start…
        </p>
      )}
    </div>
  );
}
