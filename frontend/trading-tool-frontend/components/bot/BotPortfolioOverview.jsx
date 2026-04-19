"use client";

import { Wallet, Info } from "lucide-react";

import BotBudgetBar from "./BotBudgetBar";
import BotPnLBadge from "./BotPnLBadge";

/**
 * BotPortfolioOverview — READ ONLY
 * --------------------------------------------------
 * ✅ Aggregatie over ALLE bots
 * ✅ Budget usage = executed trades
 * ✅ Invested = executed trades only
 * ✅ Backend blijft single source of truth
 */
export default function BotPortfolioOverview({ bots = [] }) {
  const list = Array.isArray(bots) ? bots : [];
  if (!list.length) return null;

  // -----------------------------
  // Helper
  // -----------------------------
  const sum = (arr, getter) =>
    arr.reduce((acc, x) => acc + (Number(getter(x)) || 0), 0);

  // =============================
  // BUDGET AGGREGATES
  // =============================

  const totalBudgetEur = sum(list, (b) => b?.budget?.total_eur);
  const totalDailyLimitEur = sum(list, (b) => b?.budget?.daily_limit_eur);
  const totalMaxOrderEur = sum(list, (b) => b?.budget?.max_order_eur);

  // ✅ Alleen executed trades tellen voor budget usage
  const spentExecuted = sum(list, (b) =>
    Math.abs(b?.stats?.net_executed_cash_delta_eur ?? 0)
  );

  const todaySpent = sum(list, (b) => b?.stats?.today_spent_eur);

  const hasBudget =
    totalBudgetEur > 0 || totalDailyLimitEur > 0 || totalMaxOrderEur > 0;

  // =============================
  // PORTFOLIO AGGREGATES
  // =============================

  const positionValue = sum(list, (b) => b?.stats?.position_value_eur);

  const pnlEur = positionValue - spentExecuted;
  const pnlPct = spentExecuted > 0 ? (pnlEur / spentExecuted) * 100 : 0;

  // =============================
  // SYMBOL BREAKDOWN
  // =============================

  const bySymbol = list.reduce((acc, b) => {
    const sym = b?.symbol || "—";

    if (!acc[sym]) {
      acc[sym] = {
        symbol: sym,
        netQty: 0,
        positionValue: 0,
        spentExecuted: 0,
      };
    }

    acc[sym].netQty += Number(b?.stats?.net_qty ?? 0);
    acc[sym].positionValue += Number(b?.stats?.position_value_eur ?? 0);
    acc[sym].spentExecuted += Math.abs(
      Number(b?.stats?.net_executed_cash_delta_eur ?? 0)
    );

    return acc;
  }, {});

  const symbolRows = Object.values(bySymbol).sort(
    (a, b) => b.positionValue - a.positionValue
  );

  // =============================
  // UI
  // =============================

  return (
    <div className="card p-10 space-y-12 animate-fade-in mb-16">
      {/* HEADER WITH BLUE ACCENT */}
      <div className="flex items-start justify-between gap-4 pb-8 border-b-2 border-slate-100">
        <div className="border-l-4 border-blue-600 pl-6">
           <div className="text-[10px] font-black text-secondary gap-2 flex items-center uppercase tracking-[0.3em] mb-1">
              <Wallet size={10} className="text-blue-600" />
              Systeem Overzicht
           </div>
           <h3 className="text-3xl font-black text-foreground tracking-tighter uppercase leading-none">
             Portfolio <span className="text-blue-600/30">—</span> Alle bots
           </h3>
           <p className="text-[13px] font-medium text-secondary mt-2">
             Geaggregeerd overzicht van budget en posities over al je actieve bots.
           </p>
        </div>

        <div className="bg-[var(--color-border-subtle)] px-4 py-2 rounded-xl border-2 border-slate-200/50">
           <div className="text-[9px] font-black text-secondary uppercase tracking-widest">Actieve Bots</div>
           <span className="text-xl font-black text-foreground tracking-tighter tabular-nums">
             {list.length}
           </span>
        </div>
      </div>

      {/* =============================
         BUDGET SECTION (BLUEPRINT STYLE)
      ============================= */}
      <div className="bg-blue-50/20 border-2 border-blue-600/5 rounded-3xl p-8">
        <div className="flex items-center gap-3 mb-6">
          <div className="p-2 bg-blue-600 text-white rounded-lg">
             <Wallet size={16} />
          </div>
          <div>
             <div className="text-[10px] font-black text-secondary uppercase tracking-widest">Gebruik van Totaal Budget</div>
             <div className="text-[11px] font-bold text-blue-600/60 uppercase">Single Source of Truth: Backend</div>
          </div>
        </div>

        {hasBudget ? (
          <div className="space-y-6">
            <BotBudgetBar
              label="Alle bots gecombineerd"
              total={totalBudgetEur}
              spent={spentExecuted}
            />

            <div className="flex flex-wrap items-center gap-x-6 gap-y-2 pt-6 border-t border-blue-600/5">
               <div className="flex flex-col">
                  <span className="text-[9px] font-black text-secondary uppercase tracking-tighter">Vandaag besteed</span>
                  <span className="text-sm font-black text-slate-800">€{Number(todaySpent ?? 0).toFixed(0)}</span>
               </div>
               {totalDailyLimitEur && (
                  <div className="flex flex-col">
                     <span className="text-[9px] font-black text-secondary uppercase tracking-tighter">Daglimiet</span>
                     <span className="text-sm font-black text-slate-800">€{Number(totalDailyLimitEur).toFixed(0)}</span>
                  </div>
               )}
               {totalMaxOrderEur && (
                  <div className="flex flex-col">
                     <span className="text-[9px] font-black text-secondary uppercase tracking-tighter">Som Max/Trade</span>
                     <span className="text-sm font-black text-slate-800">€{Number(totalMaxOrderEur).toFixed(0)}</span>
                  </div>
               )}
            </div>
          </div>
        ) : (
          <div className="text-sm font-black text-secondary uppercase tracking-widest flex items-center gap-2 py-4">
             <Info size={16} /> Geen budget ingesteld
          </div>
        )}
      </div>

      {/* =============================
         PORTFOLIO TOTAL METRICS
      ============================= */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-8 py-8 border-y-2 border-slate-100">
        <Stat label="Posities">{symbolRows.length}</Stat>

        <Stat label="Totale waarde">
          €{Number(positionValue).toFixed(0)}
        </Stat>

        <Stat label="Invested (Exec)">
          €{Number(spentExecuted).toFixed(0)}
        </Stat>

        <Stat label="PnL (Totaal)">
          <BotPnLBadge pnlEur={pnlEur} pnlPct={pnlPct} />
        </Stat>
      </div>

      {/* =============================
         PER SYMBOL BREAKDOWN
      ============================= */}
      {symbolRows.length > 0 && (
        <div className="space-y-6">
          <div className="text-[10px] font-black text-secondary uppercase tracking-[0.25em]">
            Breakdown per asset
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {symbolRows.map((row) => {
              const rowPnl = row.positionValue - row.spentExecuted;
              const rowPct =
                row.spentExecuted > 0
                  ? (rowPnl / row.spentExecuted) * 100
                  : 0;

              return (
                <div
                  key={row.symbol}
                  className="flex items-center justify-between gap-4 rounded-2xl border-2 border-slate-50 bg-slate-50/30 px-5 py-4 transition-all hover:border-blue-600/10 hover:bg-white"
                >
                  <div className="min-w-0">
                    <div className="text-[10px] font-black text-blue-600 uppercase tracking-widest mb-1 leading-none">
                      {row.symbol}
                    </div>
                    <div className="text-sm font-black text-foreground tracking-tighter">
                      {Number(row.netQty).toFixed(6)} <span className="opacity-40 text-[9px] uppercase tracking-normal">{row.symbol}</span>
                    </div>
                  </div>

                  <div className="text-right">
                    <div className="text-sm font-black text-foreground tracking-tight">
                      €{Number(row.positionValue).toFixed(0)}
                    </div>
                    <div className="mt-1">
                      <BotPnLBadge pnlEur={rowPnl} pnlPct={rowPct} />
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}

/* =============================
   UI HELPER
============================= */
function Stat({ label, children }) {
  return (
    <div className="flex flex-col">
      <div className="text-[10px] font-black text-secondary uppercase tracking-widest mb-3">{label}</div>
      <div className="text-3xl font-black text-foreground tracking-tighter leading-none">{children}</div>
    </div>
  );
}
