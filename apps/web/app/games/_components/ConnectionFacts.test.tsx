// @vitest-environment jsdom
import { readFileSync } from "fs";
import path from "path";
import { act, cleanup, render } from "@testing-library/react";
import { useState } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { CONNECTION_FACTS, FACT_ROTATION_MS } from "@/lib/connectionFacts";
import { ConnectionFacts } from "./ConnectionFacts";

const active = (container: HTMLElement) =>
  container.querySelector('[data-active="true"]')?.textContent ?? "";

const tick = (ms: number) =>
  act(() => {
    vi.advanceTimersByTime(ms);
  });

describe("fact content", () => {
  it("has the 15 facts, each with a title and a body, in the agreed order", () => {
    expect(CONNECTION_FACTS).toHaveLength(15);
    expect(new Set(CONNECTION_FACTS.map((f) => f.id)).size).toBe(15);
    for (const f of CONNECTION_FACTS) {
      expect(f.title.trim()).not.toBe("");
      expect(f.body.trim()).not.toBe("");
    }
    expect(CONNECTION_FACTS[0].title).toBe("We’re better at connecting than we think.");
    expect(CONNECTION_FACTS[14].title).toBe("Knowing someone starts with asking.");
  });

  it("rotates every 20 seconds", () => {
    expect(FACT_ROTATION_MS).toBe(20_000);
  });
});

describe("<ConnectionFacts />", () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => {
    cleanup();
    vi.useRealTimers();
  });

  it("shows the first fact first", () => {
    const { container } = render(<ConnectionFacts />);
    expect(active(container)).toContain(CONNECTION_FACTS[0].title);
    expect(active(container)).toContain(CONNECTION_FACTS[0].body);
  });

  it("moves to the next fact every 20 seconds, not before", () => {
    const { container } = render(<ConnectionFacts />);
    tick(19_999);
    expect(active(container)).toContain(CONNECTION_FACTS[0].title);
    tick(1);
    expect(active(container)).toContain(CONNECTION_FACTS[1].title);
    tick(20_000);
    expect(active(container)).toContain(CONNECTION_FACTS[2].title);
  });

  it("loops back to the first fact after the last", () => {
    const { container } = render(<ConnectionFacts />);
    tick(FACT_ROTATION_MS * (CONNECTION_FACTS.length - 1));
    expect(active(container)).toContain(CONNECTION_FACTS[14].title);
    tick(FACT_ROTATION_MS);
    expect(active(container)).toContain(CONNECTION_FACTS[0].title);
  });

  it("stops its timer when the lobby is left", () => {
    const { unmount } = render(<ConnectionFacts />);
    expect(vi.getTimerCount()).toBe(1);
    unmount();
    expect(vi.getTimerCount()).toBe(0);
  });

  it("is not restarted by the lobby refreshing around it", () => {
    // The lobby re-renders every few seconds as it polls the server.
    function Lobby() {
      const [, setN] = useState(0);
      return (
        <div>
          <button onClick={() => setN((n) => n + 1)}>poll</button>
          <ConnectionFacts />
        </div>
      );
    }
    const { container, getByText } = render(<Lobby />);
    for (let i = 0; i < 6; i++) {
      tick(3_000);
      act(() => getByText("poll").click());
    }
    // 18s in, still the first fact; 2 more seconds and it changes right on time.
    expect(active(container)).toContain(CONNECTION_FACTS[0].title);
    tick(2_000);
    expect(active(container)).toContain(CONNECTION_FACTS[1].title);
    expect(vi.getTimerCount()).toBe(1);
  });

  it("does not announce changes to screen readers", () => {
    const { container } = render(<ConnectionFacts />);
    expect(container.querySelector("[aria-live]")).toBeNull();
    expect(container.querySelector('[role="status"], [role="alert"]')).toBeNull();
  });

  it("hides the facts that aren't showing from assistive tech and from view", () => {
    const { container } = render(<ConnectionFacts />);
    const hidden = container.querySelectorAll('[aria-hidden="true"]');
    expect(hidden).toHaveLength(CONNECTION_FACTS.length - 1);
    hidden.forEach((el) => expect(el.className).toContain("invisible"));
  });

  it("keeps all facts in one grid cell so the card height never changes", () => {
    const { container } = render(<ConnectionFacts />);
    const cells = Array.from(container.querySelectorAll("[data-active]")) as HTMLElement[];
    expect(cells).toHaveLength(CONNECTION_FACTS.length);
    cells.forEach((c) => expect(c.style.gridArea).toBe("1 / 1"));
  });

  it("lets long text wrap instead of overflowing", () => {
    const { container } = render(<ConnectionFacts />);
    const cell = container.querySelector("[data-active]") as HTMLElement;
    expect(cell.className).toContain("break-words");
    expect(cell.className).toContain("min-w-0");
  });

  it("does not rotate (or keep a timer) with a single fact", () => {
    const { container } = render(<ConnectionFacts facts={[CONNECTION_FACTS[3]]} />);
    expect(vi.getTimerCount()).toBe(0);
    tick(60_000);
    expect(active(container)).toContain(CONNECTION_FACTS[3].title);
  });

  it("renders nothing when there are no facts", () => {
    const { container } = render(<ConnectionFacts facts={[]} />);
    expect(container.innerHTML).toBe("");
  });
});

describe("reduced motion", () => {
  it("only fades the fact for people who haven't asked for reduced motion", () => {
    const css = readFileSync(path.join(__dirname, "../../globals.css"), "utf8");
    const rule = css.match(
      /@media \(prefers-reduced-motion: no-preference\)\s*\{[^}]*\{[^}]*connection-fact-fade[^}]*\}\s*\}/
    );
    expect(rule).not.toBeNull();
    // no other use of the animation outside that media query
    const outside = css.replace(rule![0], "");
    expect(outside).not.toMatch(/animation:\s*connection-fact-fade/);
  });
});
