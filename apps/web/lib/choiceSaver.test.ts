import { describe, expect, it, vi } from "vitest";
import { ChoiceSaver, SaveFailure, Scheduler } from "./choiceSaver";

/** Manual clock so debounce timers can be stepped without real waiting. */
function fakeScheduler() {
  let now = 0;
  let nextId = 1;
  const pending = new Map<number, { at: number; fn: () => void }>();
  const sched: Scheduler = {
    setTimeout: (fn, ms) => {
      const id = nextId++;
      pending.set(id, { at: now + ms, fn });
      return id;
    },
    clearTimeout: (h) => {
      pending.delete(h as number);
    },
  };
  return {
    sched,
    advance(ms: number) {
      now += ms;
      for (const [id, t] of [...pending]) {
        if (t.at <= now) {
          pending.delete(id);
          t.fn();
        }
      }
    },
    pendingCount: () => pending.size,
  };
}

const classify = (err: unknown): SaveFailure => err as SaveFailure;

/** A save function whose responses the test releases one at a time. */
function controlledSave() {
  const calls: { id: string; text: string; rev: number; resolve: (r?: any) => void; reject: (e: any) => void }[] = [];
  const fn = vi.fn(
    (id: string, text: string, rev: number) =>
      new Promise<{ text: string; revision: number }>((resolve, reject) => {
        calls.push({
          id,
          text,
          rev,
          resolve: (r) => resolve(r ?? { text, revision: rev + 1 }),
          reject,
        });
      })
  );
  return { fn, calls };
}

function setup() {
  const clock = fakeScheduler();
  const save = controlledSave();
  const saver = new ChoiceSaver(save.fn, classify, 700, clock.sched);
  saver.load([
    { id: "a", text: "Tacos", revision: 0 },
    { id: "b", text: "Sushi", revision: 0 },
  ]);
  return { clock, save, saver };
}

describe("ChoiceSaver", () => {
  it("starts clean", () => {
    const { saver } = setup();
    expect(saver.isClean()).toBe(true);
  });

  it("is dirty while typing and saves after the debounce", async () => {
    const { clock, save, saver } = setup();
    saver.setDraft("a", "Pasta");
    expect(saver.isClean()).toBe(false);
    expect(save.fn).not.toHaveBeenCalled();
    clock.advance(699);
    expect(save.fn).not.toHaveBeenCalled();
    clock.advance(1);
    expect(save.fn).toHaveBeenCalledWith("a", "Pasta", 0);
    expect(saver.get("a")!.status).toBe("saving");
    save.calls[0].resolve();
    await Promise.resolve();
    await Promise.resolve();
    expect(saver.get("a")).toMatchObject({ status: "saved", revision: 1, serverText: "Pasta" });
    expect(saver.isClean()).toBe(true);
  });

  it("restarts the debounce on each keystroke (one request for a burst)", () => {
    const { clock, save, saver } = setup();
    saver.setDraft("a", "P");
    clock.advance(500);
    saver.setDraft("a", "Pa");
    clock.advance(500);
    saver.setDraft("a", "Pas");
    clock.advance(699);
    expect(save.fn).not.toHaveBeenCalled();
    clock.advance(1);
    expect(save.fn).toHaveBeenCalledTimes(1);
    expect(save.calls[0].text).toBe("Pas");
  });

  it("flush() sends pending edits immediately and resolves clean (the 'typed then clicked Confirm' case)", async () => {
    const { save, saver } = setup();
    saver.setDraft("a", "Lasagna");
    const done = saver.flush();
    expect(save.fn).toHaveBeenCalledWith("a", "Lasagna", 0);
    save.calls[0].resolve();
    expect(await done).toBe(true);
    expect(saver.revisions()).toEqual({ a: 1, b: 0 });
  });

  it("never has two requests in flight for one choice and sends the latest text next", async () => {
    const { clock, save, saver } = setup();
    saver.setDraft("a", "One");
    clock.advance(700);
    expect(save.calls).toHaveLength(1);
    saver.setDraft("a", "Two"); // typed while 'One' is in flight
    clock.advance(5000);
    expect(save.calls).toHaveLength(1);
    save.calls[0].resolve();
    await Promise.resolve();
    await Promise.resolve();
    // follow-up for the newer text, built on the revision 'One' produced
    expect(save.calls).toHaveLength(2);
    expect(save.calls[1]).toMatchObject({ text: "Two", rev: 1 });
    expect(saver.get("a")!.draft).toBe("Two");
    save.calls[1].resolve();
    await Promise.resolve();
    await Promise.resolve();
    expect(saver.get("a")).toMatchObject({ status: "saved", serverText: "Two", revision: 2 });
  });

  it("keeps the user's text when a save fails and lets flush retry", async () => {
    const { save, saver } = setup();
    saver.setDraft("a", "Pasta");
    const first = saver.flush();
    save.calls[0].reject({ status: 0, message: "Can't reach the server" });
    expect(await first).toBe(false);
    expect(saver.get("a")).toMatchObject({ status: "error", draft: "Pasta" });
    expect(saver.isClean()).toBe(false);
    const retry = saver.flush();
    expect(save.calls).toHaveLength(2);
    save.calls[1].resolve();
    expect(await retry).toBe(true);
  });

  it("marks duplicates as invalid and blocks confirm", async () => {
    const { save, saver } = setup();
    saver.setDraft("a", "Sushi");
    const p = saver.flush();
    save.calls[0].reject({ status: 409, code: "duplicate_choice", message: "Already used" });
    expect(await p).toBe(false);
    expect(saver.get("a")).toMatchObject({ status: "invalid", message: "Already used" });
  });

  it("does not send blank text", async () => {
    const { save, saver } = setup();
    saver.setDraft("a", "   ");
    expect(await saver.flush()).toBe(false);
    expect(save.fn).not.toHaveBeenCalled();
    expect(saver.get("a")!.status).toBe("invalid");
    saver.setDraft("a", "Tacos"); // back to the saved text
    expect(saver.isClean()).toBe(true);
  });

  it("treats a stale-revision conflict as stale until reloaded", async () => {
    const { save, saver } = setup();
    saver.setDraft("a", "Pasta");
    const p = saver.flush();
    save.calls[0].reject({ status: 409, code: "stale_revision", message: "Changed elsewhere" });
    await p;
    expect(saver.get("a")!.status).toBe("stale");
    saver.setDraft("a", "Pasta!");
    expect(saver.get("a")!.status).toBe("stale");
    expect(await saver.flush()).toBe(false);
    expect(save.fn).toHaveBeenCalledTimes(1);
    saver.load([{ id: "a", text: "Newer", revision: 3 }, { id: "b", text: "Sushi", revision: 0 }]);
    expect(saver.isClean()).toBe(true);
    expect(saver.get("a")!.draft).toBe("Newer");
  });

  it("adopts a regenerated answer and cancels a pending save of the old text", () => {
    const { clock, save, saver } = setup();
    saver.setDraft("a", "Half typed");
    saver.adopt("a", "Fresh AI idea", 1);
    clock.advance(5000);
    expect(save.fn).not.toHaveBeenCalled();
    expect(saver.get("a")).toMatchObject({ draft: "Fresh AI idea", revision: 1, status: "saved" });
  });

  it("reports changes to subscribers with a new snapshot object", () => {
    const { saver } = setup();
    const seen: unknown[] = [];
    saver.subscribe(() => seen.push(saver.getAll()));
    saver.setDraft("a", "x");
    saver.setDraft("a", "xy");
    expect(seen).toHaveLength(2);
    expect(seen[0]).not.toBe(seen[1]);
  });

  it("dispose() stops pending timers", () => {
    const { clock, save, saver } = setup();
    saver.setDraft("a", "Pasta");
    saver.dispose();
    clock.advance(5000);
    expect(save.fn).not.toHaveBeenCalled();
  });
});
