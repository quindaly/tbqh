"use client";

import { useEffect, useState, useCallback } from "react";
import { useParams, useRouter } from "next/navigation";
import { getLeaderboard, replayGame } from "@/lib/api";
import { usePolling } from "@/lib/usePolling";
import { Eyebrow, Heading, PrimaryButton, SecondaryButton } from "../../../../_components/ui";
import {
  ConnectionBanner,
  LobbyNotFound,
  LobbyUnreachable,
} from "../../../_components/LobbyStatus";

interface LeaderboardEntry {
  participant_id: string;
  display_name: string;
  score: number;
  rank: number;
}

interface NextGame {
  id: string | null;
  returned: string[];
  total: number;
}

function winnersLine(winners: LeaderboardEntry[]) {
  const names = winners.map((w) => w.display_name);
  if (names.length === 1) return `${names[0]} knew everyone best.`;
  if (names.length === 2) return `${names[0]} and ${names[1]} tied.`;
  return `${names.slice(0, -1).join(", ")} and ${names[names.length - 1]} tied.`;
}

export default function LeaderboardPage() {
  const { experienceId } = useParams<{ experienceId: string }>();
  const router = useRouter();

  const [entries, setEntries] = useState<LeaderboardEntry[] | null>(null);
  const [next, setNext] = useState<NextGame>({ id: null, returned: [], total: 0 });
  const [replaying, setReplaying] = useState(false);
  const [error, setError] = useState("");
  const [participantId, setParticipantId] = useState<string | null>(null);

  useEffect(() => {
    setParticipantId(localStorage.getItem(`game_pid_${experienceId}`));
  }, [experienceId]);

  // Keeps the scores and "who is back for the next game" fresh. Throws on
  // failure so usePolling can back off and stop on a missing game.
  const fetchBoard = useCallback(async () => {
    const data = await getLeaderboard(experienceId);
    setEntries(data.leaderboard);
    setNext({
      id: data.next_experience_id,
      returned: data.returned_ids ?? [],
      total: data.participant_count ?? data.leaderboard.length,
    });
  }, [experienceId]);

  const { failures, fatal, gaveUp, retry } = usePolling(fetchBoard, { baseMs: 4000 });

  async function handleReplay() {
    if (!participantId) return;
    setReplaying(true);
    setError("");
    try {
      const res = await replayGame(experienceId, participantId);
      localStorage.setItem(`game_pid_${res.experience_instance_id}`, participantId);
      router.push(`/games/experience/${res.experience_instance_id}/lobby`);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setReplaying(false);
    }
  }

  if (fatal) {
    return <LobbyNotFound />;
  }

  if (!entries) {
    return gaveUp ? (
      <LobbyUnreachable onRetry={retry} />
    ) : (
      <p className="text-center py-16 text-muted">Loading results…</p>
    );
  }

  const winners = entries.filter((e) => e.rank === 1);
  const isPlayer = !!participantId && entries.some((e) => e.participant_id === participantId);
  const nextOpen = next.id !== null && next.returned.length > 0;

  return (
    <div className="max-w-md mx-auto flex flex-col gap-8 py-8">
      {failures > 0 && <ConnectionBanner gaveUp={gaveUp} onRetry={retry} />}

      <div className="flex flex-col gap-2">
        <Eyebrow>Final scores</Eyebrow>
        {winners.length > 0 && <Heading size={44}>{winnersLine(winners)}</Heading>}
      </div>

      {/* Full rankings */}
      <ol className="border-t border-line">
        {entries.map((entry) => {
          const first = entry.rank === 1;
          const mine = entry.participant_id === participantId;
          return (
            <li
              key={entry.participant_id}
              className="flex items-baseline gap-4 py-4 border-b border-soft"
            >
              <span
                className={`w-7 font-serif ${first ? "text-[28px] text-accent" : "text-[24px] text-muted"}`}
              >
                {entry.rank}
              </span>
              <span className={`flex-grow font-serif ${first ? "text-[28px]" : "text-[24px]"}`}>
                {entry.display_name}
                {mine && <span className="font-sans text-sm text-muted"> (you)</span>}
              </span>
              <span
                className={`tabular-nums ${first ? "text-[20px]" : "text-[18px] text-muted"}`}
              >
                {entry.score}
              </span>
            </li>
          );
        })}
      </ol>

      {nextOpen && (
        <div className="rounded-md border border-soft bg-surface px-4 py-3 flex items-center justify-between">
          <span className="text-[15px] text-muted">Back in the lobby</span>
          <span className="text-[15px] tabular-nums">
            {next.returned.length} of {next.total}
          </span>
        </div>
      )}

      {error && (
        <p role="alert" className="text-red-500 text-sm">
          {error}
        </p>
      )}

      <div className="flex flex-col gap-3">
        {isPlayer && (
          <PrimaryButton onClick={handleReplay} disabled={replaying}>
            {replaying ? "One moment…" : nextOpen ? "Join the next game" : "Play again"}
          </PrimaryButton>
        )}
        <SecondaryButton onClick={() => router.push("/games")}>Choose another game</SecondaryButton>
      </div>
    </div>
  );
}
