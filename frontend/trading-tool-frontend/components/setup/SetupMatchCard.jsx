"use client";

import CardWrapper from "@/components/ui/CardWrapper";
import { CheckCircle2, Layers } from "lucide-react";
import { useDailySetupScores } from "@/hooks/useDailySetupScores";

/* -------------------------------------------------------
   Kleine helper voor score visualisatie
------------------------------------------------------- */
function ScoreBar({ score }) {
  const pct = Math.max(0, Math.min(100, Number(score) || 0));

  let color = "bg-yellow-400";
  if (pct >= 70) color = "bg-green-500";
  else if (pct <= 40) color = "bg-red-500";

  return (
    <div className="w-full h-2 bg-gray-200 rounded overflow-hidden">
      <div
        className={`h-full ${color}`}
        style={{ width: `${pct}%` }}
      />
    </div>
  );
}

/* =======================================================
   Setup Match Card
======================================================= */
export default function SetupMatchCard() {
  const { dailySetups, loading } = useDailySetupScores();

  /* -------------------------------
     Loading
  ------------------------------- */
  if (loading) {
    return (
      <CardWrapper>
        <p className="text-sm text-[var(--text-light)]">
          Setup matching laden…
        </p>
      </CardWrapper>
    );
  }

  /* -------------------------------
     Geen data
  ------------------------------- */
  if (!dailySetups || dailySetups.length === 0) {
    return (
      <CardWrapper>
        <p className="text-sm text-[var(--text-light)]">
          Geen setup-scores beschikbaar voor vandaag.
        </p>
      </CardWrapper>
    );
  }

  /* -------------------------------
     Sorteren & selecteren
  ------------------------------- */
  const sorted = [...dailySetups].sort(
    (a, b) => (b.score || 0) - (a.score || 0)
  );

  const best = sorted.find((s) => s.is_best) || sorted[0];
  const topSetups = sorted.slice(0, 3);

  return (
    <CardWrapper>
      {/* ============================
          Header
      ============================ */}
      <div className="flex items-center gap-2 mb-4">
        <Layers className="w-5 h-5 text-[var(--primary)]" />
        <h2 className="text-lg font-semibold text-[var(--text-dark)]">
          Setup Match Vandaag
        </h2>
      </div>

      {/* ============================
          Beste setup
      ============================ */}
      <div className="mb-4 p-3 rounded-lg bg-[var(--card-soft)] border">
        <div className="flex items-center gap-2 mb-1">
          <CheckCircle2 className="w-4 h-4 text-green-600" />
          <span className="text-sm font-medium text-[var(--text-dark)]">
            Beste setup
          </span>
        </div>

        <p className="text-sm text-[var(--text-dark)]">
          <strong>{best.name}</strong>{" "}
          <span className="text-[var(--text-light)]">
            · {best.symbol} · {best.timeframe}
          </span>
        </p>

        <div className="mt-2">
          <ScoreBar score={best.score} />
          <p className="text-xs text-[var(--text-light)] mt-1">
            Score: <strong>{best.score}</strong> / 100
          </p>
        </div>
      </div>

      {/* ============================
          Vergelijking
      ============================ */}
      <div>
        <p className="text-sm font-medium text-[var(--text-dark)] mb-2">
          Vergelijking (top setups)
        </p>

        <div className="space-y-3">
          {topSetups.map((s) => (
            <div key={s.id}>
              <div className="flex justify-between text-sm mb-1">
                <span className="text-[var(--text-dark)]">
                  {s.name}
                </span>
                <span className="text-[var(--text-light)]">
                  {s.score}
                </span>
              </div>
              <ScoreBar score={s.score} />
            </div>
          ))}
        </div>
      </div>

      {/* ============================
          Uitleg
      ============================ */}
      <div className="mt-4 text-xs text-[var(--text-light)]">
        De beste setup wordt bepaald op basis van de huidige macro-, markt-
        en technische scores. De hoogste relatieve score wint, ook als
        geen enkele setup perfect past.
      </div>
    </CardWrapper>
  );
}
