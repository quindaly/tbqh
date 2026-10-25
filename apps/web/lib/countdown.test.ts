import { describe, expect, it } from "vitest";
import { formatClock, secondsLeft } from "./countdown";

describe("formatClock", () => {
  it("formats m:ss", () => {
    expect(formatClock(60)).toBe("1:00");
    expect(formatClock(42)).toBe("0:42");
    expect(formatClock(9.2)).toBe("0:10"); // rounds up so it never shows 0:00 early
    expect(formatClock(0)).toBe("0:00");
    expect(formatClock(-5)).toBe("0:00");
    expect(formatClock(125)).toBe("2:05");
  });
});

describe("secondsLeft", () => {
  it("counts down from the server value using only elapsed local time", () => {
    expect(secondsLeft(60, 1000, 1000)).toBe(60);
    expect(secondsLeft(60, 1000, 11000)).toBe(50);
  });
  it("never goes below zero", () => {
    expect(secondsLeft(5, 0, 60000)).toBe(0);
  });
  it("is unaffected by the absolute value of the local clock", () => {
    // A device whose clock is wildly off still shows the right remaining time
    expect(secondsLeft(30, 9_999_999_000, 9_999_999_000 + 10_000)).toBe(20);
  });
});
