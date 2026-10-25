/**
 * Keeps edited answer text in sync with the server without losing keystrokes.
 *
 * The review screen used to send an edit only when a Save button was clicked, so
 * text typed and then left (or typed just before "Confirm") never reached the
 * database. This controller saves every edit automatically and tells the screen
 * when it is safe to confirm:
 *
 * - each choice has at most one request in flight; text typed meanwhile is sent
 *   in a follow-up request, so responses can never arrive out of order;
 * - every request carries the revision the server last confirmed, so a stale
 *   write is refused by the server instead of overwriting newer text;
 * - `flush()` resolves once nothing is dirty or in flight, and `isClean()` says
 *   whether the screen matches the database.
 */

export type SaveStatus = "saved" | "dirty" | "saving" | "error" | "invalid" | "stale";

export interface ChoiceState {
  /** What the user sees in the input. */
  draft: string;
  /** Last text the server confirmed. */
  serverText: string;
  /** Last revision the server confirmed. */
  revision: number;
  status: SaveStatus;
  message?: string;
}

export interface SaveResult {
  text: string;
  revision: number;
}

export type SaveFn = (
  choiceId: string,
  text: string,
  expectedRevision: number
) => Promise<SaveResult>;

/** What the controller needs to know about a failed request. */
export interface SaveFailure {
  status: number;
  code?: string;
  message: string;
}

export interface Scheduler {
  setTimeout: (fn: () => void, ms: number) => unknown;
  clearTimeout: (handle: unknown) => void;
}

const defaultScheduler: Scheduler = {
  setTimeout: (fn, ms) => setTimeout(fn, ms),
  clearTimeout: (h) => clearTimeout(h as ReturnType<typeof setTimeout>),
};

export class ChoiceSaver {
  private choices = new Map<string, ChoiceState>();
  private timers = new Map<string, unknown>();
  private inflight = new Map<string, Promise<void>>();
  private listeners = new Set<() => void>();
  private snapshot: Record<string, ChoiceState> = {};

  constructor(
    private save: SaveFn,
    private classify: (err: unknown) => SaveFailure,
    private debounceMs = 700,
    private scheduler: Scheduler = defaultScheduler
  ) {}

  subscribe(fn: () => void) {
    this.listeners.add(fn);
    return () => {
      this.listeners.delete(fn);
    };
  }

  private emit() {
    this.snapshot = Object.fromEntries(this.choices);
    this.listeners.forEach((l) => l());
  }

  /** Current state of every tracked choice (new object whenever anything changes). */
  getAll(): Record<string, ChoiceState> {
    return this.snapshot;
  }

  /** Replace all state with what the server says (initial load, or after a conflict). */
  load(items: { id: string; text: string; revision: number }[]) {
    this.timers.forEach((h) => this.scheduler.clearTimeout(h));
    this.timers.clear();
    this.choices.clear();
    for (const it of items) {
      this.choices.set(it.id, {
        draft: it.text,
        serverText: it.text,
        revision: it.revision,
        status: "saved",
      });
    }
    this.emit();
  }

  /** Update one choice from a server response (regeneration). */
  adopt(id: string, text: string, revision: number) {
    const cur = this.choices.get(id);
    if (!cur) return;
    this.cancelTimer(id);
    this.choices.set(id, { draft: text, serverText: text, revision, status: "saved" });
    this.emit();
  }

  get(id: string): ChoiceState | undefined {
    return this.choices.get(id);
  }

  setDraft(id: string, text: string) {
    const cur = this.choices.get(id);
    if (!cur) return;
    const next: ChoiceState = { ...cur, draft: text };
    if (cur.status === "stale") {
      // Only a reload from the server clears this; keep what the user typed.
      this.choices.set(id, next);
      this.emit();
      return;
    }
    if (text === cur.serverText && cur.status !== "saving") {
      next.status = "saved";
      next.message = undefined;
      this.cancelTimer(id);
    } else if (cur.status !== "saving") {
      next.status = text.trim() ? "dirty" : "invalid";
      next.message = text.trim() ? undefined : "Answer can't be empty";
      this.cancelTimer(id);
      if (text.trim()) {
        this.timers.set(
          id,
          this.scheduler.setTimeout(() => {
            this.timers.delete(id);
            void this.flushOne(id);
          }, this.debounceMs)
        );
      }
    }
    this.choices.set(id, next);
    this.emit();
  }

  private cancelTimer(id: string) {
    const h = this.timers.get(id);
    if (h !== undefined) {
      this.scheduler.clearTimeout(h);
      this.timers.delete(id);
    }
  }

  /** Save one choice now (if it needs saving). Resolves when it settles. */
  flushOne(id: string): Promise<void> {
    this.cancelTimer(id);
    const running = this.inflight.get(id);
    if (running) {
      // Wait for the current request, then loop to send whatever changed since.
      return running.then(() => this.flushOne(id));
    }
    const cur = this.choices.get(id);
    if (!cur) return Promise.resolve();
    if (cur.draft === cur.serverText) {
      if (cur.status !== "saved") {
        this.choices.set(id, { ...cur, status: "saved", message: undefined });
        this.emit();
      }
      return Promise.resolve();
    }
    if (!cur.draft.trim()) {
      this.choices.set(id, { ...cur, status: "invalid", message: "Answer can't be empty" });
      this.emit();
      return Promise.resolve();
    }
    if (cur.status === "stale") return Promise.resolve();

    const sending = cur.draft;
    this.choices.set(id, { ...cur, status: "saving", message: undefined });
    this.emit();

    const p = this.save(id, sending, cur.revision).then(
      (res) => {
        const now = this.choices.get(id)!;
        // If the user kept typing, the draft stays and a follow-up save is due.
        const caughtUp = now.draft === sending;
        this.choices.set(id, {
          draft: caughtUp ? res.text : now.draft,
          serverText: res.text,
          revision: res.revision,
          status: caughtUp ? "saved" : "dirty",
        });
        this.inflight.delete(id);
        this.emit();
        if (!caughtUp) return this.flushOne(id);
      },
      (err) => {
        const f = this.classify(err);
        const now = this.choices.get(id)!;
        let status: SaveStatus = "error";
        if (f.code === "stale_revision" || f.code === "choices_locked") status = "stale";
        else if (f.status === 400 || f.code === "duplicate_choice") status = "invalid";
        this.choices.set(id, { ...now, status, message: f.message });
        this.inflight.delete(id);
        this.emit();
      }
    );
    this.inflight.set(id, p);
    return p;
  }

  /** Save everything pending. Resolves with true when the screen matches the server. */
  async flush(): Promise<boolean> {
    await Promise.all([...this.choices.keys()].map((id) => this.flushOne(id)));
    return this.isClean();
  }

  /** True when every choice is saved (nothing dirty, in flight, or failed). */
  isClean(): boolean {
    for (const c of this.choices.values()) {
      if (c.status !== "saved" || c.draft !== c.serverText) return false;
    }
    return true;
  }

  /** Revisions the server has confirmed, to send with "confirm". */
  revisions(): Record<string, number> {
    return Object.fromEntries(
      [...this.choices.entries()].map(([id, c]) => [id, c.revision])
    );
  }

  /** Stop timers (call on unmount). */
  dispose() {
    this.timers.forEach((h) => this.scheduler.clearTimeout(h));
    this.timers.clear();
    this.listeners.clear();
  }
}
