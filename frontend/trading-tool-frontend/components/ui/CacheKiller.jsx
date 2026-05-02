"use client";

import { useEffect } from "react";

export default function CacheKiller() {
  useEffect(() => {
    // 💀 Atomic Cache Destroyer: Unregister all Service Workers
    if ("serviceWorker" in navigator) {
      navigator.serviceWorker.getRegistrations().then((registrations) => {
        for (let registration of registrations) {
          registration.unregister();
          console.log("💀 SW Unregistered");
        }
      });
    }
    // Clear caches
    if ("caches" in window) {
      caches.keys().then((names) => {
        for (let name of names) {
          caches.delete(name);
        }
        console.log("💀 Caches Cleared");
      });
    }
  }, []);

  return null;
}
