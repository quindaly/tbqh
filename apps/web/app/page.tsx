"use client";

import { isSignedIn, useMe } from "./_components/Me";

export default function Home() {
  const { me } = useMe();
  const signedIn = isSignedIn(me);

  return (
    <div className="text-center space-y-8 py-16">
      <h1 className="text-4xl font-bold">tbqh</h1>
      {signedIn && (
        <p className="font-serif text-2xl" data-testid="welcome">
          {me?.name ? `Welcome back, ${me.name}` : "Welcome back"}
        </p>
      )}
      <p className="text-lg text-muted">
        Let’s get to know each other.
      </p>

      <div className="flex flex-col gap-4 items-center pt-4">
        <a
          href="/games"
          className="w-72 px-6 py-4 bg-btn text-btn-text text-lg rounded-md hover:opacity-90 transition inline-block font-medium"
        >
          Social Games
        </a>
        <a
          href="/questions"
          className="w-72 px-6 py-4 bg-btn text-btn-text text-lg rounded-md hover:opacity-90 transition inline-block font-medium"
        >
          Discussion Questions
        </a>
      </div>

      {!signedIn && (
        <div className="pt-4 border-t border-soft">
          <p className="text-sm text-muted mb-2">
            Want to save your favorites and build a profile?
          </p>
          <a
            href="/login"
            className="text-accent hover:underline text-sm font-medium"
          >
            Sign in with email →
          </a>
        </div>
      )}
    </div>
  );
}
