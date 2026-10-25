// @vitest-environment jsdom
import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";

vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn() }) }));
const listGames = vi.fn();
vi.mock("@/lib/api", () => ({ listGames: (...a: unknown[]) => listGames(...a) }));

import GamesPage from "./page";

describe("games list", () => {
  it("shows a retry when loading fails, then recovers", async () => {
    listGames.mockRejectedValueOnce(new Error("offline"));
    listGames.mockResolvedValueOnce({
      games: [{ id: "1", slug: "x", display_name: "Hot Seat", description: "d", status: "active" }],
    });
    render(<GamesPage />);
    const retry = await screen.findByText("Try again");
    fireEvent.click(retry);
    await waitFor(() => expect(screen.getByText("Hot Seat")).toBeTruthy());
  });
});
