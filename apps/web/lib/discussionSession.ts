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
