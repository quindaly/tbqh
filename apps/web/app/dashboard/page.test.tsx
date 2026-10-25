// @vitest-environment jsdom
import { describe, it, expect, vi, afterEach } from "vitest";
import { cleanup, render, screen, fireEvent, waitFor } from "@testing-library/react";

const push = vi.fn();
const router = { push };
vi.mock("next/navigation", () => ({ useRouter: () => router }));
vi.mock("next/link", () => ({ default: (p: any) => <a {...p} /> }));

const getMe = vi.fn();
vi.mock("@/lib/api", async () => {
  class ApiError extends Error {
    status: number;
    code?: string;
    constructor(message: string, status: number, code?: string) {
      super(message);
      this.status = status;
      this.code = code;
    }
  }
  return {
    ApiError,
    getMe: (...a: unknown[]) => getMe(...a),
    createGroup: vi.fn(),
    listPolicies: vi.fn(),
    createSession: vi.fn(),
  };
});

import { ApiError } from "@/lib/api";
import DashboardPage from "./page";

afterEach(() => {
  cleanup();
  push.mockReset();
  getMe.mockReset();
});

describe("dashboard", () => {
  it("sends you to login only when you are really signed out", async () => {
    getMe.mockRejectedValueOnce(new ApiError("Not authenticated", 401));
    render(<DashboardPage />);
    await waitFor(() => expect(push).toHaveBeenCalledWith("/login"));
  });

  it("shows a retry, not the login page, when the server is unreachable", async () => {
    getMe.mockRejectedValueOnce(new ApiError("Can't reach the server.", 0));
    getMe.mockResolvedValueOnce({ id: "1", email: "a@b.com" });
    render(<DashboardPage />);
    fireEvent.click(await screen.findByText("Try again"));
    await waitFor(() => expect(getMe).toHaveBeenCalledTimes(2));
    expect(push).not.toHaveBeenCalled();
    await waitFor(() => expect(screen.queryByText("Try again")).toBeNull());
  });
});
