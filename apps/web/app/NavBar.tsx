"use client";

import { useEffect, useState } from "react";
import { getMe, logout } from "@/lib/api";
import { useRouter } from "next/navigation";

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
    <nav className="border-b border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 px-6 py-3 flex items-center justify-between">
      <a href="/" className="text-xl font-bold tracking-tight">
        tbqh
      </a>
      <div className="flex gap-4 text-sm items-center">
        {user ? (
          <>
            <a href="/dashboard" className="hover:underline">
              Dashboard
            </a>
            {!isGuest && (
              <>
                <a href="/favorites" className="hover:underline">
                  Favorites
                </a>
                <a href="/blocked" className="hover:underline">
                  Blocked
                </a>
              </>
            )}
            {isGuest ? (
              <a
                href="/login"
                className="text-blue-600 hover:underline font-medium"
              >
                Sign In
              </a>
            ) : (
              <button
                onClick={handleLogout}
                className="text-gray-500 hover:underline"
              >
                Sign Out
              </button>
            )}
          </>
        ) : (
          <a
            href="/login"
            className="text-blue-600 hover:underline font-medium"
          >
            Sign In
          </a>
        )}
      </div>
    </nav>
  );
}
