"use client";

import { useState } from "react";
import { requestMagicLink } from "@/lib/api";

export default function LoginPage() {
  const [email, setEmail] = useState("");
  const [sent, setSent] = useState(false);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      await requestMagicLink(email);
      setSent(true);
    } catch (err: any) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  if (sent) {
    return (
      <div className="text-center space-y-4 py-16">
        <h1 className="text-2xl font-bold">Check your email!</h1>
        <p className="text-gray-600 dark:text-gray-400">
          We sent a magic link to <strong>{email}</strong>.
        </p>
        <p className="text-sm text-gray-500">
          (In dev mode, check the API server console for the link.)
        </p>
      </div>
    );
  }

  return (
    <div className="max-w-md mx-auto space-y-6 py-16">
      <h1 className="text-2xl font-bold text-center">Sign In</h1>
      <form onSubmit={handleSubmit} className="space-y-4">
        <input
          type="email"
          placeholder="your@email.com"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          required
          className="w-full px-4 py-3 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-800 focus:ring-2 focus:ring-blue-500 outline-none"
        />
        {error && <p className="text-red-500 text-sm">{error}</p>}
        <button
          type="submit"
          disabled={loading}
          className="w-full px-4 py-3 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 transition"
        >
          {loading ? "Sending..." : "Send Magic Link"}
        </button>
      </form>
    </div>
  );
}
