"use client";

import { useState, useEffect, Suspense } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { createHWDYKGame, joinHWDYKGame } from "@/lib/api";

const NAME_KEY = "tbqh-display-name";
const QUESTION_CHOICES = [3, 5, 7, 10];

type Screen = "start" | "name" | "style" | "length" | "join";
type Style = "default" | "party";

const STYLES: { id: Style; title: string; blurb: string; tag?: string }[] = [
  {
    id: "default",
    title: "We write the wrong answers",
    blurb: "AI makes the other choices. Nothing for your friends to do but guess.",
    tag: "Easiest",
  },
  {
    id: "party",
    title: "Friends write the wrong answers",
    blurb: "Everyone invents a fake answer first. Sneakier and funnier.",
  },
];

function minutesFor(n: number) {
  return Math.round(n * 0.8 + 2);
}

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

export default function HotSeatStartPage() {
  return (
    <Suspense fallback={<div className="py-12 text-center text-muted">Loading…</div>}>
      <HotSeatStart />
    </Suspense>
  );
}

function Heading({ children }: { children: React.ReactNode }) {
  return (
    <h1 className="font-serif text-[34px] leading-[1.1] tracking-[-0.01em] font-normal">
      {children}
    </h1>
  );
}

function Eyebrow({ children }: { children: React.ReactNode }) {
  return <span className="text-xs tracking-[0.14em] uppercase text-muted">{children}</span>;
}

function PrimaryButton(props: React.ButtonHTMLAttributes<HTMLButtonElement>) {
  return (
    <button
      {...props}
      className="w-full px-6 bg-btn text-btn-text rounded-md hover:opacity-90 transition disabled:opacity-50 min-h-[56px] text-[17px] font-medium"
    />
  );
}

function BackLink({ onClick }: { onClick: () => void }) {
  return (
    <button onClick={onClick} className="text-sm text-muted hover:underline self-start">
      ← Back
    </button>
  );
}

function HotSeatStart() {
  const router = useRouter();
  const searchParams = useSearchParams();

  const [screen, setScreen] = useState<Screen>("start");
  const [displayName, setDisplayName] = useState("");
  const [joinCode, setJoinCode] = useState("");
  const [style, setStyle] = useState<Style>("default");
  const [numQuestions, setNumQuestions] = useState(5);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    setDisplayName(readName());
  }, []);

  // A shared link (?code=ABC123) goes straight to joining.
  useEffect(() => {
    const code = searchParams.get("code");
    if (code) {
      setJoinCode(code.toUpperCase());
      setScreen("join");
    }
  }, [searchParams]);

  function go(next: Screen) {
    setError("");
    setScreen(next);
  }

  function continueFromName(next: Screen) {
    if (!displayName.trim()) {
      setError("Enter your name so friends know who you are");
      return;
    }
    go(next);
  }

  async function handleCreate() {
    setLoading(true);
    setError("");
    try {
      const name = displayName.trim();
      saveName(name);
      const res = await createHWDYKGame(name, style, numQuestions);
      localStorage.setItem(`game_pid_${res.experience_instance_id}`, res.participant_id);
      router.push(`/games/experience/${res.experience_instance_id}/hwdyk-lobby`);
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
      const res = await joinHWDYKGame(joinCode.trim().toUpperCase(), name);
      localStorage.setItem(`game_pid_${res.experience_instance_id}`, res.participant_id);
      router.push(`/games/experience/${res.experience_instance_id}/hwdyk-lobby`);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }

  const errorLine = error ? <p className="text-red-500 text-sm">{error}</p> : null;

  if (screen === "start") {
    return (
      <div className="max-w-md mx-auto flex flex-col gap-8 py-10">
        <div className="flex flex-col gap-3">
          <Heading>The Hot Seat</Heading>
          <p className="text-muted">
            One person sits in the hot seat and answers questions about themselves. Everyone else
            guesses what they said.
          </p>
        </div>
        <div className="flex flex-col gap-3">
          <PrimaryButton onClick={() => go("name")}>Start a game</PrimaryButton>
          <button
            onClick={() => go("join")}
            className="w-full px-6 border border-line rounded-md hover:bg-soft transition min-h-[56px] text-[17px]"
          >
            Join with a code
          </button>
        </div>
        <a href="/games" className="text-sm text-muted hover:underline">
          ← All games
        </a>
      </div>
    );
  }

  if (screen === "name") {
    return (
      <form
        className="max-w-md mx-auto flex flex-col gap-6 py-10"
        onSubmit={(e) => {
          e.preventDefault();
          continueFromName("style");
        }}
      >
        <BackLink onClick={() => go("start")} />
        <div className="flex flex-col gap-2">
          <Eyebrow>Step 1 of 3</Eyebrow>
          <Heading>What should we call you?</Heading>
        </div>
        <input
          type="text"
          autoFocus
          autoComplete="given-name"
          aria-label="Your name"
          placeholder="Your name"
          value={displayName}
          onChange={(e) => setDisplayName(e.target.value)}
          className="w-full px-4 min-h-[56px] border rounded-md bg-surface text-[17px]"
          maxLength={40}
        />
        {errorLine}
        <PrimaryButton type="submit">Continue</PrimaryButton>
      </form>
    );
  }

  if (screen === "style") {
    return (
      <div className="max-w-md mx-auto flex flex-col gap-6 py-10">
        <BackLink onClick={() => go("name")} />
        <div className="flex flex-col gap-2">
          <Eyebrow>Step 2 of 3</Eyebrow>
          <Heading>How should the wrong answers work?</Heading>
        </div>
        <div className="flex flex-col gap-3" role="radiogroup" aria-label="Wrong answers">
          {STYLES.map((s) => {
            const on = style === s.id;
            return (
              <button
                key={s.id}
                role="radio"
                aria-checked={on}
                onClick={() => setStyle(s.id)}
                className={`text-left rounded-md p-4 min-h-[56px] transition ${
                  on ? "border-2 border-accent bg-selected" : "border border-soft bg-surface hover:bg-soft"
                }`}
              >
                <div className="flex items-center justify-between gap-3">
                  <span className="font-serif text-[22px] leading-[1.2]">{s.title}</span>
                  {s.tag && <span className="text-xs text-accent whitespace-nowrap">{s.tag}</span>}
                </div>
                <p className="text-sm text-muted mt-1">{s.blurb}</p>
              </button>
            );
          })}
        </div>
        <PrimaryButton onClick={() => go("length")}>Continue</PrimaryButton>
      </div>
    );
  }

  if (screen === "length") {
    const mins = minutesFor(numQuestions);
    return (
      <div className="max-w-md mx-auto flex flex-col gap-6 py-10">
        <BackLink onClick={() => go("style")} />
        <div className="flex flex-col gap-2">
          <Eyebrow>Step 3 of 3</Eyebrow>
          <Heading>How many questions?</Heading>
        </div>
        <div className="grid grid-cols-4 gap-3" role="radiogroup" aria-label="Number of questions">
          {QUESTION_CHOICES.map((n) => {
            const on = numQuestions === n;
            return (
              <button
                key={n}
                role="radio"
                aria-checked={on}
                onClick={() => setNumQuestions(n)}
                className={`rounded-md min-h-[56px] font-serif text-[28px] transition ${
                  on ? "border-2 border-accent bg-selected text-accent" : "border border-soft bg-surface hover:bg-soft"
                }`}
              >
                {n}
              </button>
            );
          })}
        </div>
        <p className="text-sm text-muted">
          About {mins} minutes, plus time for friends to join. The person in the hot seat can skip
          any question they would rather not answer.
        </p>
        <div className="border-t border-soft pt-4 text-sm text-muted flex flex-col gap-1">
          <span>
            Playing as <span className="text-ink">{displayName.trim()}</span>
          </span>
          <span>{style === "default" ? "AI writes the wrong answers" : "Friends write the wrong answers"}</span>
        </div>
        {errorLine}
        <PrimaryButton onClick={handleCreate} disabled={loading}>
          {loading ? "Creating…" : "Create game"}
        </PrimaryButton>
      </div>
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
      <BackLink onClick={() => go("start")} />
      <Heading>Join a game</Heading>
      <div className="flex flex-col gap-3">
        <input
          type="text"
          aria-label="Join code"
          placeholder="Join code"
          value={joinCode}
          onChange={(e) => setJoinCode(e.target.value.toUpperCase())}
          className="w-full px-4 min-h-[56px] border rounded-md bg-surface uppercase tracking-widest text-center text-[17px]"
          maxLength={6}
        />
        <input
          type="text"
          autoComplete="given-name"
          aria-label="Your name"
          placeholder="Your name"
          value={displayName}
          onChange={(e) => setDisplayName(e.target.value)}
          className="w-full px-4 min-h-[56px] border rounded-md bg-surface text-[17px]"
          maxLength={40}
        />
      </div>
      {errorLine}
      <PrimaryButton type="submit" disabled={loading}>
        {loading ? "Joining…" : "Join"}
      </PrimaryButton>
    </form>
  );
}
