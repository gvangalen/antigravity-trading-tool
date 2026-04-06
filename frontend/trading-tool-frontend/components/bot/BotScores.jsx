"use client";

import CardWrapper from "@/components/ui/CardWrapper";
import CardLoader from "@/components/ui/CardLoader";
import { BarChart3 } from "lucide-react";

export default function BotScores({
  scores = {},
  loading = false,
}) {
  const hasScores =
    scores && Object.keys(scores).length > 0;

  return (
    <div className="bg-white border border-slate-200 rounded-[2rem] p-6 shadow-sm">
      <div className="flex items-center gap-3 mb-6">
        <div className="p-2 rounded-lg bg-blue-50 text-[var(--primary)]">
          <BarChart3 size={18} />
        </div>
        <div>
          <div className="text-[10px] font-black text-slate-400 uppercase tracking-widest">Environment Analytics</div>
          <div className="text-sm font-bold text-slate-800 tracking-tight">System Health & Market Scopes</div>
        </div>
      </div>

      {loading && (
        <CardLoader text="SYNCING SENSORS..." />
      )}

      {!loading && !hasScores && (
        <div className="p-8 rounded-2xl bg-slate-50 border border-slate-100 border-dashed text-center">
          <p className="text-xs font-black text-slate-400 uppercase tracking-widest">
            NO TELEMETRY DATA AVAILABLE FOR CURRENT SESSION
          </p>
        </div>
      )}

      {!loading && hasScores && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          {Object.entries(scores).map(([key, value]) => {
            const score = Number(value) || 0;

            let colorClass = "text-slate-400";
            let bgClass = "bg-slate-50 border-slate-100";
            
            if (score >= 70) {
              colorClass = "text-green-600";
              bgClass = "bg-green-50/50 border-green-100/50";
            } else if (score <= 35) {
              colorClass = "text-red-600";
              bgClass = "bg-red-50/50 border-red-100/50";
            }

            return (
              <div
                key={key}
                className={`
                  rounded-2xl
                  ${bgClass}
                  border
                  p-4 flex flex-col justify-between
                `}
              >
                <div className="text-[9px] font-black text-slate-400 uppercase tracking-tighter mb-1">
                  {key} INDEX
                </div>

                <div className={`text-2xl font-black font-mono tracking-tighter ${colorClass}`}>
                  {score.toString().padStart(2, '0')}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
