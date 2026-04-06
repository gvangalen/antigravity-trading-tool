'use client';

export default function SkeletonBlock({ height = "1rem", width = "100%" }) {
  return (
    <div
      className="
        rounded-lg overflow-hidden relative
        bg-[var(--card-border)]/50
      "
      style={{ height, width }}
    >
      <div className="absolute inset-0 animate-[pulse_1.2s_ease-in-out_infinite] bg-[var(--bg-soft)]/40" />
    </div>
  );
}
