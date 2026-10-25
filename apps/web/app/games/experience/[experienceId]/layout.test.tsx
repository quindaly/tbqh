// @vitest-environment jsdom
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, waitFor, cleanup, act } from "@testing-library/react";

vi.mock("next/navigation", () => ({ useParams: () => ({ experienceId: "e1" }) }));
vi.mock("next/link", () => ({
  default: ({ href, children }: { href: string; children: React.ReactNode }) => (
    <a href={href}>{children}</a>
  ),
}));
const checkIn = vi.fn();
vi.mock("@/lib/api", () => ({ checkIn: (...a: unknown[]) => checkIn(...a) }));

import ExperienceLayout from "./layout";

const here = { member: true, removed: false, left_out: false, host_id: "q" };

beforeEach(() => {
  vi.useFakeTimers({ shouldAdvanceTime: true });
  localStorage.clear();
  localStorage.setItem("game_pid_e1", "q");
  checkIn.mockReset();
  checkIn.mockResolvedValue(here);
});
afterEach(() => {
  cleanup();
  vi.useRealTimers();
});

describe("game presence", () => {
  it("checks in straight away and then every ten seconds", async () => {
    render(<ExperienceLayout><p>the game</p></ExperienceLayout>);
    await waitFor(() => expect(checkIn).toHaveBeenCalledWith("e1", "q"));
    expect(screen.getByText("the game")).toBeTruthy();
    await act(async () => {
      vi.advanceTimersByTime(10_000);
    });
    expect(checkIn).toHaveBeenCalledTimes(2);
  });

  it("does nothing for a device that never joined", async () => {
    localStorage.clear();
    render(<ExperienceLayout><p>the game</p></ExperienceLayout>);
    await act(async () => {
      vi.advanceTimersByTime(30_000);
    });
    expect(checkIn).not.toHaveBeenCalled();
    expect(screen.getByText("the game")).toBeTruthy();
  });

  it("tells someone the host removed them", async () => {
    checkIn.mockResolvedValue({ member: false, removed: true, left_out: false, host_id: null });
    render(<ExperienceLayout><p>the game</p></ExperienceLayout>);
    await screen.findByText("You were removed from this game");
    expect(screen.queryByText("the game")).toBeNull();
    expect(screen.getByText("Back to games").getAttribute("href")).toBe("/games");
  });

  it("tells someone the game started without them", async () => {
    checkIn.mockResolvedValue({ member: true, removed: false, left_out: true, host_id: "x" });
    render(<ExperienceLayout><p>the game</p></ExperienceLayout>);
    await screen.findByText("This game started without you");
  });

  it("keeps the game on screen through a failed check-in", async () => {
    checkIn.mockRejectedValue(new Error("offline"));
    render(<ExperienceLayout><p>the game</p></ExperienceLayout>);
    await waitFor(() => expect(checkIn).toHaveBeenCalled());
    expect(screen.getByText("the game")).toBeTruthy();
  });
});
