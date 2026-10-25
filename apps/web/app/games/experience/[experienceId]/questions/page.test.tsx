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
});
