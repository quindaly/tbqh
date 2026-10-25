// @vitest-environment jsdom
import { describe, it, expect, afterEach } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import ThemeToggle, { THEME_KEY } from "./ThemeToggle";

afterEach(() => {
  cleanup();
  localStorage.clear();
  document.documentElement.removeAttribute("data-theme");
});

describe("theme toggle", () => {
  it("cycles Match my phone, Light, Dark and remembers the choice", () => {
    render(<ThemeToggle />);
    const root = document.documentElement;
    const btn = () => screen.getByRole("button");

    expect(btn().getAttribute("aria-label")).toContain("Match my phone");
    fireEvent.click(btn());
    expect(root.getAttribute("data-theme")).toBe("light");
    expect(localStorage.getItem(THEME_KEY)).toBe("light");

    fireEvent.click(btn());
    expect(root.getAttribute("data-theme")).toBe("dark");
    expect(localStorage.getItem(THEME_KEY)).toBe("dark");

    fireEvent.click(btn());
    expect(root.hasAttribute("data-theme")).toBe(false);
    expect(localStorage.getItem(THEME_KEY)).toBeNull();
  });

  it("starts from the saved choice", () => {
    localStorage.setItem(THEME_KEY, "dark");
    render(<ThemeToggle />);
    expect(screen.getByRole("button").getAttribute("aria-label")).toContain("Theme: Dark");
  });
});
