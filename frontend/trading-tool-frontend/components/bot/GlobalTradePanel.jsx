"use client";

import { useActiveBot } from "@/app/providers/ActiveBotProvider";
import TradePanelContainer from "./TradePanelContainer";
import { Target, X } from "lucide-react";
import { useTranslation } from "@/app/providers/I18nProvider";

export default function GlobalTradePanel({
  decision,
  portfolio,
  onManualTrade,
  onClose,
}) {
  const { activeBot } = useActiveBot();
  const { t } = useTranslation();
  const copy = t?.botPage?.globalTradePanel || {};

  if (!activeBot) {
    return (
      <div className="card card-p text-center">
        <p className="text-xs font-black text-secondary uppercase tracking-widest opacity-60">
           {copy.selectBot}
        </p>
      </div>
    );
  }

  const symbol = (
    activeBot?.strategy?.setup?.symbol ||
    activeBot?.strategy?.symbol ||
    activeBot?.symbol ||
    "—"
  ).toUpperCase();
  const timeframe =
    activeBot?.strategy?.setup?.timeframe ||
    activeBot?.strategy?.timeframe ||
    activeBot?.timeframe ||
    "—";
  const isPaused = Boolean(
    activeBot?.is_active === false ||
    activeBot?.is_paused ||
    activeBot?.status === "paused"
  );
  const isLive = Boolean(activeBot?.is_live);

  return (
    <div id="execution-guardrail-panel" className="space-y-6">
      
      {/* 🧭 BOT CONTEXT (High 3D) */}
      <div className="card">
        <div className="card-p">
           <div className="flex items-center gap-4 mb-4 pb-4 border-b border-slate-50">
              <div className="w-10 h-10 rounded-xl bg-[var(--color-border-subtle)] border border-slate-100 flex items-center justify-center text-blue-600 shadow-inner">
                 <Target size={20} />
              </div>
              <div>
                 <p className="text-[10px] font-black text-secondary uppercase tracking-widest leading-none mb-1">{copy.tradingWith}</p>
                 <h2 className="text-sm font-extrabold text-foreground tracking-tight">{activeBot?.name || copy.botFallback}</h2>
              </div>
              <button
                type="button"
                onClick={onClose}
                aria-label={copy.close}
                className="ml-auto inline-flex h-9 w-9 items-center justify-center rounded-xl text-slate-400 transition hover:bg-slate-100 hover:text-slate-700"
              >
                <X size={17} />
              </button>
           </div>
           
           <div className="grid grid-cols-2 gap-2 text-[10px] font-black uppercase tracking-widest text-slate-500 sm:grid-cols-4">
              <span className="rounded-lg border border-slate-100 bg-[var(--color-border-subtle)] px-2 py-1.5 text-center">{symbol}</span>
              <span className="rounded-lg border border-slate-100 bg-[var(--color-border-subtle)] px-2 py-1.5 text-center">{timeframe}</span>
              <span className={`rounded-lg border px-2 py-1.5 text-center ${isLive ? "border-red-200 bg-red-50 text-red-700" : "border-blue-200 bg-blue-50 text-blue-700"}`}>
                {isLive ? copy.live : copy.paper}
              </span>
              <span className={`rounded-lg border px-2 py-1.5 text-center ${isPaused ? "border-amber-200 bg-amber-50 text-amber-700" : "border-emerald-200 bg-emerald-50 text-emerald-700"}`}>
                {isPaused ? copy.paused : copy.active}
              </span>
           </div>
        </div>
      </div>

      {/* ⚡ TRADE PANEL (High Depth) */}
      <div className="card">
        <div className="bg-slate-50/10 p-1">
          <TradePanelContainer
            bot={activeBot}
            decision={decision}
            portfolio={portfolio}
            onManualTrade={onManualTrade}
          />
        </div>
      </div>

    </div>
  );
}
