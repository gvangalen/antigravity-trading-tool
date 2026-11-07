"use client";

import { useEffect, useRef } from "react";
import { usePathname } from "next/navigation";
import { useAuth } from "@/components/auth/AuthProvider";
import { fetchAuth } from "@/lib/api/auth";

const ACTIVITY_INTERVAL_MS = 5 * 60 * 1000;

export default function AppActivityTracker() {
  const pathname = usePathname();
  const { user } = useAuth();
  const lastSentRef = useRef(0);

  useEffect(() => {
    lastSentRef.current = 0;
  }, [user?.id]);

  useEffect(() => {
    if (!user?.id || pathname?.startsWith("/admin")) return undefined;

    const recordVisibleActivity = () => {
      if (document.visibilityState !== "visible") return;
      const now = Date.now();
      if (now - lastSentRef.current < ACTIVITY_INTERVAL_MS) return;
      lastSentRef.current = now;
      void fetchAuth("/api/assistant/analytics/events", {
        method: "POST",
        body: JSON.stringify({ event_name: "app_activity", surface: "web" }),
      }).catch(() => {
        lastSentRef.current = 0;
      });
    };

    recordVisibleActivity();
    window.addEventListener("pointerdown", recordVisibleActivity, { passive: true });
    window.addEventListener("keydown", recordVisibleActivity);
    document.addEventListener("visibilitychange", recordVisibleActivity);
    return () => {
      window.removeEventListener("pointerdown", recordVisibleActivity);
      window.removeEventListener("keydown", recordVisibleActivity);
      document.removeEventListener("visibilitychange", recordVisibleActivity);
    };
  }, [pathname, user?.id]);

  return null;
}
