"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { checkIn } from "@/lib/api";

const PING_EVERY_MS = 10_000;

/**
 * Wraps every page of a game. While one is open it tells the server "still
 * here" every few seconds. That is how the lobby can show who has gone quiet,
 * how the host can clear them out, and how host controls pass to someone who
 * is still here if the host closes their tab.
 *
 * It also catches the two cases where this person is no longer in the game.
 */
export default function ExperienceLayout({ children }: { children: React.ReactNode }) {
  const { experienceId } = useParams<{ experienceId: string }>();
  const [notice, setNotice] = useState<"removed" | "left_out" | null>(null);

  useEffect(() => {
    let participantId = "";
    try {
      participantId = localStorage.getItem(`game_pid_${experienceId}`) || "";
    } catch {
      /* private mode: nothing to report */
    }
    if (!participantId) return;

    let stopped = false;
    const ping = async () => {
      try {
        const res = await checkIn(experienceId, participantId);
        if (stopped) return;
        setNotice(res.removed ? "removed" : res.left_out ? "left_out" : null);
      } catch {
        /* offline or a hiccup: the next ping will try again */
      }
    };
    const onVisible = () => {
      if (document.visibilityState === "visible") ping();
    };

    ping();
    const timer = setInterval(ping, PING_EVERY_MS);
    document.addEventListener("visibilitychange", onVisible);
    return () => {
      stopped = true;
      clearInterval(timer);
      document.removeEventListener("visibilitychange", onVisible);
    };
  }, [experienceId]);

  if (notice) {
    return (
      <div className="max-w-md mx-auto py-16 text-center space-y-4" role="status">
        <h1 className="font-serif text-[28px] leading-[1.15] font-normal">
          {notice === "removed" ? "You were removed from this game" : "This game started without you"}
        </h1>
        <p className="text-muted">
          {notice === "removed"
            ? "The host cleared the lobby because you had left. If you are back, join again with the code."
            : "The host began once enough people had finished their answers. When it ends, enter the same code to join the next one."}
        </p>
        <Link
          href="/games"
          className="inline-flex items-center justify-center w-64 px-6 py-3 bg-btn text-btn-text rounded-md hover:opacity-90 transition min-h-[56px] text-[17px] font-medium"
        >
          Back to games
        </Link>
      </div>
    );
  }

  return <>{children}</>;
}
