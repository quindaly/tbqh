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
let meState: { me: any; loaded: boolean } = {
  me: { id: "u1", email: "q@example.com", is_guest: false },
  loaded: true,
};
vi.mock("../../../_components/Me", () => ({
  useMe: () => meState,
  isSignedIn: (me: any) => !!me && !me.is_guest,
}));
vi.mock("@/lib/api", () => ({
  ApiError: class ApiError extends Error {
    status: number;
    constructor(m: string, s: number) {
      super(m);
      this.status = s;
    }
  },
  createExperience: (...a: unknown[]) => createExperience(...a),
  getRecommendations: (...a: unknown[]) => getRecommendations(...a),
  getMoreRecommendations: (...a: unknown[]) => getMoreRecommendations(...a),
  listExperienceItems: (...a: unknown[]) => listExperienceItems(...a),
  submitFeedback: (...a: unknown[]) => submitFeedback(...a),
}));

import QuestionsPage from "./page";
import { ApiError } from "@/lib/api";

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
  meState = { me: { id: "u1", email: "q@example.com", is_guest: false }, loaded: true };
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

  describe("feedback needs an account", () => {
    const ready = () => {
      remember({ experienceId: "e1" });
      listExperienceItems.mockResolvedValue({ content_items: [item(1), item(2)] });
    };

    it("asks a guest to sign in when they tap Love it, and sends nothing", async () => {
      meState = { me: { id: "g", email: "guest-1@guest.local", is_guest: true }, loaded: true };
      ready();
      render(<QuestionsPage />);
      fireEvent.click(await screen.findByText("Love it"));
      expect(await screen.findByText("Sign in to leave feedback")).toBeTruthy();
      expect(submitFeedback).not.toHaveBeenCalled();
      expect(screen.getByText("Question 1?")).toBeTruthy(); // still on the same question
    });

    it("does the same for Not for us when nobody is signed in", async () => {
      meState = { me: null, loaded: true };
      ready();
      render(<QuestionsPage />);
      fireEvent.click(await screen.findByText("Not for us"));
      await screen.findByText("Sign in to leave feedback");
      expect(submitFeedback).not.toHaveBeenCalled();
    });

    it("lets a guest skip without an account", async () => {
      meState = { me: null, loaded: true };
      ready();
      render(<QuestionsPage />);
      fireEvent.click(await screen.findByText("Skip"));
      await waitFor(() => expect(submitFeedback).toHaveBeenCalledWith("c1", "e1", "me", "skip"));
      expect(screen.queryByText("Sign in to leave feedback")).toBeNull();
    });

    it("sends them to sign in and back to this same page", async () => {
      meState = { me: null, loaded: true };
      ready();
      render(<QuestionsPage />);
      fireEvent.click(await screen.findByText("Love it"));
      fireEvent.click(await screen.findByText("Sign in with email"));
      expect(push).toHaveBeenCalledWith(
        `/login?next=${encodeURIComponent("/session/s1/questions")}`
      );
    });

    it("can be dismissed", async () => {
      meState = { me: null, loaded: true };
      ready();
      render(<QuestionsPage />);
      fireEvent.click(await screen.findByText("Love it"));
      fireEvent.click(await screen.findByText("Not now"));
      expect(screen.queryByText("Sign in to leave feedback")).toBeNull();
    });

    it("lets a signed-in person rate, and follows the participant the server uses", async () => {
      ready();
      submitFeedback.mockResolvedValue({ ok: true, participant_id: "me2" });
      render(<QuestionsPage />);
      fireEvent.click(await screen.findByText("Love it"));
      await waitFor(() => expect(submitFeedback).toHaveBeenCalledWith("c1", "e1", "me", "like"));
      await screen.findByText("Question 2?");
      expect(JSON.parse(localStorage.getItem("tbqh_session_s1")!).participantId).toBe("me2");
      fireEvent.click(await screen.findByText("Love it"));
      await waitFor(() => expect(submitFeedback).toHaveBeenLastCalledWith("c2", "e1", "me2", "like"));
    });

    it("asks to sign in if the server says the session has ended", async () => {
      meState = { me: { id: "u1", email: "q@example.com", is_guest: false }, loaded: false };
      ready();
      submitFeedback.mockRejectedValue(new ApiError("Sign in to leave feedback.", 401));
      render(<QuestionsPage />);
      fireEvent.click(await screen.findByText("Love it"));
      await screen.findByText("Sign in with email");
    });

    it("picks up where it left off when opened from a sign-in link in a new browser", async () => {
      const r = btoa(JSON.stringify({ participantId: "me", groupProfileId: "gp1", experienceId: "e1" }))
        .replace(/\+/g, "-")
        .replace(/\//g, "_")
        .replace(/=+$/, "");
      window.history.pushState(null, "", `/session/s1/questions?r=${r}`);
      listExperienceItems.mockResolvedValue({ content_items: [item(1, "skip"), item(2)] });
      render(<QuestionsPage />);
      await screen.findByText("Question 2?");
      expect(listExperienceItems).toHaveBeenCalledWith("e1", "me");
      expect(window.location.search).toBe("");
    });
  });
});
