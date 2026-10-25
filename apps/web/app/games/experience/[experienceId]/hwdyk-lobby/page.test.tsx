// @vitest-environment jsdom
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent, waitFor, cleanup } from "@testing-library/react";

vi.mock("next/navigation", () => ({
  useParams: () => ({ experienceId: "e1" }),
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
}));
const getHWDYKLobby = vi.fn();
const removePlayer = vi.fn();
vi.mock("@/lib/api", () => {
  class ApiError extends Error {
    status = 0;
  }
  return {
    ApiError,
    getHWDYKLobby: (...a: unknown[]) => getHWDYKLobby(...a),
    removePlayer: (...a: unknown[]) => removePlayer(...a),
    returnToHWDYKLobby: vi.fn(),
    selectMainPerson: vi.fn(),
    startHWDYKSetup: vi.fn(),
    startLiveGame: vi.fn(),
  };
});

import LobbyPage from "./page";

const lobby = (over = {}) => ({
  experience_id: "e1",
  game_state: "lobby",
  state_version: 1,
  phase: null,
  join_code: "ABC123",
  share_url: "https://x/games/the-hot-seat?code=ABC123",
  host_id: "q",
  main_person_participant_id: null,
  is_replay: false,
  absent_participants: [],
  participants: [
    { id: "q", display_name: "Quin", role: "host", away: false },
    { id: "b", display_name: "Bea", role: "guest", away: true },
    { id: "c", display_name: "Cal", role: "guest", away: false },
  ],
  ...over,
});

beforeEach(() => {
  localStorage.clear();
  localStorage.setItem("game_pid_e1", "q");
  getHWDYKLobby.mockReset();
  removePlayer.mockReset();
});
afterEach(cleanup);

describe("Hot Seat lobby: players who left", () => {
  it("lets the host remove someone who is away, and only them", async () => {
    getHWDYKLobby.mockResolvedValue(lobby());
    render(<LobbyPage />);
    await screen.findByText("Away");
    expect(screen.getAllByText("Remove")).toHaveLength(1);
    expect(screen.getByLabelText("Remove Bea")).toBeTruthy();
  });

  it("removes them and refreshes the lobby", async () => {
    getHWDYKLobby.mockResolvedValueOnce(lobby());
    getHWDYKLobby.mockResolvedValue(
      lobby({
        state_version: 2,
        participants: [
          { id: "q", display_name: "Quin", role: "host", away: false },
          { id: "c", display_name: "Cal", role: "guest", away: false },
        ],
      })
    );
    removePlayer.mockResolvedValue({});
    render(<LobbyPage />);
    fireEvent.click(await screen.findByLabelText("Remove Bea"));
    await waitFor(() => expect(removePlayer).toHaveBeenCalledWith("e1", "q", "b"));
    await waitFor(() => expect(screen.queryByText("Bea")).toBeNull());
  });

  it("does not offer removal to players who are not the host", async () => {
    localStorage.setItem("game_pid_e1", "c");
    getHWDYKLobby.mockResolvedValue(lobby());
    render(<LobbyPage />);
    await screen.findByText("Away");
    expect(screen.queryByText("Remove")).toBeNull();
  });

  it("does not offer removal once setup has started", async () => {
    getHWDYKLobby.mockResolvedValue(lobby({ game_state: "main_person_answering" }));
    render(<LobbyPage />);
    await screen.findByText("Away");
    expect(screen.queryByText("Remove")).toBeNull();
  });

  it("shows the host as whoever holds the controls now", async () => {
    getHWDYKLobby.mockResolvedValue(
      lobby({
        host_id: "c",
        participants: [
          { id: "q", display_name: "Quin", role: "guest", away: true },
          { id: "c", display_name: "Cal", role: "host", away: false },
        ],
      })
    );
    localStorage.setItem("game_pid_e1", "c");
    render(<LobbyPage />);
    await screen.findByText("Host");
    expect(screen.getByText("Away")).toBeTruthy();
  });
});
