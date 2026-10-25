// @vitest-environment jsdom
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent, waitFor, cleanup } from "@testing-library/react";

const push = vi.fn();
let search = "";
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push }),
  useSearchParams: () => new URLSearchParams(search),
}));
const create = vi.fn();
const join = vi.fn();
vi.mock("@/lib/api", () => ({
  createHWDYKGame: (...a: unknown[]) => create(...a),
  joinHWDYKGame: (...a: unknown[]) => join(...a),
}));

import Page from "./page";

afterEach(cleanup);

beforeEach(() => {
  push.mockClear();
  create.mockReset();
  join.mockReset();
  search = "";
  localStorage.clear();
});

describe("Hot Seat start flow", () => {
  it("walks name, style, length and creates with the choices", async () => {
    create.mockResolvedValue({ experience_instance_id: "e1", participant_id: "p1" });
    render(<Page />);
    fireEvent.click(screen.getByText("Start a game"));
    // name is required
    fireEvent.click(screen.getByText("Continue"));
    expect(screen.getByText(/Enter your name/)).toBeTruthy();
    fireEvent.change(screen.getByLabelText("Your name"), { target: { value: "Quin" } });
    fireEvent.click(screen.getByText("Continue"));
    fireEvent.click(screen.getByText("Friends write the wrong answers"));
    fireEvent.click(screen.getByText("Continue"));
    fireEvent.click(screen.getByText("7"));
    fireEvent.click(screen.getByText("Create game"));
    await waitFor(() => expect(push).toHaveBeenCalledWith("/games/experience/e1/hwdyk-lobby"));
    expect(create).toHaveBeenCalledWith("Quin", "party", 7);
    expect(localStorage.getItem("game_pid_e1")).toBe("p1");
    expect(localStorage.getItem("tbqh-display-name")).toBe("Quin");
  });

  it("defaults to AI answers and five questions", async () => {
    create.mockResolvedValue({ experience_instance_id: "e2", participant_id: "p2" });
    localStorage.setItem("tbqh-display-name", "Maya");
    render(<Page />);
    fireEvent.click(screen.getByText("Start a game"));
    await waitFor(() => expect((screen.getByLabelText("Your name") as HTMLInputElement).value).toBe("Maya"));
    fireEvent.click(screen.getByText("Continue"));
    fireEvent.click(screen.getByText("Continue"));
    fireEvent.click(screen.getByText("Create game"));
    await waitFor(() => expect(create).toHaveBeenCalledWith("Maya", "default", 5));
  });

  it("opens straight to join when the link has a code", () => {
    search = "code=ab12cd";
    render(<Page />);
    expect((screen.getByLabelText("Join code") as HTMLInputElement).value).toBe("AB12CD");
  });
});
