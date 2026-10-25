"use client";

import { useState, useEffect } from "react";
import { useParams, useRouter } from "next/navigation";
import { createGame, joinGame } from "@/lib/api";
import { BackLink, Heading, PrimaryButton, SecondaryButton } from "../../_components/ui";

const NAME_KEY = "tbqh-display-name";

function readName() {
  try {
    return localStorage.getItem(NAME_KEY) || "";
  } catch {
    return "";
  }
}

function saveName(name: string) {
  try {
    localStorage.setItem(NAME_KEY, name);
  } catch {
    /* private mode: fine */
  }
}

export default function GameSlugPage() {
  const { slug } = useParams<{ slug: string }>();
  const router = useRouter();

  // The Hot Seat has its own start page.
  useEffect(() => {
    if (slug === "how-well-do-you-know") {
      router.replace("/games/how-well-do-you-know");
    }
  }, [slug, router]);

  const [mode, setMode] = useState<"choose" | "create" | "join">("choose");
  const [displayName, setDisplayName] = useState("");
  const [joinCode, setJoinCode] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    setDisplayName(readName());
  }, []);

  // Invite links look like /games/who-knows-who?code=ABC123: jump straight to
  // the join form with the code filled in.
  useEffect(() => {
    const code = new URLSearchParams(window.location.search).get("code");
    if (code) {
      setJoinCode(code.toUpperCase().slice(0, 6));
      setMode("join");
    }
  }, []);

  function go(next: "choose" | "create" | "join") {
    setError("");
    setMode(next);
  }

  async function handleCreate() {
    if (!displayName.trim()) {
      setError("Enter your name so friends know who you are");
      return;
    }
    setLoading(true);
    setError("");
    try {
      const name = displayName.trim();
      saveName(name);
      const res = await createGame(slug, name);
      localStorage.setItem(`game_pid_${res.experience_instance_id}`, res.participant_id);
      router.push(`/games/experience/${res.experience_instance_id}/lobby`);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }

  async function handleJoin() {
    if (!displayName.trim() || !joinCode.trim()) {
      setError("Enter your name and the join code");
      return;
    }
    setLoading(true);
    setError("");
    try {
      const name = displayName.trim();
      saveName(name);
      const res = await joinGame(slug, joinCode.trim().toUpperCase(), name);
      localStorage.setItem(`game_pid_${res.experience_instance_id}`, res.participant_id);
      router.push(`/games/experience/${res.experience_instance_id}/lobby`);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }

  const errorLine = error ? <p role="alert" className="text-red-500 text-sm">{error}</p> : null;

  if (mode === "choose") {
    return (
      <div className="max-w-md mx-auto flex flex-col gap-8 py-10">
        <div className="flex flex-col gap-3">
          <Heading>Who Knows Who</Heading>
          <p className="text-muted">
            Everyone answers questions about themselves. Then you take turns guessing who wrote
            each answer. Best with 3 or more friends.
          </p>
        </div>
        <div className="flex flex-col gap-3">
          <PrimaryButton onClick={() => go("create")}>Start a game</PrimaryButton>
          <SecondaryButton onClick={() => go("join")}>Join with a code</SecondaryButton>
        </div>
        <a href="/games" className="text-sm text-muted hover:underline">
          ← All games
        </a>
      </div>
    );
  }

  if (mode === "create") {
    return (
      <form
        className="max-w-md mx-auto flex flex-col gap-6 py-10"
        onSubmit={(e) => {
          e.preventDefault();
          handleCreate();
        }}
      >
        <BackLink onClick={() => go("choose")} />
        <Heading>What should we call you?</Heading>
        <input
          type="text"
          autoFocus
          autoComplete="given-name"
          aria-label="Your name"
          placeholder="Your name"
          value={displayName}
          onChange={(e) => setDisplayName(e.target.value)}
          maxLength={40}
          className="w-full px-4 min-h-[56px] border rounded-md bg-surface text-[17px]"
        />
        {errorLine}
        <PrimaryButton type="submit" disabled={loading}>
          {loading ? "Creating…" : "Create game"}
        </PrimaryButton>
      </form>
    );
  }

  // Join
  return (
    <form
      className="max-w-md mx-auto flex flex-col gap-6 py-10"
      onSubmit={(e) => {
        e.preventDefault();
        handleJoin();
      }}
    >
      <BackLink onClick={() => go("choose")} />
      <Heading>Join a game</Heading>
      <div className="flex flex-col gap-3">
        <input
          type="text"
          aria-label="Join code"
          placeholder="Join code"
          value={joinCode}
          onChange={(e) => setJoinCode(e.target.value.toUpperCase())}
          maxLength={6}
          className="w-full px-4 min-h-[56px] border rounded-md bg-surface uppercase tracking-widest text-center text-[17px]"
        />
        <input
          type="text"
          autoComplete="given-name"
          aria-label="Your name"
          placeholder="Your name"
          value={displayName}
          onChange={(e) => setDisplayName(e.target.value)}
          maxLength={40}
          className="w-full px-4 min-h-[56px] border rounded-md bg-surface text-[17px]"
        />
      </div>
      {errorLine}
      <PrimaryButton type="submit" disabled={loading}>
        {loading ? "Joining…" : "Join"}
      </PrimaryButton>
    </form>
  );
}
