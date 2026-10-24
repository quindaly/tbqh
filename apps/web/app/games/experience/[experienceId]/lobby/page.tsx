"use client";

import { useEffect, useState, useCallback } from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { getLobby, startCollection } from "@/lib/api";
import { usePolling } from "@/lib/usePolling";
import {
  ConnectionBanner,
  LobbyNotFound,
  LobbyUnreachable,
} from "../../../_components/LobbyStatus";

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
  const [starting, setStarting] = useState(false);
  const [error, setError] = useState("");
  const [copied, setCopied] = useState(false);
  const [copiedLink, setCopiedLink] = useState(false);
  const [participantId, setParticipantId] = useState<string | null>(null);

  useEffect(() => {
    setParticipantId(localStorage.getItem(`game_pid_${experienceId}`));
  }, [experienceId]);

  // Throws on failure so usePolling can stop on a 404 and back off on outages.
  const fetchLobby = useCallback(async () => {
    const data = await getLobby(experienceId);
    setLobby(data);

    // Only players in this game follow it into the next screen. Someone who
    // opened the page without joining stays here and sees the join prompt.
    const isPlayer =
      !!participantId && data.participants.some((p) => p.id === participantId);
    if (!isPlayer) return;

    if (data.game_state === "question_collection" || data.game_state === "ready_to_start") {
      router.push(`/games/experience/${experienceId}/questions`);
    } else if (data.game_state === "round_active" || data.game_state === "round_reveal") {
      router.push(`/games/experience/${experienceId}/play`);
    }
  }, [experienceId, router, participantId]);

  const { failures, fatal, gaveUp, retry } = usePolling(fetchLobby);

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

  function copyLink() {
    if (lobby?.share_url) {
      navigator.clipboard.writeText(lobby.share_url);
      setCopiedLink(true);
      setTimeout(() => setCopiedLink(false), 2000);
    }
  }

  if (fatal) {
    return <LobbyNotFound />;
  }

  if (!lobby) {
    return gaveUp ? (
      <LobbyUnreachable onRetry={retry} />
    ) : (
      <p className="text-center py-16 text-gray-500">Loading lobby…</p>
    );
  }

  const isPlayer =
    !!participantId && lobby.participants.some((p) => p.id === participantId);
  const isHost = isPlayer && participantId === lobby.host_id;
  const canJoin = !isPlayer && lobby.game_state === "lobby";

  return (
    <div className="max-w-md mx-auto space-y-6 py-8">
      <h1 className="text-2xl font-bold text-center">Game Lobby</h1>

      {failures > 0 && <ConnectionBanner gaveUp={gaveUp} onRetry={retry} />}

      {/* Join code */}
      <div className="rounded-xl border p-4 text-center space-y-2">
        <p className="text-sm text-gray-500 dark:text-gray-400">
          Share this code or link to invite players
        </p>
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

      {/* Visitor who hasn't joined */}
      {!isPlayer && (
        <div className="rounded-xl border p-4 text-center space-y-3">
          {canJoin ? (
            <>
              <p className="text-gray-500 dark:text-gray-400">
                You're not in this game yet.
              </p>
              <Link
                href={`/games/who-knows-who?code=${lobby.join_code}`}
                className="block w-full px-6 py-3 bg-purple-600 text-white rounded-lg hover:bg-purple-700 transition"
              >
                Join this game
              </Link>
            </>
          ) : (
            <p className="text-gray-500 dark:text-gray-400">
              This game has already started, so new players can't join.
            </p>
          )}
        </div>
      )}

      {/* Host controls */}
      {isPlayer &&
        (isHost ? (
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
        ))}
    </div>
  );
}
