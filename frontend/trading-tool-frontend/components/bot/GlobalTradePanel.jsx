"use client";

import { useActiveBot } from "@/app/providers/ActiveBotProvider";
import TradePanelContainer from "./TradePanelContainer";
import { Cpu, Target } from "lucide-react";

export default function GlobalTradePanel({
  decision,
  portfolio,
  onManualTrade,
}) {
  const { activeBot } = useActiveBot();

  if (!activeBot) {
    return (
      <div className="card card-p text-center">
        <p className="text-xs font-black text-slate-400 uppercase tracking-widest opacity-60">
           Selecteer een bot om te handelen
        </p>
      </div>
    );
  }

  const symbol = (activeBot?.strategy?.symbol || activeBot?.symbol || "—").toUpperCase();
  const timeframe = activeBot?.strategy?.timeframe || activeBot?.timeframe || "—";

  return (
    <div className="space-y-6">
      
      {/* 🧭 BOT CONTEXT (High 3D) */}
      <div className="card">
        <div className="card-p">
           <div className="flex items-center gap-4 mb-4 pb-4 border-b border-slate-50">
              <div className="w-10 h-10 rounded-xl bg-slate-50 border border-slate-100 flex items-center justify-center text-blue-600 shadow-inner">
                 <Target size={20} />
              </div>
              <div>
                 <p className="text-[10px] font-black text-slate-400 uppercase tracking-widest leading-none mb-1">Handelen met</p>
                 <h2 className="text-sm font-extrabold text-slate-900 tracking-tight">{activeBot?.name || "Bot"}</h2>
              </div>
           </div>
           
           <div className="flex items-center justify-between text-[11px] font-black uppercase tracking-widest text-slate-500">
              <span className="bg-slate-50 px-2 py-1 rounded-lg border border-slate-100">{symbol}</span>
              <span className="bg-slate-50 px-2 py-1 rounded-lg border border-slate-100">{timeframe}</span>
           </div>
        </div>
      </div>

      {/* ⚡ TRADE PANEL (High Depth) */}
      <div className="card overflow-hidden">
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
