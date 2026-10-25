"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

/** The dashboard was an extra stop between signing in and everything else. Home does that job now. */
export default function DashboardPage() {
  const router = useRouter();
  useEffect(() => {
    router.replace("/");
  }, [router]);
  return null;
}
