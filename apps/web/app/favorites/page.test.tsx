// @vitest-environment jsdom
import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";

const getFavorites = vi.fn();
vi.mock("@/lib/api", () => ({ getFavorites: (...a: unknown[]) => getFavorites(...a) }));

import FavoritesPage from "./page";

describe("favorites", () => {
  it("shows a retry when loading fails instead of an empty list", async () => {
    getFavorites.mockRejectedValueOnce(new Error("Can't reach the server."));
    getFavorites.mockResolvedValueOnce({
      question_items: [{ question_item_id: "q", question_text: "Best trip?", liked_at: "2026-01-01" }],
    });
    render(<FavoritesPage />);
    expect(await screen.findByText("Can't reach the server.")).toBeTruthy();
    expect(screen.queryByText(/No favorites yet/)).toBeNull();
    fireEvent.click(screen.getByText("Try again"));
    await waitFor(() => expect(screen.getByText("Best trip?")).toBeTruthy());
  });
});
