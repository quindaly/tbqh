"use client";

import { useEffect, useState } from "react";
import { getMe, logout } from "@/lib/api";
import { useRouter } from "next/navigation";
import ThemeToggle from "./ThemeToggle";

export default function NavBar() {
  const router = useRouter();
  const [user, setUser] = useState<{ id: string; email: string } | null>(null);
  const isGuest = user?.email?.endsWith("@guest.local");

  useEffect(() => {
    getMe().then(setUser).catch(() => {});
  }, []);

  async function handleLogout() {
    await logout();
    setUser(null);
    router.push("/");
  }

  return (
    <nav className="border-b border-soft bg-paper px-6 py-2 flex items-center justify-between gap-3">
      <a href="/" className="font-serif text-[26px] font-medium tracking-[-0.01em]">
        tbqh
      </a>
      <div className="flex flex-wrap justify-end gap-x-4 text-sm items-center text-muted">
        {user ? (
          <>
            <a href="/dashboard" className="hover:text-ink hover:underline">
              Dashboard
            </a>
            {!isGuest && (
              <>
                <a href="/favorites" className="hover:text-ink hover:underline">
                  Favorites
                </a>
                <a href="/blocked" className="hover:text-ink hover:underline">
                  Blocked
                </a>
              </>
            )}
            {isGuest ? (
              <a
                href="/login"
                className="text-accent hover:underline font-medium"
              >
                Sign In
              </a>
            ) : (
              <button
                onClick={handleLogout}
                className="hover:underline"
              >
                Sign Out
              </button>
            )}
          </>
        ) : (
          <a
            href="/login"
            className="text-accent hover:underline font-medium"
          >
            Sign In
          </a>
        )}
        <ThemeToggle />
      </div>
    </nav>
  );
}
