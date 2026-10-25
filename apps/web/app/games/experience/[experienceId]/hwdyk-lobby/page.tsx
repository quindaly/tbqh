"use client";

import { useState, useCallback, useRef } from "react";
import { useParams, useRouter } from "next/navigation";
import {
  getHWDYKLobby,
  removePlayer,
  returnToHWDYKLobby,
  selectMainPerson,
  startHWDYKSetup,
  startLiveGame,
} from "@/lib/api";
import { formatClock, useCountdown } from "@/lib/countdown";
import { usePolling } from "@/lib/usePolling";
import {
  ConnectionBanner,
  LobbyNotFound,
  LobbyUnreachable,
} from "../../../_components/LobbyStatus";
import { ConnectionFacts } from "../../../_components/ConnectionFacts";

interface Participant {
  id: string;
  display_name: string;
  role: string;
  away?: boolean;
}

interface Absent {
  id: string;
  display_name: string;
}

export default function HWDYKLobbyPage() {
  const { experienceId } = useParams<{ experienceId: string }>();
  const router = useRouter();

  const [lobby, setLobby] = useState<any>(null);
  // When the lobby data (and so its countdown) arrived, on this device's clock.
  const [receivedAt, setReceivedAt] = useState(0);
  const lastVersion = useRef(-1);
  const [error, setError] = useState("");
  const [copied, setCopied] = useState(false);
  const [selectedMainPerson, setSelectedMainPerson] = useState<string>("");
  const [actionLoading, setActionLoading] = useState(false);

  const [participantId, setParticipantId] = useState(() => {
    if (typeof window === "undefined") return "";
    return localStorage.getItem(`game_pid_${experienceId}`) || "";
  });

  // Throws on failure so usePolling can stop on a 404 and back off on outages.
  const fetchLobby = useCallback(async () => {
    const data = await getHWDYKLobby(experienceId);
    // Two polls can overlap; never let an older reply overwrite a newer state.
    if (data.state_version < lastVersion.current) return;
    lastVersion.current = data.state_version;
    setLobby(data);
    setReceivedAt(Date.now());

    // Auto-recover participantId for replay: if we don't have one for this
    // experience, check if any stored PID matches a participant in this lobby
    let pid = participantId;
    if (!pid && data.participants?.length) {
      const knownPids = new Set<string>([
        ...data.participants.map((p: Participant) => p.id),
        ...(data.absent_participants || []).map((p: Absent) => p.id),
      ]);
      for (let i = 0; i < localStorage.length; i++) {
        const key = localStorage.key(i);
        if (key?.startsWith("game_pid_")) {
          const val = localStorage.getItem(key) || "";
          if (knownPids.has(val)) {
            localStorage.setItem(`game_pid_${experienceId}`, val);
            pid = val;
            setParticipantId(val);
            break;
          }
        }
      }
    }

    // In a replay lobby, someone who hasn't come back is not in this game, so
    // they are never sent into its screens.
    if ((data.absent_participants || []).some((p: Absent) => p.id === pid)) return;

    // Route based on state
    // The main person is sent to their screen only while there is time left on
    // the clock; in the last moments the server is still finalising, and sending
    // them back would just bounce them between the two pages.
    const timeLeft = data.phase ? data.phase.seconds_remaining > 0 : true;
    if (data.game_state === "main_person_answering") {
      if (pid === data.main_person_participant_id && timeLeft) {
        router.push(`/games/experience/${experienceId}/answer`);
      }
      // Others stay in lobby waiting
    } else if (data.game_state === "ai_generating_choices") {
      // Everyone waits here; the main person is sent to review once it is ready
    } else if (data.game_state === "main_person_reviewing_choices") {
      if (pid === data.main_person_participant_id && timeLeft) {
        router.push(`/games/experience/${experienceId}/review`);
      }
    } else if (data.game_state === "players_submitting_fake_answers") {
      if (pid !== data.main_person_participant_id) {
        router.push(`/games/experience/${experienceId}/fake-answers`);
      }
    } else if (data.game_state === "round_active" || data.game_state === "round_reveal") {
      router.push(`/games/experience/${experienceId}/hwdyk-play`);
    } else if (data.game_state === "completed") {
      router.push(`/games/experience/${experienceId}/hwdyk-leaderboard`);
    }
  }, [experienceId, router, participantId]);

  const { failures, fatal, gaveUp, retry } = usePolling(fetchLobby);
  const remaining = useCountdown(lobby?.phase, receivedAt);

  async function handleRemove(p: Participant) {
    setActionLoading(true);
    setError("");
    try {
      await removePlayer(experienceId, participantId, p.id);
      await fetchLobby();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setActionLoading(false);
    }
  }

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

  async function handleJoinThisLobby() {
    setActionLoading(true);
    setError("");
    try {
      await returnToHWDYKLobby(experienceId, participantId);
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

  const isHost = participantId === lobby.host_id;
  // Only people who have gone quiet can be removed, and only before setup starts.
  const canRemove = isHost && lobby.game_state === "lobby";
  const isMainPerson = participantId === lobby.main_person_participant_id;
  const isAbsent = !!lobby.absent_participants?.some((p: Absent) => p.id === participantId);
  const playerCount = lobby.participants?.length || 0;
  const mainPersonName =
    lobby.participants?.find(
      (p: Participant) => p.id === lobby.main_person_participant_id
    )?.display_name || null;

  return (
    <div className="max-w-md mx-auto space-y-6 py-8">
      <div className="space-y-1.5">
        <h1 className="font-serif text-[34px] leading-[1.1] tracking-[-0.01em] font-normal">The Hot Seat</h1>
        <p className="text-xs uppercase tracking-[0.14em] text-muted">
          {lobby.mode === "party" ? "Party mode" : "Default mode"}
        </p>
      </div>

      {failures > 0 && <ConnectionBanner gaveUp={gaveUp} onRetry={retry} />}

      {/* Join code & share link */}
      {lobby.game_state !== "round_active" && lobby.game_state !== "round_reveal" && lobby.game_state !== "completed" && (
        <div className="rounded-md border border-line bg-surface p-5 text-center space-y-1.5">
          <p className="text-sm text-muted">Share this code or link to invite players</p>
          <p className="text-[40px] leading-tight tracking-[0.14em] tabular-nums">
            {lobby.join_code}
          </p>
          <div className="flex justify-center gap-3">
            <button
              onClick={copyCode}
              className="text-sm text-accent hover:underline"
            >
              {copied ? "Copied!" : "Copy code"}
            </button>
            {lobby.share_url && (
              <button
                onClick={copyLink}
                className="text-sm text-accent hover:underline"
              >
                {copiedLink ? "Link copied!" : "Copy link"}
              </button>
            )}
          </div>
        </div>
      )}

      {/* Main person indicator */}
      {mainPersonName && (
        <div className="rounded-md border border-accent px-5 py-4">
          <p className="text-xs uppercase tracking-widest text-muted mb-1">In the hot seat</p>
          <p className="font-serif text-[28px] leading-tight">
            {mainPersonName}
          </p>
        </div>
      )}

      {/* Participants */}
      <div className="space-y-2">
        <h2 className="text-xs uppercase tracking-[0.14em] text-muted font-normal">
          {lobby.is_replay ? "Back in the lobby" : "Players"} ({playerCount})
        </h2>
        <ul className="border-t border-soft">
          {lobby.participants?.map((p: Participant) => (
            <li
              key={p.id}
              className="flex items-center justify-between border-b border-soft min-h-[52px] text-[17px]"
            >
              <span className={p.away ? "text-muted" : ""}>{p.display_name}</span>
              <span className="flex items-center gap-3">
              {p.away && <span className="text-xs text-muted">Away</span>}
              {p.away && canRemove && p.id !== participantId && (
                <button
                  onClick={() => handleRemove(p)}
                  disabled={actionLoading}
                  aria-label={`Remove ${p.display_name}`}
                  className="text-xs underline text-muted hover:text-text min-h-[44px] px-1"
                >
                  Remove
                </button>
              )}
              {p.role === "host" && (
                <span className="text-xs text-accent">Host</span>
              )}
              {p.id === lobby.main_person_participant_id && (
                <span className="text-xs text-accent">Hot seat</span>
              )}
              </span>
            </li>
          ))}
        </ul>
        {lobby.is_replay && lobby.absent_participants?.length > 0 && (
          <div className="pt-2">
            <h3 className="text-xs uppercase tracking-[0.14em] text-muted font-normal">Not back yet</h3>
            <ul className="space-y-1 pt-1">
              {lobby.absent_participants.map((p: Absent) => (
                <li
                  key={p.id}
                  className="flex items-center gap-2 border-b border-dashed border-soft min-h-[52px] text-muted"
                >
                  <span>{p.display_name}</span>
                  {p.id === participantId && (
                    <span className="text-xs text-accent">(you)</span>
                  )}
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>

      {error && <p role="alert" className="text-red-500 text-sm">{error}</p>}

      {/* A session member who hasn't come back to this replay lobby yet */}
      {isAbsent && (
        <div className="space-y-2">
          {lobby.game_state === "lobby" ? (
            <button
              onClick={handleJoinThisLobby}
              disabled={actionLoading}
              className="w-full min-h-[56px] px-6 bg-btn text-btn-text rounded-md font-medium hover:opacity-90 transition disabled:opacity-50"
            >
              {actionLoading ? "Joining…" : "Join this lobby"}
            </button>
          ) : (
            <p className="text-center text-muted" role="status">
              This game has already started without you. You can join the next one.
            </p>
          )}
        </div>
      )}

      {/* Why we're back in the lobby (time ran out, nothing playable) */}
      {lobby.game_state === "lobby" && lobby.notice && (
        <div
          role="status"
          className="rounded-md border border-soft bg-surface px-3 py-2 text-sm text-ink"
        >
          {lobby.notice.message}
        </div>
      )}

      {/* STATE: lobby — host selects main person & starts */}
      {lobby.game_state === "lobby" && isHost && (
        <div className="space-y-4">
          <div className="space-y-2">
            <label htmlFor="main-person" className="text-sm font-medium">
              {lobby.main_person_participant_id
                ? "Who's in the hot seat:"
                : "Select who's in the hot seat:"}
            </label>
            <select
              id="main-person"
              value={selectedMainPerson || lobby.main_person_participant_id || ""}
              onChange={(e) => setSelectedMainPerson(e.target.value)}
              className="w-full px-4 py-3 border border-line rounded-md bg-surface text-ink"
            >
              <option value="">Choose a player…</option>
              {lobby.participants?.map((p: Participant) => (
                <option key={p.id} value={p.id}>
                  {p.display_name}
                  {p.id === lobby.previous_main_person_id ? " (last game's hot seat)" : ""}
                </option>
              ))}
            </select>
            {selectedMainPerson &&
              selectedMainPerson !== lobby.main_person_participant_id && (
                <button
                  onClick={handleSelectMainPerson}
                  disabled={actionLoading}
                  className="w-full min-h-[44px] px-4 bg-btn text-btn-text rounded-md font-medium hover:opacity-90 transition disabled:opacity-50"
                >
                  {actionLoading ? "Selecting…" : "Confirm hot seat"}
                </button>
              )}
          </div>

          {lobby.main_person_participant_id && (
            <>
              <button
                onClick={handleStartSetup}
                disabled={actionLoading || playerCount < 2}
                className="w-full min-h-[56px] px-6 bg-btn text-btn-text rounded-md font-medium hover:opacity-90 transition disabled:opacity-50"
              >
                {actionLoading ? "Starting…" : "Start setup"}
              </button>
              {playerCount < 2 && (
                <p className="text-center text-sm text-muted">
                  Waiting for at least one more player.
                </p>
              )}
            </>
          )}
        </div>
      )}

      {/* STATE: main_person_answering: everyone sees who, which question and how long */}
      {lobby.game_state === "main_person_answering" && (
        <div className="text-center py-4 space-y-2">
          <div aria-hidden="true" className="mx-auto h-2 w-2 rounded-full bg-accent animate-pulse" />
          <p className="text-muted">
            <span role="status">
              {isMainPerson ? "You're" : `${mainPersonName} is`} answering{" "}
              {lobby.progress
                ? `question ${Math.min(lobby.progress.current_index + 1, lobby.progress.total)} of ${lobby.progress.total}`
                : "questions"}
            </span>
            {remaining !== null && <span>, {formatClock(remaining)} remaining</span>}
          </p>
          {lobby.progress && (
            <p className="text-sm text-muted">
              {lobby.progress.answered} answered
            </p>
          )}
        </div>
      )}

      {/* STATE: ai_generating_choices — everyone waits (no clock: the editing
          time doesn't start until the choices are ready) */}
      {lobby.game_state === "ai_generating_choices" && (
        <div className="text-center py-4 space-y-2">
          <div aria-hidden="true" className="mx-auto h-2 w-2 rounded-full bg-accent animate-pulse" />
          <p className="text-muted" role="status">
            Generating answer choices…
          </p>
        </div>
      )}

      {/* STATE: main_person_reviewing_choices */}
      {lobby.game_state === "main_person_reviewing_choices" && (
        <div className="text-center py-4 space-y-2">
          <div aria-hidden="true" className="mx-auto h-2 w-2 rounded-full bg-accent animate-pulse" />
          <p className="text-muted">
            <span role="status">
              {isMainPerson ? "You're" : `${mainPersonName} is`} reviewing answer choices
            </span>
            {remaining !== null && <span>, {formatClock(remaining)} remaining</span>}
          </p>
        </div>
      )}

      {/* STATE: players_submitting_fake_answers — main person waits */}
      {lobby.game_state === "players_submitting_fake_answers" && isMainPerson && (
        <div className="text-center py-4 space-y-2">
          <div aria-hidden="true" className="mx-auto h-2 w-2 rounded-full bg-accent animate-pulse" />
          <p className="text-muted">
            Players are writing fake answers…
          </p>
        </div>
      )}

      {/* STATE: ready_to_start — host can launch */}
      {lobby.game_state === "ready_to_start" && (
        <div className="space-y-3">
          <p className="text-center text-ink font-medium" role="status">
            Everyone is ready.
          </p>
          {isHost ? (
            <button
              onClick={handleStartLive}
              disabled={actionLoading}
              className="w-full min-h-[56px] px-6 bg-btn text-btn-text rounded-md font-medium hover:opacity-90 transition disabled:opacity-50"
            >
              {actionLoading ? "Starting…" : "Start the game"}
            </button>
          ) : (
            <p className="text-center text-muted">
              Waiting for the host to start the game…
            </p>
          )}
        </div>
      )}

      {/* Non-host waiting message for lobby state */}
      {lobby.game_state === "lobby" && !isHost && !isAbsent && (
        <p className="text-center text-muted">
          Waiting for the host to configure and start…
        </p>
      )}

      {/* Something to read while waiting. Last, so it never pushes the player
          list, host controls, join code or timers around. */}
      <ConnectionFacts />
    </div>
  );
}
