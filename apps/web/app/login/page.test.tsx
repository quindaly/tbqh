// @vitest-environment jsdom
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent, waitFor, cleanup } from "@testing-library/react";

let search = "";
vi.mock("next/navigation", () => ({ useSearchParams: () => new URLSearchParams(search) }));
const requestMagicLink = vi.fn();
vi.mock("@/lib/api", () => ({ requestMagicLink: (...a: unknown[]) => requestMagicLink(...a) }));

import LoginPage from "./page";

beforeEach(() => {
  search = "";
  requestMagicLink.mockReset();
});
afterEach(cleanup);

describe("Sign in", () => {
  it("sends the link and says where it went", async () => {
    requestMagicLink.mockResolvedValue({ ok: true });
    render(<LoginPage />);
    fireEvent.change(screen.getByLabelText("Email"), { target: { value: " me@example.com " } });
    fireEvent.click(screen.getByText("Email me a link"));
    await screen.findByText("Check your email");
    expect(requestMagicLink).toHaveBeenCalledWith("me@example.com", null);
    expect(screen.getByText("me@example.com")).toBeTruthy();
  });

  it("shows the server's reason when sending fails", async () => {
    requestMagicLink.mockRejectedValue(new Error("We couldn't send the email right now."));
    render(<LoginPage />);
    fireEvent.change(screen.getByLabelText("Email"), { target: { value: "me@example.com" } });
    fireEvent.click(screen.getByText("Email me a link"));
    await screen.findByText(/couldn't send/);
    expect(screen.queryByText("Check your email")).toBeNull();
  });

  it("can send again and switch to another address", async () => {
    requestMagicLink.mockResolvedValue({ ok: true });
    render(<LoginPage />);
    fireEvent.change(screen.getByLabelText("Email"), { target: { value: "me@example.com" } });
    fireEvent.click(screen.getByText("Email me a link"));
    fireEvent.click(await screen.findByText("Send it again"));
    await waitFor(() => expect(requestMagicLink).toHaveBeenCalledTimes(2));
    fireEvent.click(screen.getByText("Use a different email"));
    expect(screen.getByLabelText("Email")).toBeTruthy();
  });

  it("explains an expired or already used link", () => {
    search = "error=expired";
    render(<LoginPage />);
    expect(screen.getByText(/expired or was already used/)).toBeTruthy();
  });

  describe("coming back to where you were", () => {
    const send = async () => {
      requestMagicLink.mockResolvedValue({ ok: true });
      render(<LoginPage />);
      fireEvent.change(screen.getByLabelText("Email"), { target: { value: "me@example.com" } });
      fireEvent.click(screen.getByText("Email me a link"));
      await screen.findByText("Check your email");
    };

    it("asks for the home page when you just chose Sign In", async () => {
      await send();
      expect(requestMagicLink).toHaveBeenCalledWith("me@example.com", null);
    });

    it("asks to come back to the game you were in, with what this browser remembers", async () => {
      localStorage.clear();
      localStorage.setItem(
        "tbqh_session_s1",
        JSON.stringify({ participantId: "p1", groupProfileId: "gp1", experienceId: "e1" })
      );
      search = `next=${encodeURIComponent("/session/s1/questions")}`;
      await send();
      const [, next] = requestMagicLink.mock.calls[0];
      expect(next.startsWith("/session/s1/questions?r=")).toBe(true);
      const r = next.split("r=")[1].replace(/-/g, "+").replace(/_/g, "/");
      expect(JSON.parse(atob(r))).toEqual({ participantId: "p1", groupProfileId: "gp1", experienceId: "e1" });
    });

    it("comes back to a plain path when nothing is remembered", async () => {
      localStorage.clear();
      search = `next=${encodeURIComponent("/games/the-hot-seat?code=ABC123")}`;
      await send();
      expect(requestMagicLink).toHaveBeenCalledWith("me@example.com", "/games/the-hot-seat?code=ABC123");
    });

    it.each(["https://evil.example", "//evil.example", "javascript:alert(1)"])(
      "ignores a destination that leaves the site: %s",
      async (bad) => {
        search = `next=${encodeURIComponent(bad)}`;
        await send();
        expect(requestMagicLink).toHaveBeenCalledWith("me@example.com", null);
      }
    );

    it("says the link works once", async () => {
      await send();
      expect(screen.getByText(/once, for 10 minutes/)).toBeTruthy();
    });
  });
});
