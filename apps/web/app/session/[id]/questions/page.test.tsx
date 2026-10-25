// @vitest-environment jsdom
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent, waitFor, cleanup } from "@testing-library/react";

const push = vi.fn();
vi.mock("next/navigation", () => ({
  useParams: () => ({ id: "s1" }),
  useRouter: () => ({ push }),
}));

const createExperience = vi.fn();
const getRecommendations = vi.fn();
const getMoreRecommendations = vi.fn();
const listExperienceItems = vi.fn();
const submitFeedback = vi.fn();
vi.mock("@/lib/api", () => ({
  createExperience: (...a: unknown[]) => createExperience(...a),
  getRecommendations: (...a: unknown[]) => getRecommendations(...a),
  getMoreRecommendations: (...a: unknown[]) => getMoreRecommendations(...a),
  listExperienceItems: (...a: unknown[]) => listExperienceItems(...a),
  submitFeedback: (...a: unknown[]) => submitFeedback(...a),
}));

import QuestionsPage from "./page";

const item = (n: number, feedback: string | null = null) => ({
  id: `c${n}`,
  content_type: "discussion_question",
  text: `Question ${n}?`,
  metadata: {},
  feedback,
});

function remember(extra: Record<string, string> = {}) {
  localStorage.setItem(
    "tbqh_session_s1",
    JSON.stringify({ participantId: "me", groupProfileId: "gp1", ...extra })
  );
}

beforeEach(() => {
  localStorage.clear();
  createExperience.mockResolvedValue({ experience_instance_id: "e1" });
  submitFeedback.mockResolvedValue({ ok: true });
});
afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("discussion questions", () => {
  it("sends people back to describe their group when there is no profile", async () => {
    render(<QuestionsPage />);
    expect(await screen.findByText(/Tell us about your group first/)).toBeTruthy();
    expect(createExperience).not.toHaveBeenCalled();
  });

  it("explains when nothing fits instead of showing a blank card", async () => {
    remember();
    getRecommendations.mockResolvedValue({ content_items: [], exhausted: true });
    render(<QuestionsPage />);
    expect(await screen.findByText("No questions to show yet")).toBeTruthy();
  });

  it("rates a question and moves on", async () => {
    remember();
    getRecommendations.mockResolvedValue({ content_items: [item(1), item(2)] });
    render(<QuestionsPage />);
    expect(await screen.findByText("Question 1?")).toBeTruthy();
    fireEvent.click(screen.getByText("Not for us"));
    await waitFor(() => expect(submitFeedback).toHaveBeenCalledWith("c1", "e1", "me", "dislike"));
    expect(await screen.findByText("Question 2?")).toBeTruthy();
    expect(JSON.parse(localStorage.getItem("tbqh_session_s1")!).experienceId).toBe("e1");
  });

  it("picks up where it left off after a reload without using up new questions", async () => {
    remember({ experienceId: "e1" });
    listExperienceItems.mockResolvedValue({
      content_items: [item(1, "like"), item(2, "skip"), item(3), item(4)],
    });
    render(<QuestionsPage />);
    expect(await screen.findByText("Question 3?")).toBeTruthy();
    expect(createExperience).not.toHaveBeenCalled();
    expect(getRecommendations).not.toHaveBeenCalled();
  });

  it("says so when the group has seen every question", async () => {
    remember();
    getRecommendations.mockResolvedValue({ content_items: [item(1)] });
    getMoreRecommendations.mockResolvedValue({ content_items: [], exhausted: true });
    render(<QuestionsPage />);
    fireEvent.click(await screen.findByText("Love it"));
    fireEvent.click(await screen.findByText("Get 10 more"));
    expect(await screen.findByText(/every question we have/)).toBeTruthy();
  });

  it("keeps the current question when saving a rating fails", async () => {
    remember();
    getRecommendations.mockResolvedValue({ content_items: [item(1), item(2)] });
    submitFeedback.mockRejectedValueOnce(new Error("Can't reach the server."));
    render(<QuestionsPage />);
    fireEvent.click(await screen.findByText("Love it"));
    expect(await screen.findByText("Can't reach the server.")).toBeTruthy();
    expect(screen.getByText("Question 1?")).toBeTruthy();
  });
});
