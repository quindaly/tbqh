// @vitest-environment jsdom
import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { useCountdown } from "./countdown";

describe("useCountdown", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-01-01T00:00:00Z"));
  });
  afterEach(() => vi.useRealTimers());

  it("returns null when there is no clock", () => {
    const { result } = renderHook(() => useCountdown(null, 0));
    expect(result.current).toBeNull();
  });

  it("counts down in real time from the server's value", () => {
    const received = Date.now();
    const { result } = renderHook(() => useCountdown({ seconds_remaining: 30 }, received));
    expect(result.current).toBeCloseTo(30, 0);
    act(() => {
      vi.advanceTimersByTime(10_000);
    });
    expect(result.current).toBeCloseTo(20, 0);
    act(() => {
      vi.advanceTimersByTime(60_000);
    });
    expect(result.current).toBe(0);
  });

  it("does not re-render excessively when the caller passes a new object each render", async () => {
    // Sanity bound on renders (the hook's effect depends on primitives, so a
    // fresh object per render doesn't restart its interval).
    vi.useRealTimers();
    vi.useFakeTimers({ toFake: ["setInterval", "clearInterval", "setTimeout", "clearTimeout"] });
    const received = Date.now();
    let renders = 0;
    renderHook(() => {
      renders += 1;
      return useCountdown({ seconds_remaining: 30 }, received);
    });
    await act(async () => {});
    act(() => {
      vi.advanceTimersByTime(1000);
    });
    // ~4 ticks per second; a feedback loop would run to the hundreds
    expect(renders).toBeLessThan(15);
  });

  it("restarts from a fresh server value", () => {
    const t0 = Date.now();
    const { result, rerender } = renderHook(
      ({ p, at }) => useCountdown(p, at),
      { initialProps: { p: { seconds_remaining: 30 }, at: t0 } }
    );
    act(() => {
      vi.advanceTimersByTime(20_000);
    });
    expect(result.current).toBeCloseTo(10, 0);
    rerender({ p: { seconds_remaining: 25 }, at: Date.now() });
    expect(result.current).toBeCloseTo(25, 0);
  });
});
