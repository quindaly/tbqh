// @vitest-environment jsdom
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent, waitFor, cleanup } from "@testing-library/react";

vi.mock("next/navigation", () => ({
  useParams: () => ({ experienceId: "e1" }),
  useRouter: () => ({ push: vi.fn() }),
}));
const getGameState = vi.fn();
const submitGuess = vi.fn();
vi.mock("@/lib/api", async () => {
  class ApiError extends Error {
    status: number;
    constructor(m: string, s: number) {
      super(m);
      this.status = s;
    }
  }
  return {
    ApiError,
    getGameState: (...a: unknown[]) => getGameState(...a),
    submitGuess: (...a: unknown[]) => submitGuess(...a),
    revealRound: vi.fn(),
    advanceRound: vi.fn(),
  };
});

import PlayPage from "./page";

const people = [
  { id: "h", display_name: "Maya", role: "host" },
  { id: "d", display_name: "Dev", role: "guest" },
  { id: "q", display_name: "Quin", role: "guest" },
];
const round = (over = {}) => ({
  round_id: "r1",
  round_number: 1,
  status: "active",
  question_text: "Guilty pleasure?",
  answer_text: "Reality TV",
  is_yours: false,
  you_guessed: false,
  guessed_count: 0,
  guesser_count: 2,
  ...over,
});
const state = (r: object) => ({
  experience_id: "e1",
  experience_type: "who_knows_who",
  game_state: "round_active",
  current_round: 1,
  max_rounds: 5,
  participants: people,
  round: r,
});

beforeEach(() => {
  localStorage.setItem("game_pid_e1", "q");
  getGameState.mockReset();
  submitGuess.mockReset();
});
afterEach(cleanup);

describe("Who Knows Who play screen", () => {
  it("never offers the player themselves as a guess", async () => {
    getGameState.mockResolvedValue(state(round()));
    render(<PlayPage />);
    await screen.findByText("Who wrote this?");
    expect(screen.getByText("Maya")).toBeTruthy();
    expect(screen.getByText("Dev")).toBeTruthy();
    expect(screen.queryByText("Quin")).toBeNull();
  });

  it("asks the server about the viewer, not just the game", async () => {
    getGameState.mockResolvedValue(state(round()));
    render(<PlayPage />);
    await screen.findByText("Who wrote this?");
    expect(getGameState).toHaveBeenCalledWith("e1", "q");
  });

  it("keeps the guess buttons away after guessing, even if the next poll is stale", async () => {
    getGameState.mockResolvedValue(state(round()));
    submitGuess.mockResolvedValue({ ok: true });
    render(<PlayPage />);
    fireEvent.click(await screen.findByText("Dev"));
    await screen.findByText(/Guess locked in/);
    // The server replies before it has recorded the guess: still locked.
    getGameState.mockResolvedValue(state(round()));
    await waitFor(() => expect(getGameState.mock.calls.length).toBeGreaterThan(1));
    expect(screen.queryByText("Who wrote this?")).toBeNull();
  });

  it("shows a reload straight to the locked state", async () => {
    getGameState.mockResolvedValue(state(round({ you_guessed: true, guessed_count: 1 })));
    render(<PlayPage />);
    await screen.findByText(/Guess locked in/);
    expect(screen.getByText("1 of 2 guessed")).toBeTruthy();
  });

  it("tells the owner it is their answer and offers no guesses", async () => {
    getGameState.mockResolvedValue(state(round({ is_yours: true })));
    render(<PlayPage />);
    await screen.findByText(/based on your answer/);
    expect(screen.queryByText("Who wrote this?")).toBeNull();
  });

  it("lets a non-host reveal only once everyone has guessed", async () => {
    getGameState.mockResolvedValue(state(round({ guessed_count: 1 })));
    const { unmount } = render(<PlayPage />);
    await screen.findByText("Who wrote this?");
    expect(screen.queryByText(/Reveal/)).toBeNull();
    unmount();
    getGameState.mockResolvedValue(state(round({ guessed_count: 2 })));
    render(<PlayPage />);
    await screen.findByText(/Everyone has guessed/);
  });
});
