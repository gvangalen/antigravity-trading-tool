'use client';

export default function SkeletonTable({ rows = 5, columns = 5 }) {
  return (
    <div className="space-y-3">
      {[...Array(rows)].map((_, rowIndex) => (
        <div key={rowIndex} className="flex gap-3">
          {[...Array(columns)].map((_, colIndex) => (
            <div
              key={colIndex}
              className="
                relative overflow-hidden
                rounded-lg
                bg-[var(--card-border)]/50
                h-4 w-full
              "
            >
              <div
                className="
                  absolute inset-0
                  animate-[pulse_1.2s_ease-in-out_infinite]
                  bg-[var(--bg-soft)]/40
                "
              />
            </div>
          ))}
        </div>
      ))}
    </div>
  );
}
