"use client";

import { useEffect } from "react";

const CURRENT_BUILD =
  (typeof window !== "undefined" && window.__NEXT_DATA__?.buildId) ||
  process.env.NEXT_PUBLIC_DEPLOY_VERSION ||
  process.env.NEXT_PUBLIC_VERCEL_GIT_COMMIT_SHA ||
  "2026-07-25-runtime-recovery-v2";

export default function CacheKiller() {
  useEffect(() => {
    if (typeof window === "undefined") return;

    async function clearStaleBuild() {
      const recoveryKey = `tradamind_build_recovered_${CURRENT_BUILD}`;
      const lastBuild = localStorage.getItem("tradamind_build_id");

      if (lastBuild === CURRENT_BUILD) return;

      localStorage.setItem("tradamind_build_id", CURRENT_BUILD);

      if (sessionStorage.getItem(recoveryKey)) return;
      sessionStorage.setItem(recoveryKey, "1");

      if ("serviceWorker" in navigator && navigator.serviceWorker.getRegistrations) {
        const registrations = await navigator.serviceWorker.getRegistrations();
        await Promise.all(registrations.map((registration) => registration.unregister()));
      }

      if (window.caches?.keys) {
        const cacheNames = await caches.keys();
        await Promise.all(cacheNames.map((cacheName) => caches.delete(cacheName)));
      }

      const nextUrl = new URL(window.location.href);
      nextUrl.searchParams.set("v", Date.now().toString());
      window.location.replace(nextUrl.toString());
    }

    clearStaleBuild().catch(() => {
      // Cache recovery is best effort; normal rendering should continue.
    });
  }, []);

  return null;
}
