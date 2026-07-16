"use client";

import { Suspense, useEffect, useMemo, useState } from "react";
import { Wallet } from "lucide-react";

import useBotData from "@/hooks/useBotData";
import BotPortfolioOverview from "@/components/bot/BotPortfolioOverview";
import PortfolioBalanceCard from "@/components/bot/PortfolioBalanceCard";
import DashboardErrorBoundary from "@/components/ui/DashboardErrorBoundary";
import SystemConnectivity from "@/components/dashboard/SystemConnectivity";
import { trackAssistantEvent } from "@/lib/api/assistantAnalytics";
import { useTranslation } from "@/app/providers/I18nProvider";

function PortfolioPageInner() {
  const { t } = useTranslation();
  const copy = t?.botPage || {};
  const [envFilter, setEnvFilter] = useState("all");

  const {
    configs: bots = [],
    portfolios = [],
    loading,
    error,
  } = useBotData();

  useEffect(() => {
    trackAssistantEvent({
      event_name: "screen_view",
      page: "/portfolio",
      surface: "web",
      flow_type: "portfolio_review",
    });
  }, []);

  const aggregatedBotsForOverview = useMemo(() => {
    return bots.map((bot) => {
      const portfolio = portfolios.find((item) => item.bot_id === bot.id);
      return {
        bot_id: bot.id,
        symbol: portfolio?.symbol ?? bot?.symbol ?? "—",
        is_live: bot.is_live,
        budget: portfolio?.budget ?? {},
        stats: portfolio?.stats ?? {},
      };
    });
  }, [bots, portfolios]);

  return (
    <div className="page-container !max-w-none !px-6 bg-white dark:bg-[#020617] transition-colors h-auto overflow-visible pb-24">
      <header className="page-header border-l-4 border-blue-600 pl-8 mb-16">
        <div className="page-label text-[11px] font-black text-blue-600 dark:text-blue-500 uppercase tracking-[0.3em] mb-2 opacity-80 flex items-center gap-2">
          <Wallet size={12} />
          {copy.eyebrow}
        </div>
        <div className="max-w-2xl">
          <h1 className="page-title text-5xl font-black text-slate-900 dark:text-slate-100 tracking-tight leading-none mb-3">
            {t?.assistant?.uiText?.portfolio || "Portfolio"}
          </h1>
          <p className="page-subtitle text-[15px] font-medium text-slate-400 dark:text-slate-500 leading-relaxed">
            {copy.subtitle}
          </p>
        </div>
      </header>

      <div className="space-y-8">
        {error && (
          <div className="rounded-2xl border border-red-200 bg-red-50 px-5 py-4 text-sm font-bold text-red-700 dark:border-red-900/60 dark:bg-red-950/30 dark:text-red-200">
            {copy.partialError}
          </div>
        )}

        <div className="flex justify-end">
          <DashboardErrorBoundary>
            <SystemConnectivity />
          </DashboardErrorBoundary>
        </div>

        <div className="card bg-white dark:bg-[#0f172a] border-2 border-slate-100 dark:border-slate-800 rounded-3xl overflow-hidden shadow-sm">
          <div className="card-header border-b border-slate-100 dark:border-slate-800 p-6">
            <div className="card-title text-slate-900 dark:text-white flex items-center gap-3 font-black uppercase tracking-widest text-xs">
              {copy.portfolioOverviewTitle}
            </div>
          </div>
          <div className="card-p p-8">
            <PortfolioBalanceCard
              title={copy.portfolioOverviewCardTitle}
              defaultRange="1W"
              is_live={envFilter === "all" ? null : envFilter === "live"}
            />
          </div>
        </div>

        {!loading?.configs && !loading?.portfolios && aggregatedBotsForOverview.length === 0 ? (
          <div className="card p-10 text-center text-sm font-bold text-slate-500 dark:text-slate-400">
            {copy.noBotsYet || "Nog geen portfolio-data beschikbaar."}
          </div>
        ) : null}

        <BotPortfolioOverview
          bots={aggregatedBotsForOverview}
          envFilter={envFilter}
          onEnvFilterChange={setEnvFilter}
        />
      </div>
    </div>
  );
}

export default function PortfolioPage() {
  return (
    <Suspense fallback={null}>
      <PortfolioPageInner />
    </Suspense>
  );
}
