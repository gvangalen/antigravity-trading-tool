"use client";

import { useEffect, useRef } from "react";

export function isDocumentVisible() {
  if (typeof document === "undefined") return true;
  return document.visibilityState !== "hidden";
}

export function wait(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

export async function waitUntilVisible(checkEveryMs = 1000) {
  while (!isDocumentVisible()) {
    await wait(checkEveryMs);
  }
}

export function useVisibilityPolling(
  callback,
  {
    enabled = true,
    intervalMs,
    backgroundIntervalMs = null,
    runImmediately = true,
    deps = [],
  }
) {
  const callbackRef = useRef(callback);

  useEffect(() => {
    callbackRef.current = callback;
  }, [callback]);

  useEffect(() => {
    if (!enabled || !intervalMs) return undefined;

    let interval = null;
    let cancelled = false;

    const run = () => {
      if (cancelled) return;
      callbackRef.current?.();
    };

    const activeInterval = () => {
      if (isDocumentVisible()) return intervalMs;
      return backgroundIntervalMs;
    };

    const schedule = () => {
      if (interval) clearInterval(interval);

      const nextInterval = activeInterval();
      if (!nextInterval) return;

      interval = setInterval(() => {
        if (!isDocumentVisible() && !backgroundIntervalMs) return;
        run();
      }, nextInterval);
    };

    const handleVisibilityChange = () => {
      schedule();
      if (isDocumentVisible()) run();
    };

    if (runImmediately) run();
    schedule();

    if (typeof document !== "undefined") {
      document.addEventListener("visibilitychange", handleVisibilityChange);
    }

    return () => {
      cancelled = true;
      if (interval) clearInterval(interval);
      if (typeof document !== "undefined") {
        document.removeEventListener("visibilitychange", handleVisibilityChange);
      }
    };
  }, [enabled, intervalMs, backgroundIntervalMs, runImmediately, ...deps]);
}
