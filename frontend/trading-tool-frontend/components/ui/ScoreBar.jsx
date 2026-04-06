"use client";

import { getScoreBarClass } from "@/components/ui/scoreUtils";

export default function ScoreBar({
  score = 0,
  height = "h-2",
  showLabel = false,
}) {
  const numericScore = Number(score);
  const safeScore =
    Number.isFinite(numericScore) && numericScore > 0
      ? Math.min(numericScore, 100)
      : 10;

  return (
    <div className="space-y-1">
      <div className={`w-full bg-gray-100 rounded-full overflow-hidden ${height}`}>
        <div
          className={`${getScoreBarClass(safeScore)} h-full transition-all duration-300`}
          style={{ width: `${safeScore}%` }}
        />
      </div>

      {showLabel && (
        <div className="text-xs text-[var(--text-muted)]">
          Score: <span className="font-medium">{safeScore} / 100</span>
        </div>
      )}
    </div>
  );
}
