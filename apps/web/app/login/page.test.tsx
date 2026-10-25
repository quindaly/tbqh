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
    expect(requestMagicLink).toHaveBeenCalledWith("me@example.com");
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
});
