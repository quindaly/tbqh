"use client";

import { useEffect, useState, useCallback } from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { getLobby, startCollection, replayGame } from "@/lib/api";
import { usePolling } from "@/lib/usePolling";
import { Eyebrow, Heading, PrimaryButton } from "../../../../_components/ui";
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

interface Lobby {
  game_state: string;
  join_code: string;
  share_url: string;
  host_id: string | null;
  participants: Participant[];
  absent_participants?: { id: string; display_name: string }[];
  is_replay?: boolean;
  min_players?: number;
}

export default function LobbyPage() {
  const { experienceId } = useParams<{ experienceId: string }>();
  const router = useRouter();

  const [lobby, setLobby] = useState<Lobby | null>(null);
  const [starting, setStarting] = useState(false);
  const [joining, setJoining] = useState(false);
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

  // A player from the last game who has not come back to this lobby yet.
  async function handleJoinThisLobby() {
    if (!participantId) return;
    setJoining(true);
    setError("");
    try {
      await replayGame(experienceId, participantId);
      await fetchLobby();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setJoining(false);
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
      <p className="text-center py-16 text-muted">Loading lobby…</p>
    );
  }

  const minPlayers = lobby.min_players ?? 3;
  const isPlayer =
    !!participantId && lobby.participants.some((p) => p.id === participantId);
  const isHost = isPlayer && participantId === lobby.host_id;
  const isAbsent =
    !!participantId && !!lobby.absent_participants?.some((p) => p.id === participantId);
  const canJoin = !isPlayer && !isAbsent && lobby.game_state === "lobby";
  const needed = Math.max(0, minPlayers - lobby.participants.length);

  return (
    <div className="max-w-md mx-auto space-y-6 py-8">
      <div className="space-y-1.5">
        <Heading>Who Knows Who</Heading>
        <p className="text-sm text-muted">Everyone answers questions, then guesses who said what.</p>
      </div>

      {failures > 0 && <ConnectionBanner gaveUp={gaveUp} onRetry={retry} />}

      {/* Join code */}
      <div className="rounded-md border border-line bg-surface p-5 text-center space-y-1.5">
        <p className="text-sm text-muted">Share this code or link to invite players</p>
        <p className="text-[40px] leading-tight tracking-[0.14em] tabular-nums">
          {lobby.join_code}
        </p>
        <div className="flex justify-center gap-3">
          <button onClick={copyCode} className="text-sm text-accent hover:underline">
            {copied ? "Copied!" : "Copy code"}
          </button>
          {lobby.share_url && (
            <button onClick={copyLink} className="text-sm text-accent hover:underline">
              {copiedLink ? "Link copied!" : "Copy link"}
            </button>
          )}
        </div>
      </div>

      {/* Participants */}
      <div className="space-y-2">
        <h2 className="text-xs uppercase tracking-[0.14em] text-muted font-normal">
          {lobby.is_replay ? "Back in the lobby" : "Players"} ({lobby.participants.length})
        </h2>
        <ul className="border-t border-soft">
          {lobby.participants.map((p) => (
            <li
              key={p.id}
              className="flex items-center justify-between border-b border-soft min-h-[52px] text-[17px]"
            >
              <span>
                {p.display_name}
                {p.id === participantId && <span className="text-muted text-sm"> (you)</span>}
              </span>
              {p.id === lobby.host_id && <span className="text-xs text-accent">Host</span>}
            </li>
          ))}
        </ul>
        {lobby.is_replay && !!lobby.absent_participants?.length && (
          <div className="pt-2">
            <h3 className="text-xs uppercase tracking-[0.14em] text-muted font-normal">
              Not back yet
            </h3>
            <ul className="pt-1">
              {lobby.absent_participants.map((p) => (
                <li
                  key={p.id}
                  className="flex items-center gap-2 border-b border-dashed border-soft min-h-[52px] text-muted"
                >
                  <span>{p.display_name}</span>
                  {p.id === participantId && <span className="text-xs text-accent">(you)</span>}
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>

      {error && (
        <p role="alert" className="text-red-500 text-sm">
          {error}
        </p>
      )}

      {/* Someone from the last game who has not come back yet */}
      {isAbsent && (
        <div className="space-y-2">
          {lobby.game_state === "lobby" ? (
            <PrimaryButton onClick={handleJoinThisLobby} disabled={joining}>
              {joining ? "Joining…" : "Join this lobby"}
            </PrimaryButton>
          ) : (
            <p className="text-center text-muted" role="status">
              This game has already started without you.
            </p>
          )}
        </div>
      )}

      {/* Visitor who hasn't joined */}
      {!isPlayer && !isAbsent && (
        <div className="rounded-md border border-soft bg-surface p-4 text-center space-y-3">
          {canJoin ? (
            <>
              <p className="text-muted">You&apos;re not in this game yet.</p>
              <Link
                href={`/games/who-knows-who?code=${lobby.join_code}`}
                className="flex items-center justify-center w-full px-6 bg-btn text-btn-text rounded-md hover:opacity-90 transition min-h-[56px] text-[17px] font-medium"
              >
                Join this game
              </Link>
            </>
          ) : (
            <p className="text-muted">
              This game has already started, so new players can&apos;t join.
            </p>
          )}
        </div>
      )}

      {/* Host controls */}
      {isPlayer &&
        (isHost ? (
          <div className="space-y-2">
            <PrimaryButton onClick={handleStart} disabled={starting || needed > 0}>
              {starting
                ? "Starting…"
                : needed > 0
                ? `Waiting for ${needed} more ${needed === 1 ? "player" : "players"}`
                : "Start game"}
            </PrimaryButton>
            {needed > 0 && (
              <p className="text-center text-sm text-muted">
                Who Knows Who needs at least {minPlayers} players.
              </p>
            )}
          </div>
        ) : (
          <p className="text-center text-muted">Waiting for the host to start the game…</p>
        ))}
    </div>
  );
}
