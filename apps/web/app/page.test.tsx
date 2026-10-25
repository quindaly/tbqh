// @vitest-environment jsdom
import { describe, it, expect, vi, afterEach } from "vitest";
import { render, screen, cleanup } from "@testing-library/react";

let meState: { me: any; loaded: boolean } = { me: null, loaded: true };
vi.mock("./_components/Me", () => ({
  useMe: () => meState,
  isSignedIn: (me: any) => !!me && !me.is_guest,
}));

import Home from "./page";

afterEach(cleanup);

describe("home page welcome", () => {
  it("greets a signed-in person by name", () => {
    meState = { me: { id: "u", email: "q@x.com", name: "Quin" }, loaded: true };
    render(<Home />);
    expect(screen.getByTestId("welcome").textContent).toBe("Welcome back, Quin");
    expect(screen.queryByText(/Sign in with email/)).toBeNull();
  });

  it("just says welcome back when they gave no name", () => {
    meState = { me: { id: "u", email: "q@x.com", name: null }, loaded: true };
    render(<Home />);
    expect(screen.getByTestId("welcome").textContent).toBe("Welcome back");
  });

  it("never shows an email address", () => {
    meState = { me: { id: "u", email: "private@x.com", name: null }, loaded: true };
    render(<Home />);
    expect(document.body.textContent).not.toContain("private@x.com");
  });

  it("says nothing special to a visitor and offers sign in", () => {
    meState = { me: null, loaded: true };
    render(<Home />);
    expect(screen.queryByTestId("welcome")).toBeNull();
    expect(screen.getByText(/Sign in with email/)).toBeTruthy();
    expect(screen.getByText("Let’s get to know each other.")).toBeTruthy();
  });

  it("treats a guest like a visitor", () => {
    meState = { me: { id: "g", email: "guest-1@guest.local", is_guest: true }, loaded: true };
    render(<Home />);
    expect(screen.queryByTestId("welcome")).toBeNull();
    expect(screen.getByText(/Sign in with email/)).toBeTruthy();
  });
});
