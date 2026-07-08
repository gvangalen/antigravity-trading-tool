"use client";

import { useEffect } from "react";

export default function CacheKiller() {
  const CURRENT_BUILD = "2026-07-08-copy-chunk-recovery";

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
