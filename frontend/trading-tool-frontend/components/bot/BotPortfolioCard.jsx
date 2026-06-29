"use client";

import { Wallet, Info } from "lucide-react";
import { useTranslation } from "@/app/providers/I18nProvider";
import { formatCurrency, formatNumber } from "@/lib/i18n";

import BotBudgetBar from "./BotBudgetBar";
import BotPnLBadge from "./BotPnLBadge";

/**
 * BotPortfolioSection — READ ONLY (FINAL)
 * --------------------------------------------------
 * ✅ Gebaseerd op /bot/portfolios API
 * ✅ Alleen financiële / portfolio data
 * ❌ GEEN status (active / paused)
 * ❌ GEEN acties
 * ✅ Backend = single source of truth
 */
export default function BotPortfolioSection({ bot }) {
  const { t, locale } = useTranslation();
  const copy = t?.botPage?.portfolioCard || {};
  if (!bot) return null;

  const {
    symbol = "—",
    budget = {},
    stats = {},
  } = bot;

  const hasBudget =
    (budget.total_eur ?? 0) > 0 ||
    (budget.daily_limit_eur ?? 0) > 0 ||
    (budget.max_order_eur ?? 0) > 0;

  // =====================================================
  // BACKEND-LED STATS
  // =====================================================

  const netQty = stats.net_qty ?? 0;
  const positionValue = stats.position_value_eur ?? 0;

  // ✔ Alleen ECHTE uitgevoerde trades
  const spentExecuted = Math.abs(
    stats.net_executed_cash_delta_eur ?? 0
  );

  // (optioneel context — nu niet gebruikt voor budget bar)
  const spentTotalForBudget = Math.abs(
    stats.net_cash_delta_eur ?? 0
  );

  const todaySpent = stats.today_spent_eur ?? 0;
  const dailyLimit = budget.daily_limit_eur ?? null;
  const maxOrder = budget.max_order_eur ?? null;

  return (
    <div className="space-y-6">
      {/* 💳 BUDGET CONTROLS */}
      <div className="bg-[var(--color-border-subtle)] border border-slate-100 rounded-2xl p-5 shadow-inner">
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-2 text-[10px] font-black text-secondary uppercase tracking-widest">
            <Wallet size={14} className="text-slate-300" />
            {copy.capitalAllocation}
          </div>
          <div className="flex items-center gap-1.5 px-2 py-0.5 rounded bg-card border border-slate-100 text-[10px] font-bold text-slate-500">
            <Info size={10} />
            {copy.synced}
          </div>
        </div>

        {hasBudget ? (
          <div className="space-y-4">
            <BotBudgetBar
              label={copy.totalBudgetExposure}
              total={budget.total_eur ?? 0}
              spent={spentExecuted}
            />

            <div className="grid grid-cols-2 gap-2 pt-2 border-t border-slate-200/50">
              <div className="flex flex-col">
                <span className="text-[9px] font-black text-secondary uppercase tracking-tighter">{copy.dailySpend}</span>
                <span className="text-xs font-black text-slate-700 font-mono tracking-tighter">
                  {formatCurrency(Number(todaySpent ?? 0), locale, "EUR", { maximumFractionDigits: 0 })} /{" "}
                  {dailyLimit !== null
                    ? formatCurrency(Number(dailyLimit), locale, "EUR", { maximumFractionDigits: 0 })
                    : copy.unlimited}
                </span>
              </div>
              <div className="flex flex-col">
                <span className="text-[9px] font-black text-secondary uppercase tracking-tighter">{copy.maxOrderSize}</span>
                <span className="text-xs font-black text-slate-700 font-mono tracking-tighter">
                  {maxOrder !== null
                    ? formatCurrency(Number(maxOrder), locale, "EUR", { maximumFractionDigits: 0 })
                    : copy.unlimited}
                </span>
              </div>
            </div>
          </div>
        ) : (
          <div className="text-xs font-bold text-secondary italic py-2">
            {copy.noBudgetAssigned}
          </div>
        )}
      </div>

      {/* 📊 PORTFOLIO READOUT */}
      <div className="grid grid-cols-2 gap-4 pt-1">
        <Stat label={copy.netPositionQty}>
          <span className="font-mono tracking-tighter text-slate-800">
            {formatNumber(Number(netQty), locale, {
              minimumFractionDigits: 0,
              maximumFractionDigits: 6,
            })}
          </span>
          <span className="ml-1.5 text-secondary font-black text-[10px]">{symbol}</span>
        </Stat>

        <Stat label={copy.currentAssetValue}>
           <span className="font-mono tracking-tighter text-slate-800">
             {formatCurrency(Number(positionValue), locale, "EUR", {
               minimumFractionDigits: 0,
               maximumFractionDigits: 0,
             })}
           </span>
        </Stat>

        <Stat label={copy.costBasisExecuted}>
           <span className="font-mono tracking-tighter text-slate-800">
             {formatCurrency(Number(spentExecuted), locale, "EUR", {
               minimumFractionDigits: 0,
               maximumFractionDigits: 0,
             })}
           </span>
        </Stat>

        <Stat label={copy.sessionPerformance}>
          <BotPnLBadge
            pnlEur={positionValue - spentExecuted}
            pnlPct={
              spentExecuted > 0
                ? ((positionValue - spentExecuted) / spentExecuted) * 100
                : 0
            }
          />
        </Stat>
      </div>
    </div>
  );
}

/* =====================================================
   UI HELPERS
===================================================== */

function Stat({ label, children }) {
  return (
    <div className="bg-[var(--color-border-subtle)] border border-slate-100 rounded-xl p-3 flex flex-col justify-between hover:border-slate-200 transition-colors">
      <div className="text-[9px] font-black text-secondary uppercase tracking-tighter mb-1.5">
        {label}
      </div>
      <div className="text-[13px] font-black leading-none">
        {children}
      </div>
    </div>
  );
}
