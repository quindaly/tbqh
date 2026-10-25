// @vitest-environment jsdom
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent, waitFor, cleanup } from "@testing-library/react";

const push = vi.fn();
vi.mock("next/navigation", () => ({
  useParams: () => ({ id: "s1" }),
  useRouter: () => ({ push }),
}));

const getFollowups = vi.fn();
const answerFollowup = vi.fn();
const commitGroupProfile = vi.fn();
vi.mock("@/lib/api", () => ({
  getFollowups: (...a: unknown[]) => getFollowups(...a),
  answerFollowup: (...a: unknown[]) => answerFollowup(...a),
  commitGroupProfile: (...a: unknown[]) => commitGroupProfile(...a),
}));

import FollowupsPage from "./page";

const prompts = [
  { id: "p1", prompt_text: "What do you usually do?", options: ["Weekend get-togethers", "Mother's side", "Other (type your own)"] },
  { id: "p2", prompt_text: "How deep should we go?", options: ["Light", "Deep", "Other (type your own)"] },
];

beforeEach(() => {
  localStorage.clear();
  localStorage.setItem("tbqh_session_s1", JSON.stringify({ participantId: "me" }));
  getFollowups.mockResolvedValue({ prompts, provisional_group_profile_id: "prov1" });
  answerFollowup.mockResolvedValue({ ok: true });
  commitGroupProfile.mockResolvedValue({ group_profile_id: "gp1", version: 1 });
});
afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("follow-up questions", () => {
  it("only treats the real 'Other' choice as free text", async () => {
    render(<FollowupsPage />);
    fireEvent.click(await screen.findByText("Weekend get-togethers"));
    expect(screen.queryByLabelText("Your answer")).toBeNull();
    fireEvent.click(screen.getByText("Mother's side"));
    expect(screen.queryByLabelText("Your answer")).toBeNull();

    fireEvent.click(screen.getByText("Other (type your own)"));
    expect(screen.getByLabelText("Your answer")).toBeTruthy();
  });

  it("won't continue until an 'Other' answer has text", async () => {
    render(<FollowupsPage />);
    fireEvent.click(await screen.findByText("Other (type your own)"));
    const next = screen.getByRole("button", { name: "Next" }) as HTMLButtonElement;
    expect(next.disabled).toBe(true);

    fireEvent.change(screen.getByLabelText("Your answer"), { target: { value: "Road trips" } });
    expect(next.disabled).toBe(false);
    fireEvent.click(next);
    await waitFor(() =>
      expect(answerFollowup).toHaveBeenCalledWith("s1", "p1", "me", null, "Road trips")
    );
  });

  it("builds the profile from the latest description after the last question", async () => {
    render(<FollowupsPage />);
    fireEvent.click(await screen.findByText("Weekend get-togethers"));
    fireEvent.click(screen.getByRole("button", { name: "Next" }));
    fireEvent.click(await screen.findByText("Deep"));
    fireEvent.click(screen.getByRole("button", { name: "Get my questions" }));

    await waitFor(() => expect(commitGroupProfile).toHaveBeenCalledWith("s1", "prov1"));
    await waitFor(() => expect(push).toHaveBeenCalledWith("/session/s1/questions"));
    expect(JSON.parse(localStorage.getItem("tbqh_session_s1")!).groupProfileId).toBe("gp1");
  });

  it("lets you skip a question and go back", async () => {
    render(<FollowupsPage />);
    await screen.findByText("What do you usually do?");
    fireEvent.click(screen.getByText("Skip"));
    expect(await screen.findByText("How deep should we go?")).toBeTruthy();
    expect(answerFollowup).not.toHaveBeenCalled();
    fireEvent.click(screen.getByText("← Back"));
    expect(await screen.findByText("What do you usually do?")).toBeTruthy();
  });

  it("keeps the person on the question when saving fails", async () => {
    answerFollowup.mockRejectedValueOnce(new Error("Can't reach the server."));
    render(<FollowupsPage />);
    fireEvent.click(await screen.findByText("Weekend get-togethers"));
    fireEvent.click(screen.getByRole("button", { name: "Next" }));
    expect(await screen.findByText("Can't reach the server.")).toBeTruthy();
    expect(screen.getByText("What do you usually do?")).toBeTruthy();
  });
});
