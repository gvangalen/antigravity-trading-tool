"use client";

export default function CardLoader({ text = "Laden…" }) {
  return (
    <div className="flex flex-col items-center justify-center py-6 animate-fade-slide">

      {/* Glow Ring */}
      <div className="relative">
        <div
          className="
            absolute inset-0 rounded-full
            bg-[var(--primary)] opacity-20 blur-lg
            animate-pulse
          "
        />
        <div
          className="
            h-8 w-8 
            rounded-full border-2 
            border-[var(--primary)] 
            border-t-transparent 
            animate-spin
          "
        />
      </div>

      {text && (
        <p className="mt-3 text-xs text-[var(--text-light)] opacity-80">
          {text}
        </p>
      )}
    </div>
  );
}
