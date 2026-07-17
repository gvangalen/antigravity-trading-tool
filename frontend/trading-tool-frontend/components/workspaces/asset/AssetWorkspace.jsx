"use client";

import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "next/navigation";
import { BarChart3 } from "lucide-react";
import { useAsset } from "@/app/providers/AssetProvider";
import { useTranslation } from "@/app/providers/I18nProvider";
import DashboardErrorBoundary from "@/components/ui/DashboardErrorBoundary";
import AgentInsightPanel from "@/components/agents/AgentInsightPanel";
import MarketAnalysisWorkflow from "@/components/workflows/MarketAnalysisWorkflow";

function interpolate(template, values) {
  return Object.entries(values).reduce(
    (copy, [key, value]) => copy.replaceAll(`{${key}}`, value),
    template || ""
  );
}

function AssetOverview({ symbol }) {
  const { t } = useTranslation();
  const copy = t.assetWorkspace;
  const labels = copy.tabs;

  return (
    <div className="page-container bg-white dark:bg-[#020617] min-h-screen transition-colors">
      <header className="page-header border-l-4 border-blue-600 pl-8 mb-12">
        <div className="page-label text-[11px] font-black text-blue-600 uppercase tracking-[0.3em] mb-2 opacity-80 flex items-center gap-2">
          <BarChart3 size={12} />
          {copy.overview.eyebrow}
        </div>
        <h1 className="page-title text-5xl font-black text-slate-900 dark:text-slate-100 tracking-tight leading-none mb-3">
          {symbol} {copy.overview.titleSuffix}
        </h1>
        <p className="page-subtitle text-[15px] font-medium text-slate-400 dark:text-slate-500 max-w-2xl leading-relaxed">
          {interpolate(copy.overview.subtitle, { symbol })}
        </p>
      </header>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        {["market", "macro", "technical", "ai"].map((tabId) => (
          <div
            key={tabId}
            className="rounded-3xl border-2 border-slate-100 bg-white p-8 shadow-sm dark:border-slate-800 dark:bg-[#0f172a]"
          >
            <div className="mb-3 text-[11px] font-black uppercase tracking-[0.25em] text-blue-600">
              {labels[tabId]}
            </div>
            <p className="text-sm font-semibold leading-relaxed text-slate-500 dark:text-slate-400">
              {interpolate(copy.overview.cardBody, {
                tab: labels[tabId].toLowerCase(),
                symbol,
              })}
            </p>
          </div>
        ))}
      </div>
    </div>
  );
}

export default function AssetWorkspace({ initialTab = "overview" }) {
  const searchParams = useSearchParams();
  const { selectedAsset, setSelectedAsset } = useAsset();
  const { t } = useTranslation();
  const labels = t.assetWorkspace.tabs;
  const copy = t.assetWorkspace;
  const queryTab = searchParams.get("tab");
  const symbolFromUrl = searchParams.get("symbol")?.toUpperCase();
  const activeSymbol = symbolFromUrl || selectedAsset || "BTC";
  const [activeTab, setActiveTab] = useState(queryTab || initialTab || "overview");

  useEffect(() => {
    if (symbolFromUrl && symbolFromUrl !== selectedAsset) {
      setSelectedAsset(symbolFromUrl);
    }
  }, [selectedAsset, setSelectedAsset, symbolFromUrl]);

  useEffect(() => {
    if (queryTab && queryTab !== activeTab) {
      setActiveTab(queryTab);
    }
  }, [activeTab, queryTab]);

  const tabContent = useMemo(() => {
    switch (activeTab) {
      case "market":
        return <MarketAnalysisWorkflow initialStep="market" />;
      case "macro":
        return <MarketAnalysisWorkflow initialStep="macro" />;
      case "technical":
        return <MarketAnalysisWorkflow initialStep="technical" />;
      case "ai":
        return (
          <div className="page-container bg-white dark:bg-[#020617] min-h-screen">
            <header className="page-header border-l-4 border-blue-600 pl-8 mb-12">
              <div className="page-label text-[11px] font-black text-blue-600 uppercase tracking-[0.3em] mb-2 opacity-80">
                {copy.ai.eyebrow}
              </div>
              <h1 className="page-title text-5xl font-black text-slate-900 dark:text-slate-100 tracking-tight leading-none mb-3">
                {labels.ai}
              </h1>
              <p className="page-subtitle text-[15px] font-medium text-slate-400 dark:text-slate-500 max-w-2xl leading-relaxed">
                {interpolate(copy.ai.subtitle, { symbol: activeSymbol })}
              </p>
            </header>
            <DashboardErrorBoundary>
              <AgentInsightPanel category="market" symbol={activeSymbol} />
            </DashboardErrorBoundary>
          </div>
        );
      default:
        return <AssetOverview symbol={activeSymbol} />;
    }
  }, [activeSymbol, activeTab, copy.ai, labels.ai]);

  return <section className="min-h-screen bg-white dark:bg-[#020617]">{tabContent}</section>;
}
