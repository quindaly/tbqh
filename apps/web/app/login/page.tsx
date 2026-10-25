"use client";

import { Suspense, useState } from "react";
import { useSearchParams } from "next/navigation";
import { requestMagicLink } from "@/lib/api";
import { Heading, PrimaryButton, SecondaryButton } from "../_components/ui";

export default function LoginPage() {
  return (
    <Suspense fallback={null}>
      <LoginForm />
    </Suspense>
  );
}

function LoginForm() {
  const searchParams = useSearchParams();
  const linkProblem = searchParams.get("error") === "expired";

  const [email, setEmail] = useState("");
  const [sent, setSent] = useState(false);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const send = async () => {
    setError("");
    setLoading(true);
    try {
      await requestMagicLink(email.trim());
      setSent(true);
    } catch (err: any) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  if (sent) {
    return (
      <div className="max-w-md mx-auto flex flex-col gap-6 py-12">
        <Heading>Check your email</Heading>
        <p className="text-muted">
          We sent a sign-in link to <span className="text-ink">{email.trim()}</span>. It works for
          10 minutes. If you don&apos;t see it, check your spam folder.
        </p>
        {process.env.NODE_ENV !== "production" && (
          <p className="text-sm text-muted">
            Local development: the link is printed in the API server console.
          </p>
        )}
        {error && (
          <p role="alert" className="text-red-500 text-sm">
            {error}
          </p>
        )}
        <div className="flex flex-col gap-3">
          <SecondaryButton onClick={send} disabled={loading}>
            {loading ? "Sending…" : "Send it again"}
          </SecondaryButton>
          <button
            onClick={() => {
              setSent(false);
              setError("");
            }}
            className="text-sm text-muted hover:underline"
          >
            Use a different email
          </button>
        </div>
      </div>
    );
  }

  return (
    <form
      className="max-w-md mx-auto flex flex-col gap-6 py-12"
      onSubmit={(e) => {
        e.preventDefault();
        void send();
      }}
    >
      <div className="flex flex-col gap-3">
        <Heading>Sign in</Heading>
        <p className="text-muted">
          Enter your email and we&apos;ll send you a link. No password needed.
        </p>
      </div>
      {linkProblem && (
        <p
          role="status"
          className="rounded-md border border-soft bg-surface px-3 py-2 text-sm"
        >
          That sign-in link has expired or was already used. Enter your email for a new one.
        </p>
      )}
      <input
        type="email"
        autoComplete="email"
        aria-label="Email"
        placeholder="you@example.com"
        value={email}
        onChange={(e) => setEmail(e.target.value)}
        required
        className="w-full px-4 min-h-[56px] border border-line rounded-md bg-surface text-[17px]"
      />
      {error && (
        <p role="alert" className="text-red-500 text-sm">
          {error}
        </p>
      )}
      <PrimaryButton type="submit" disabled={loading}>
        {loading ? "Sending…" : "Email me a link"}
      </PrimaryButton>
    </form>
  );
}
