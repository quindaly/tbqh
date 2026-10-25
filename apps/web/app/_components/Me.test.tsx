// @vitest-environment jsdom
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent, waitFor, cleanup } from "@testing-library/react";

const getMe = vi.fn();
const updateMyName = vi.fn();
vi.mock("@/lib/api", () => ({
  getMe: (...a: unknown[]) => getMe(...a),
  updateMyName: (...a: unknown[]) => updateMyName(...a),
}));

import { MeProvider, NamePrompt, useMe } from "./Me";

function Who() {
  const { me, loaded } = useMe();
  return <p>{loaded ? (me ? `hi ${me.name ?? "nobody"}` : "signed out") : "loading"}</p>;
}

const app = () =>
  render(
    <MeProvider>
      <Who />
      <NamePrompt />
    </MeProvider>
  );

beforeEach(() => {
  getMe.mockReset();
  updateMyName.mockReset();
});
afterEach(cleanup);

describe("first sign-in name prompt", () => {
  it("asks a brand new account for a name", async () => {
    getMe.mockResolvedValue({ id: "u", email: "a@b.c", is_guest: false, name: null, needs_name: true });
    app();
    await screen.findByText("What should we call you?");
  });

  it("saves the name and says hello with it", async () => {
    getMe.mockResolvedValue({ id: "u", email: "a@b.c", is_guest: false, name: null, needs_name: true });
    updateMyName.mockResolvedValue({ ok: true, name: "Quin" });
    app();
    fireEvent.change(await screen.findByLabelText("Your name"), { target: { value: "  Quin " } });
    fireEvent.click(screen.getByText("Save"));
    await waitFor(() => expect(updateMyName).toHaveBeenCalledWith({ name: "Quin" }));
    await screen.findByText("hi Quin");
    expect(screen.queryByText("What should we call you?")).toBeNull();
  });

  it("does not let you save a blank name", async () => {
    getMe.mockResolvedValue({ id: "u", email: "a@b.c", needs_name: true });
    app();
    await screen.findByText("What should we call you?");
    expect((screen.getByText("Save") as HTMLButtonElement).disabled).toBe(true);
  });

  it("'Not now' stops the asking and leaves no name", async () => {
    getMe.mockResolvedValue({ id: "u", email: "a@b.c", is_guest: false, name: null, needs_name: true });
    updateMyName.mockResolvedValue({ ok: true, name: null });
    app();
    fireEvent.click(await screen.findByText("Not now"));
    await waitFor(() => expect(updateMyName).toHaveBeenCalledWith({ skip: true }));
    await waitFor(() => expect(screen.queryByText("What should we call you?")).toBeNull());
    await screen.findByText("hi nobody");
  });

  it("shows an error and keeps the prompt if saving fails", async () => {
    getMe.mockResolvedValue({ id: "u", email: "a@b.c", needs_name: true });
    updateMyName.mockRejectedValue(new Error("Names can be up to 40 characters."));
    app();
    fireEvent.change(await screen.findByLabelText("Your name"), { target: { value: "Q" } });
    fireEvent.click(screen.getByText("Save"));
    await screen.findByText("Names can be up to 40 characters.");
    expect(screen.getByText("What should we call you?")).toBeTruthy();
  });

  it.each([
    ["a returning account", { id: "u", email: "a@b.c", name: "Quin", needs_name: false }],
    ["a guest", { id: "g", email: "guest-1@guest.local", is_guest: true, needs_name: false }],
  ])("does not ask %s", async (_label, me) => {
    getMe.mockResolvedValue(me);
    app();
    await waitFor(() => expect(screen.queryByText("loading")).toBeNull());
    expect(screen.queryByText("What should we call you?")).toBeNull();
  });

  it("does not ask someone who is signed out", async () => {
    getMe.mockRejectedValue(new Error("401"));
    app();
    await screen.findByText("signed out");
    expect(screen.queryByText("What should we call you?")).toBeNull();
  });
});
