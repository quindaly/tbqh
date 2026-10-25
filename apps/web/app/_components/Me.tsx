"use client";

import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import { getMe, updateMyName, type Me } from "@/lib/api";
import { Heading, PrimaryButton } from "./ui";

interface MeState {
  me: Me | null;
  /** The first answer has come back (signed in or not). */
  loaded: boolean;
  setMe: (me: Me | null) => void;
}

const MeContext = createContext<MeState>({ me: null, loaded: false, setMe: () => {} });

/** Who is signed in, fetched once and shared by the nav bar, home page and name prompt. */
export function MeProvider({ children }: { children: ReactNode }) {
  const [me, setMe] = useState<Me | null>(null);
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    getMe()
      .then(setMe)
      .catch(() => setMe(null))
      .finally(() => setLoaded(true));
  }, []);

  return <MeContext.Provider value={{ me, loaded, setMe }}>{children}</MeContext.Provider>;
}

export function useMe() {
  return useContext(MeContext);
}

/** True for someone with a real account (not signed out, not a guest). */
export function isSignedIn(me: Me | null): boolean {
  return !!me && !me.is_guest;
}

/**
 * Asked once, right after someone's first sign-in: what should we call you?
 * It sits over whatever page they landed on, so returning to a game in
 * progress is not interrupted. "Not now" is a fine answer.
 */
export function NamePrompt() {
  const { me, setMe } = useMe();
  const [name, setName] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  if (!me?.needs_name) return null;

  async function finish(update: { name?: string; skip?: boolean }) {
    setSaving(true);
    setError("");
    try {
      const res = await updateMyName(update);
      setMe({ ...me!, name: res.name, needs_name: false });
    } catch (e: any) {
      setError(e?.message || "Couldn't save that. Try again.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 px-4"
      role="dialog"
      aria-modal="true"
      aria-labelledby="name-prompt-title"
    >
      <form
        className="w-full max-w-sm bg-paper border border-soft rounded-md p-6 flex flex-col gap-4"
        onSubmit={(e) => {
          e.preventDefault();
          if (name.trim()) void finish({ name: name.trim() });
        }}
      >
        <div id="name-prompt-title">
          <Heading size={28}>What should we call you?</Heading>
        </div>
        <p className="text-muted text-sm">We&apos;ll use it to say hello when you come back.</p>
        <input
          autoFocus
          aria-label="Your name"
          placeholder="Your name"
          autoComplete="given-name"
          maxLength={40}
          value={name}
          onChange={(e) => setName(e.target.value)}
          className="w-full px-4 min-h-[56px] border border-line rounded-md bg-surface text-[17px]"
        />
        {error && (
          <p role="alert" className="text-red-500 text-sm">
            {error}
          </p>
        )}
        <PrimaryButton type="submit" disabled={saving || !name.trim()}>
          {saving ? "Saving…" : "Save"}
        </PrimaryButton>
        <button
          type="button"
          onClick={() => void finish({ skip: true })}
          disabled={saving}
          className="text-sm text-muted hover:underline min-h-[44px]"
        >
          Not now
        </button>
      </form>
    </div>
  );
}
