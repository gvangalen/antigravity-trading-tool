'use client';

import { useEffect, useState } from "react";

export default function PageLoader({
  text = "Dashboard laden…",
  minDuration = 600,   // Minimum duration for smooth transition
  maxDuration = 2500,  // Fallback max duration
  active = true,       // Controlled by parent state
}) {
  const [visible, setVisible] = useState(true);
  const [fadeOut, setFadeOut] = useState(false);

  useEffect(() => {
    if (!active) {
      // When parent signaling done → initiate fade-out
      const fadeTimer = setTimeout(() => setFadeOut(true), minDuration);

      // Remove from DOM when fade-out completes
      const removeTimer = setTimeout(() => setVisible(false), minDuration + 300);

      return () => {
        clearTimeout(fadeTimer);
        clearTimeout(removeTimer);
      };
    }

    // Fallback — Ensure loader clears eventually
    const fallbackTimer = setTimeout(() => {
      setFadeOut(true);
      setTimeout(() => setVisible(false), 300);
    }, maxDuration);

    return () => clearTimeout(fallbackTimer);
  }, [active, minDuration, maxDuration]);

  if (!visible) return null;

  return (
    <div
      className={`
        fixed inset-0 z-[999]
        flex flex-col items-center justify-center
        bg-white/80 dark:bg-[#020617]/90 backdrop-blur-md
        transition-opacity duration-500
        ${fadeOut ? "opacity-0 pointer-events-none" : "opacity-100"}
      `}
    >
      {/* Hybrid Glow Loader */}
      <div className="relative">
        {/* Soft Aura Glow */}
        <div
          className="
            absolute inset-0 rounded-full
            bg-blue-600 opacity-20 blur-3xl
            animate-pulse scale-150
          "
        ></div>

        {/* High-Precision Rotating Ring */}
        <div
          className="
            h-16 w-16 
            rounded-full border-[3px] 
            border-blue-600/20 dark:border-blue-400/10
            border-t-blue-600 dark:border-t-blue-400
            animate-spin
          "
        ></div>
      </div>

      {/* INTELLIGENCE STATUS */}
      {text && (
        <div className="mt-8 flex flex-col items-center gap-2">
            <p
              className="
                text-[11px] font-black uppercase tracking-[0.4em]
                text-muted dark:text-slate-400
                animate-pulse
              "
            >
              {text}
            </p>
            <div className="flex gap-1.5">
               <div className="w-1 h-1 rounded-full bg-blue-600 animate-bounce [animation-delay:-0.3s]" />
               <div className="w-1 h-1 rounded-full bg-blue-600 animate-bounce [animation-delay:-0.15s]" />
               <div className="w-1 h-1 rounded-full bg-blue-600 animate-bounce" />
            </div>
        </div>
      )}
    </div>
  );
}
