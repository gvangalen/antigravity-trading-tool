'use client';

import { useEffect, useState } from "react";

export default function PageLoader({
  text = "Dashboard wordt geladen…",
  minDuration = 600,   // minimale weergavetijd voor smooth effect
  maxDuration = 1500,  // maximale tijd voor fallback
  active = true,       // dashboard bepaalt wanneer loader weg mag
}) {
  const [visible, setVisible] = useState(true);
  const [fadeOut, setFadeOut] = useState(false);

  useEffect(() => {
    if (!active) {
      // Wanneer dashboard klaar is → fade-out
      const fadeTimer = setTimeout(() => setFadeOut(true), minDuration);

      // Verwijder uit DOM wanneer fade-out klaar is
      const removeTimer = setTimeout(() => setVisible(false), minDuration + 250);

      return () => {
        clearTimeout(fadeTimer);
        clearTimeout(removeTimer);
      };
    }

    // Fallback — loader mag NOOIT langer dan maxDuration blijven staan
    const fallbackTimer = setTimeout(() => {
      setFadeOut(true);
      setTimeout(() => setVisible(false), 250);
    }, maxDuration);

    return () => clearTimeout(fallbackTimer);
  }, [active, minDuration, maxDuration]);

  if (!visible) return null;

  return (
    <div
      className={`
        fixed inset-0 z-[999]
        flex flex-col items-center justify-center
        bg-white/70 dark:bg-black/60 backdrop-blur-sm
        transition-opacity duration-300
        ${fadeOut ? "opacity-0 pointer-events-none" : "opacity-100"}
      `}
    >
      {/* Hybrid Glow Loader */}
      <div className="relative">
        {/* Soft Glow */}
        <div
          className="
            absolute inset-0 rounded-full
            bg-[var(--primary)] opacity-25 blur-xl
            animate-pulse
          "
        ></div>

        {/* Rotating Ring */}
        <div
          className="
            h-14 w-14 sm:h-16 sm:w-16 
            rounded-full border-4 
            border-[var(--primary)] 
            border-t-transparent 
            animate-spin
          "
        ></div>
      </div>

      {/* LOADING TEXT */}
      {text && (
        <p
          className="
            mt-4 text-sm
            text-[var(--text-light)]
            dark:text-[var(--text-light)]
            animate-fade-slide
          "
        >
          {text}
        </p>
      )}
    </div>
  );
}
