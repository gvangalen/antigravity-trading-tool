"use client";

import { useMemo } from "react";
import {
  Bot,
  Target,
  Shield,
  TrendingUp,
  AlertTriangle,
} from "lucide-react";

/* =========================
   Helpers
========================= */

const num = (v, d = null) => {
  const n = Number(v);
  return Number.isFinite(n) ? n : d;
};

const fmtEur = (v) => {
  const n = Number(v);
  if (!Number.isFinite(n)) return "—";
  return `€${Math.round(n).toLocaleString("nl-NL")}`;
};

const fmtPrice = (v) => {
  const n = Number(v);
  if (!Number.isFinite(n)) return "—";
  return n.toLocaleString("nl-NL");
};

const toArray = (value) => {
  if (Array.isArray(value)) return value;
  if (value == null) return [];

  if (typeof value === "string") {
    const trimmed = value.trim();
    if (!trimmed) return [];

    try {
      const parsed = JSON.parse(trimmed);
      if (Array.isArray(parsed)) return parsed;
    } catch {}

    return trimmed
      .split(",")
      .map((v) => v.trim())
      .filter(Boolean);
  }

  return [value];
};

/* =========================
   NORMALIZERS
========================= */

const normalizeTargets = (value) =>
  toArray(value)
    .map((item, i) => {
      const price =
        typeof item === "number"
          ? item
          : typeof item === "string"
          ? num(item)
          : num(item?.price ?? item?.target ?? item?.value);

      if (price == null) return null;

      return {
        label: item?.label || item?.name || `TP${i + 1}`,
        price,
      };
    })
    .filter(Boolean);

const normalizeEntryPlan = (value) =>
  toArray(value)
    .map((item, i) => {
      const price =
        typeof item === "number"
          ? item
          : typeof item === "string"
          ? num(item)
          : num(item?.price ?? item?.entry ?? item?.value);

      if (price == null) return null;

      return {
        type: item?.type || "watch",
        label: item?.label || item?.name || `Entry ${i + 1}`,
        price,
      };
    })
    .filter(Boolean);

const normalizeStopLoss = (value) => {
  const price =
    typeof value === "object"
      ? num(value?.price ?? value?.stop_loss ?? value?.value)
      : num(value);

  return { price };
};

const normalizeRisk = (value) => {
  if (!value || typeof value !== "object") {
    return { rr: null, risk_eur: null };
  }

  return {
    rr: value.rr ?? value.risk_reward ?? null,
    risk_eur: num(value.risk_eur),
  };
};

/* =========================
   UI
========================= */

function SectionTitle({ icon, title }) {
  return (
    <div className="flex items-center gap-2 font-semibold text-gray-900">
      {icon}
      <span>{title}</span>
    </div>
  );
}

/* =========================
   MAIN COMPONENT
========================= */

export default function TradePlanCard({
  tradePlan = null,
  decision = null,
  loading = false,
}) {
  const safeDecision = decision || {};

  /* ================= DERIVE PLAN ================= */

  const derived = useMemo(() => {
    const raw =
      tradePlan ||
      safeDecision?.trade_plan ||
      safeDecision?.plan ||
      null;

    if (!raw || typeof raw !== "object") {
      return {
        symbol: safeDecision?.symbol || "BTC",
        side: safeDecision?.action || "observe",
        entry_plan: [],
        stop_loss: { price: null },
        targets: [],
        risk: { rr: null, risk_eur: null },
      };
    }

    return {
      symbol: raw.symbol || safeDecision?.symbol || "BTC",
      side: raw.side || safeDecision?.action || "observe",
      entry_plan: normalizeEntryPlan(raw.entry_plan),
      stop_loss: normalizeStopLoss(raw.stop_loss),
      targets: normalizeTargets(raw.targets),
      risk: normalizeRisk(raw.risk),
    };
  }, [tradePlan, safeDecision]);

  /* ================= WATCH MODE FIX ================= */

  const isWatchMode =
    derived.side === "hold" ||
    derived.side === "observe" ||
    derived.targets.length === 0 ||
    derived.stop_loss?.price == null;

  /* ================= LIVE PRICE ================= */

  const livePrice = useMemo(() => {
    return (
      num(safeDecision?.live_price) ??
      num(safeDecision?.price) ??
      num(safeDecision?.market_price) ??
      null
    );
  }, [safeDecision]);

  const symbol = (derived.symbol || "BTC").toUpperCase();

  if (loading) {
    return (
      <div className="rounded-2xl border bg-white p-6">
        <div className="text-sm text-gray-500">
          Trade plan laden…
        </div>
      </div>
    );
  }

  return (
    <div className="rounded-[2rem] border border-slate-200 bg-white shadow-sm p-6 space-y-6">
      {/* 🧭 NAVIGATION HEADER */}
      <div className="flex items-center justify-between">
        <div>
          <div className="text-[10px] font-black text-slate-400 uppercase tracking-widest mb-1">Execution Plan</div>
          <div className="flex items-center gap-2">
            <h3 className="text-xl font-black text-slate-800 tracking-tight">Active Target Logic</h3>
            <div className={`px-2 py-0.5 rounded text-[10px] font-black uppercase tracking-tighter ${derived.side.toLowerCase() === 'buy' || derived.side.toLowerCase() === 'long' ? 'bg-green-100 text-green-600' : 'bg-slate-100 text-slate-500'}`}>
              {derived.side.toUpperCase()}
            </div>
          </div>
        </div>
        
        {Number.isFinite(livePrice) && (
          <div className="text-right">
            <div className="text-[9px] font-black text-slate-400 uppercase tracking-tighter">Live Ticker</div>
            <div className="text-lg font-black text-[var(--primary)] font-mono tracking-tighter animate-pulse">
              €{fmtPrice(livePrice)}
            </div>
          </div>
        )}
      </div>

      {/* 🪜 VERTICAL PRICE LADDER */}
      <div className="bg-slate-50 rounded-2xl p-4 border border-slate-100">
        <div className="relative space-y-1">
          {/* Central Vertical Line */}
          <div className="absolute left-[84px] top-0 bottom-0 w-[1px] bg-slate-200" />

          {/* 🎯 TARGETS (Top-Down) */}
          {[...derived.targets].reverse().map((t, i) => (
            <div key={`target-${i}`} className="flex items-center gap-4 group">
              <div className="w-20 text-right font-mono text-[11px] font-bold text-slate-400 tabular-nums">
                {fmtPrice(t.price)}
              </div>
              <div className="relative flex items-center justify-center w-2 h-2">
                <div className="w-2 h-2 rounded-full bg-green-500 shadow-[0_0_8px_rgba(34,197,94,0.3)] z-10" />
              </div>
              <div className="flex-1 px-3 py-1.5 rounded-xl bg-green-50/50 border border-green-100 text-green-700 text-[10px] font-black uppercase tracking-wider flex items-center justify-between">
                <span>{t.label}</span>
                <span className="opacity-40">TARGET REACH</span>
              </div>
            </div>
          ))}

          {/* ⚡ LIVE PRICE INDICATOR (Dynamic position) */}
          {Number.isFinite(livePrice) && (
            <div className="flex items-center gap-4 py-3 relative z-20">
              <div className="w-20 text-right font-mono text-xs font-black text-[var(--primary)] tabular-nums scale-110">
                {fmtPrice(livePrice)}
              </div>
              <div className="relative flex items-center justify-center w-2 h-2">
                <div className="absolute inset-x-[-100px] h-[2px] bg-[var(--primary)] opacity-10" />
                <div className="w-3 h-3 rounded-full bg-[var(--primary)] shadow-[0_0_12px_var(--primary-soft)] z-20 animate-pulse border-2 border-white" />
              </div>
              <div className="flex-1 px-3 py-2 rounded-xl bg-[var(--primary)] text-white text-[10px] font-black uppercase tracking-widest flex items-center justify-between shadow-md">
                <span>Market Price</span>
                <Activity size={12} className="opacity-60" />
              </div>
            </div>
          )}

          {/* 🏁 ENTRY PLAN */}
          {derived.entry_plan.map((e, i) => {
            const isWatchSide = e.type === "watch";
            return (
              <div key={`entry-${i}`} className="flex items-center gap-4 group">
                <div className="w-20 text-right font-mono text-[11px] font-bold text-slate-400 tabular-nums">
                  {fmtPrice(e.price)}
                </div>
                <div className="relative flex items-center justify-center w-2 h-2">
                  <div className={`w-2 h-2 rounded-full z-10 ${isWatchSide ? 'bg-blue-500' : 'bg-slate-400'}`} />
                </div>
                <div className={`flex-1 px-3 py-1.5 rounded-xl border text-[10px] font-black uppercase tracking-wider flex items-center justify-between ${isWatchSide ? 'bg-blue-50 border-blue-100 text-blue-700' : 'bg-slate-100 border-slate-200 text-slate-500'}`}>
                  <span>{e.label}</span>
                  <span className="opacity-40">{isWatchSide ? "ENTRY WATCH" : "LIMIT LEVEL"}</span>
                </div>
              </div>
            );
          })}

          {/* 🛑 STOP LOSS (Bottom) */}
          {Number.isFinite(derived.stop_loss.price) && (
            <div className="flex items-center gap-4 pt-2 group">
              <div className="w-20 text-right font-mono text-[11px] font-bold text-slate-400 tabular-nums">
                {fmtPrice(derived.stop_loss.price)}
              </div>
              <div className="relative flex items-center justify-center w-2 h-2">
                <div className="w-2 h-2 rounded-full bg-red-500 shadow-[0_0_8px_rgba(239,68,68,0.3)] z-10" />
              </div>
              <div className="flex-1 px-3 py-1.5 rounded-xl bg-red-50 border border-red-100 text-red-600 text-[10px] font-black uppercase tracking-wider flex items-center justify-between">
                <span>STOP LOSS</span>
                <Shield size={10} className="opacity-40" />
              </div>
            </div>
          )}
        </div>
      </div>

      {/* 📊 MISSION INTELLIGENCE FOOTER */}
      <div className="grid grid-cols-2 gap-4">
        <div className="bg-slate-50 border border-slate-100 rounded-xl p-3 flex flex-col justify-center">
          <div className="text-[9px] font-black text-slate-400 uppercase tracking-tighter mb-1">Risk Exposure</div>
          <div className="text-xs font-black text-slate-800 font-mono tracking-tighter">
            {fmtEur(derived.risk.risk_eur)}
          </div>
        </div>

        <div className="bg-slate-50 border border-slate-100 rounded-xl p-3 flex flex-col justify-center">
          <div className="text-[9px] font-black text-slate-400 uppercase tracking-tighter mb-1">R:R Performance</div>
          <div className="text-xs font-black text-slate-800 font-mono tracking-tighter">
            RATIO {derived.risk.rr ?? "—"}
          </div>
        </div>
      </div>

      {loading && (
        <div className="absolute inset-0 bg-white/60 backdrop-blur-[1px] flex items-center justify-center rounded-2xl z-50">
           <div className="text-xs font-black text-slate-400 uppercase tracking-widest animate-pulse">Syncing Plan...</div>
        </div>
      )}
    </div>
  );
}
