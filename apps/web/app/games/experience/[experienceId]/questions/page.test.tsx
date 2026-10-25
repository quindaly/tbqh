// @vitest-environment jsdom
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent, waitFor, cleanup } from "@testing-library/react";

const push = vi.fn();
vi.mock("next/navigation", () => ({
  useParams: () => ({ experienceId: "e1" }),
  useRouter: () => ({ push }),
}));
const getGamePrompts = vi.fn();
const submitGameAnswer = vi.fn();
const getAnswerProgress = vi.fn();
const startWithFinished = vi.fn();
vi.mock("@/lib/api", () => {
  class ApiError extends Error {
    status: number;
    constructor(m: string, s: number) {
      super(m);
      this.status = s;
    }
  }
  return {
    ApiError,
    getGamePrompts: (...a: unknown[]) => getGamePrompts(...a),
    submitGameAnswer: (...a: unknown[]) => submitGameAnswer(...a),
    getAnswerProgress: (...a: unknown[]) => getAnswerProgress(...a),
    startWithFinished: (...a: unknown[]) => startWithFinished(...a),
    getGameState: vi.fn().mockResolvedValue({ game_state: "question_collection" }),
  };
});

import QuestionsPage from "./page";

const prompts = (answered: boolean[]) =>
  answered.map((a, i) => ({ id: `p${i}`, prompt_text: `Question ${i + 1}?`, answered: a }));

beforeEach(() => {
  localStorage.setItem("game_pid_e1", "q");
  push.mockClear();
  getGamePrompts.mockReset();
  submitGameAnswer.mockReset();
  getAnswerProgress.mockReset();
  getAnswerProgress.mockResolvedValue({ players: [], total_questions: 2, can_start_now: false, finished_count: 0, min_players: 3, game_state: "question_collection" });
  startWithFinished.mockReset();
});
afterEach(cleanup);

describe("Who Knows Who questions", () => {
  it("resumes at the first unanswered question after a reload", async () => {
    getGamePrompts.mockResolvedValue({ prompts: prompts([true, true, false, false]) });
    render(<QuestionsPage />);
    await screen.findByText("Question 3?");
    expect(getGamePrompts).toHaveBeenCalledWith("e1", "q");
    expect(screen.getByText("3 of 4")).toBeTruthy();
  });

  it("shows the waiting screen if everything is already answered", async () => {
    getGamePrompts.mockResolvedValue({ prompts: prompts([true, true]) });
    render(<QuestionsPage />);
    await screen.findByText("All done");
  });

  it("moves on if a question was already answered elsewhere", async () => {
    const { ApiError } = await import("@/lib/api");
    getGamePrompts.mockResolvedValue({ prompts: prompts([false, false]) });
    submitGameAnswer.mockRejectedValue(new ApiError("Already answered this prompt", 409));
    render(<QuestionsPage />);
    fireEvent.change(await screen.findByLabelText("Your answer"), { target: { value: "pizza" } });
    fireEvent.click(screen.getByText("Next"));
    await screen.findByText("Question 2?");
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("goes to play when the last answer completes the game", async () => {
    getGamePrompts.mockResolvedValue({ prompts: prompts([true, false]) });
    submitGameAnswer.mockResolvedValue({ ok: true, all_submitted: true });
    render(<QuestionsPage />);
    fireEvent.change(await screen.findByLabelText("Your answer"), { target: { value: "pizza" } });
    fireEvent.click(screen.getByText("Finish"));
    await waitFor(() => expect(push).toHaveBeenCalledWith("/games/experience/e1/play"));
  });

  describe("waiting for the others", () => {
    const progress = (canStart: boolean) => ({
      game_state: "question_collection",
      total_questions: 10,
      finished_count: 3,
      min_players: 3,
      can_start_now: canStart,
      players: [
        { id: "q", display_name: "Quin", answered: 10, finished: true, away: false },
        { id: "b", display_name: "Bea", answered: 10, finished: true, away: false },
        { id: "c", display_name: "Cal", answered: 10, finished: true, away: false },
        { id: "d", display_name: "Dee", answered: 4, finished: false, away: true },
      ],
    });

    it("shows who has finished", async () => {
      getGamePrompts.mockResolvedValue({ prompts: prompts([true, true]) });
      getAnswerProgress.mockResolvedValue(progress(false));
      render(<QuestionsPage />);
      await screen.findByText("4 of 10 · away");
      expect(screen.getAllByText("Done")).toHaveLength(3);
      expect(screen.queryByText(/Start with the/)).toBeNull();
    });

    it("lets the host start with whoever has finished", async () => {
      getGamePrompts.mockResolvedValue({ prompts: prompts([true, true]) });
      getAnswerProgress.mockResolvedValue(progress(true));
      startWithFinished.mockResolvedValue({ ok: true, players: 3, left_out: 1 });
      render(<QuestionsPage />);
      fireEvent.click(await screen.findByText("Start with the 3 who have finished"));
      await waitFor(() => expect(startWithFinished).toHaveBeenCalledWith("e1", "q"));
      await waitFor(() => expect(push).toHaveBeenCalledWith("/games/experience/e1/play"));
    });

    it("names who would be left out", async () => {
      getGamePrompts.mockResolvedValue({ prompts: prompts([true, true]) });
      getAnswerProgress.mockResolvedValue(progress(true));
      render(<QuestionsPage />);
      await screen.findByText(/Dee won't be in this game/);
    });
  });
});
