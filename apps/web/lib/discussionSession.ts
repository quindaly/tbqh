/**
 * What this browser remembers about each Discussion Questions session.
 *
 * Kept per session (not in one global slot) so starting or joining a second
 * session doesn't overwrite the first one's participant and profile.
 */

export interface SessionMemory {
  participantId?: string;
  joinCode?: string;
  provisionalProfileId?: string;
  groupProfileId?: string;
  experienceId?: string;
}

const key = (sessionId: string) => `tbqh_session_${sessionId}`;

export function readSession(sessionId: string): SessionMemory {
  try {
    const raw = localStorage.getItem(key(sessionId));
    if (raw) return JSON.parse(raw) as SessionMemory;
    // Sessions started before this existed used global keys.
    if (localStorage.getItem("session_id") === sessionId) {
      return {
        participantId: localStorage.getItem("participant_id") || undefined,
        joinCode: localStorage.getItem("join_code") || undefined,
        provisionalProfileId: localStorage.getItem("provisional_group_profile_id") || undefined,
        groupProfileId: localStorage.getItem("group_profile_id") || undefined,
      };
    }
  } catch {
    /* storage unavailable: behave as if nothing is remembered */
  }
  return {};
}

export function rememberSession(sessionId: string, patch: SessionMemory): SessionMemory {
  const next = { ...readSession(sessionId), ...patch };
  try {
    localStorage.setItem(key(sessionId), JSON.stringify(next));
  } catch {
    /* private mode etc.: the flow still works until the page is reloaded */
  }
  return next;
}

/** "Other (type your own)" is the free-text choice; "Together" or "Mother's side" are not. */
export function isOtherOption(option: string | null | undefined): boolean {
  return !!option && /^other(\s*\(.*\))?$/i.test(option.trim());
}

/** A link a friend can open to join this session with the code already filled in. */
export function inviteLink(sessionId: string, joinCode: string | undefined): string {
  const q = new URLSearchParams({ s: sessionId });
  if (joinCode) q.set("c", joinCode);
  return `${window.location.origin}/join?${q.toString()}`;
}

const SAFE_VALUE = /^[A-Za-z0-9_-]{1,64}$/;
const RESUME_KEYS: (keyof SessionMemory)[] = [
  "participantId",
  "joinCode",
  "provisionalProfileId",
  "groupProfileId",
  "experienceId",
];

/**
 * The part of this browser's memory of a session that is worth carrying through
 * a sign-in link, as a URL-safe string. If the email opens in a different
 * browser (an in-app mail viewer, say), the page can pick up where it left off
 * instead of starting over. It holds ids only, nothing secret.
 */
export function encodeResume(sessionId: string): string | null {
  const mem = readSession(sessionId);
  const keep: Record<string, string> = {};
  for (const k of RESUME_KEYS) {
    const v = mem[k];
    if (v && SAFE_VALUE.test(v)) keep[k] = v;
  }
  if (!Object.keys(keep).length) return null;
  try {
    return btoa(JSON.stringify(keep)).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
  } catch {
    return null;
  }
}

/** Add `r=<memory>` to a /session/... path so the page can restore it. */
export function withResume(path: string): string {
  const m = /^\/session\/([^/?#]+)/.exec(path);
  if (!m) return path;
  const r = encodeResume(m[1]);
  if (!r) return path;
  return `${path}${path.includes("?") ? "&" : "?"}r=${r}`;
}

/**
 * If the page was opened from a sign-in link carrying `r=`, restore that
 * memory (without overwriting what this browser already knows) and tidy the URL.
 */
export function adoptResume(sessionId: string): void {
  try {
    const url = new URL(window.location.href);
    const r = url.searchParams.get("r");
    if (!r) return;
    url.searchParams.delete("r");
    window.history.replaceState(null, "", url.pathname + (url.search || "") + url.hash);

    const parsed = JSON.parse(atob(r.replace(/-/g, "+").replace(/_/g, "/")));
    const mine = readSession(sessionId);
    const patch: SessionMemory = {};
    for (const k of RESUME_KEYS) {
      const v = parsed?.[k];
      if (typeof v === "string" && SAFE_VALUE.test(v) && !mine[k]) patch[k] = v;
    }
    if (Object.keys(patch).length) rememberSession(sessionId, patch);
  } catch {
    /* a mangled link: carry on with whatever this browser remembers */
  }
}
