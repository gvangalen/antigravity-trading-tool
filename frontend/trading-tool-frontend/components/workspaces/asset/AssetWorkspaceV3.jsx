"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import {
  Activity,
  ArrowRight,
  Brain,
  Compass,
  Globe,
  LineChart,
  Plus,
  Target,
} from "lucide-react";

import { useAsset } from "@/app/providers/AssetProvider";
import { useTranslation } from "@/app/providers/I18nProvider";
import { useMarketData } from "@/hooks/useMarketData";
import { useMacroData } from "@/hooks/useMacroData";
import { useTechnicalData } from "@/hooks/useTechnicalData";
import { useScoresData } from "@/hooks/useScoresData";
import DashboardErrorBoundary from "@/components/ui/DashboardErrorBoundary";
import AgentInsightPanel from "@/components/agents/AgentInsightPanel";
import IndicatorConfigModal from "@/components/scoring/IndicatorConfigModal";
import MarketTerminalHUD from "@/components/market/MarketTerminalHUD";
import MacroTerminalHUD from "@/components/macro/MacroTerminalHUD";
import TechnicalTerminalHUD from "@/components/technical/TechnicalTerminalHUD";
import MarketIndicatorScoreView from "@/components/market/MarketIndicatorScoreView";
import MacroIndicatorScoreView from "@/components/macro/MacroIndicatorScoreView";
import TechnicalTabs from "@/components/technical/TechnicalTabs";
import MacroTabs from "@/components/macro/MacroTabs";
import TechnicalTerminalGrid from "@/components/technical/TechnicalTerminalGrid";
import MarketSevenDayTable from "@/components/market/MarketSevenDayTable";
import MarketForwardReturnTabs from "@/components/market/MarketForwardReturnTabs";

const SEARCH_OPEN_EVENT = "finn-command-search:open";
const CONTEXT_ORDER = ["market", "macro", "technical"];

function clampNumber(value, fallback = 50) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}

function formatPrice(value, locale) {
  const numericValue = Number(value);
  if (!Number.isFinite(numericValue)) return "—";
  return new Intl.NumberFormat(locale || "en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: numericValue >= 1000 ? 0 : 2,
  }).format(numericValue);
}

function formatPercent(value) {
  const numericValue = Number(value);
  if (!Number.isFinite(numericValue)) return "—";
  return `${numericValue >= 0 ? "+" : ""}${numericValue.toFixed(2)}%`;
}

function formatTimestamp(value, locale) {
  if (!value) return "Offline";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "Offline";
  return new Intl.DateTimeFormat(locale || "en-US", {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

function buildContextHref({ pathname, symbol, context, variant }) {
  const safeSymbol = encodeURIComponent(symbol || "BTC");
  const params = new URLSearchParams();
  params.set("symbol", safeSymbol);

  if (variant === "v3") {
    params.set("variant", "v3");
  }

  if (pathname === "/macro" || pathname === "/market" || pathname === "/technical") {
    return `/${context}?${params.toString()}`;
  }

  params.set("tab", context);
  return `/asset?${params.toString()}`;
}

function resolveContext({ pathname, searchParams, initialTab }) {
  if (pathname === "/macro") return "macro";
  if (pathname === "/technical") return "technical";
  if (pathname === "/market") return "market";

  const tab = searchParams.get("tab");
  if (CONTEXT_ORDER.includes(tab)) return tab;

  const step = searchParams.get("step");
  if (CONTEXT_ORDER.includes(step)) return step;

  return CONTEXT_ORDER.includes(initialTab) ? initialTab : "market";
}

function trimSentence(value, fallback) {
  const source = String(value || "").trim();
  if (!source) return fallback;
  if (source.length <= 140) return source;
  return `${source.slice(0, 137).trim()}...`;
}

function normalizeSignals(signals = [], fallback = []) {
  const items = Array.isArray(signals) ? signals : [];
  const normalized = items
    .map((item) => {
      if (typeof item === "string") return item;
      if (item && typeof item === "object") {
        return item.label || item.name || item.indicator || item.title || null;
      }
      return null;
    })
    .filter(Boolean)
    .slice(0, 4);

  return normalized.length ? normalized : fallback.slice(0, 4);
}

function getContextMeta(symbol, scores, t, btcLive) {
  const marketSignals = normalizeSignals(scores.market?.top_contributors, [
    `Bias: ${scores.market?.bias || t?.pages?.market?.biasNeutral || "Neutral"}`,
    `Risk: ${scores.market?.risk || "Balanced"}`,
    `24h: ${formatPercent(btcLive?.change_24h)}`,
  ]);
  const macroSignals = normalizeSignals(scores.macro?.top_contributors, [
    `Trend: ${scores.macro?.trend || t?.pages?.macro?.unknown || "Unknown"}`,
    `Risk: ${scores.macro?.risk || "Balanced"}`,
    `Bias: ${scores.macro?.bias || t?.pages?.macro?.neutral || "Neutral"}`,
  ]);
  const technicalSignals = normalizeSignals(scores.technical?.top_contributors, [
    `Trend: ${scores.technical?.trend || "Stable"}`,
    `Risk: ${scores.technical?.risk || "Balanced"}`,
    `Bias: ${scores.technical?.bias || "Neutral"}`,
  ]);

  return {
    market: {
      id: "market",
      label: "Markt",
      icon: Compass,
      status: scores.market?.bias || t?.pages?.market?.biasNeutral || "Neutral",
      score: clampNumber(scores.market?.score),
      summary: trimSentence(
        scores.market?.uitleg,
        `Prijsactie, liquiditeit en participatie voor ${symbol} in de actuele marktfase.`
      ),
      detailTitle: `${symbol} market context`,
      detailDescription: `Signalen, configuratie en marktgeschiedenis voor ${symbol} op een plek.`,
      signals: marketSignals,
    },
    macro: {
      id: "macro",
      label: "Macro",
      icon: Globe,
      status: scores.macro?.trend || scores.macro?.bias || t?.pages?.macro?.neutral || "Neutral",
      score: clampNumber(scores.macro?.score),
      summary: trimSentence(
        scores.macro?.uitleg,
        `Regime, flows en hogere druklagen rond ${symbol} zonder uit de assetcontext te stappen.`
      ),
      detailTitle: `${symbol} macro context`,
      detailDescription: `Macro-indicatoren, timeframe drilldown en historische context voor ${symbol}.`,
      signals: macroSignals,
    },
    technical: {
      id: "technical",
      label: "Technisch",
      icon: LineChart,
      status: scores.technical?.trend || scores.technical?.bias || "Stable",
      score: clampNumber(scores.technical?.score),
      summary: trimSentence(
        scores.technical?.uitleg,
        `Trend, momentum en indicatorlogica voor ${symbol} met dezelfde gedeelde detailzone.`
      ),
      detailTitle: `${symbol} technical context`,
      detailDescription: `Indicatoren, signaaltabellen en technische historie voor ${symbol}.`,
      signals: technicalSignals,
    },
  };
}

function ScorePill({ value }) {
  const numericValue = clampNumber(value);
  const toneClass =
    numericValue >= 70
      ? "border-emerald-200 bg-emerald-50 text-emerald-700"
      : numericValue <= 35
      ? "border-red-200 bg-red-50 text-red-700"
      : "border-slate-200 bg-white text-slate-700";

  return (
    <div className={`inline-flex items-center rounded-full border px-3 py-1 text-[11px] font-black uppercase tracking-[0.22em] ${toneClass}`}>
      {numericValue}/100
    </div>
  );
}

function ContextCard({ context, active, onClick }) {
  const Icon = context.icon;

  return (
    <button
      type="button"
      onClick={onClick}
      className={`rounded-[28px] border p-5 text-left transition-all ${
        active
          ? "border-blue-500 bg-blue-600 text-white shadow-[0_24px_50px_-30px_rgba(37,99,235,0.75)]"
          : "border-slate-200/80 bg-white hover:border-blue-200 hover:bg-blue-50/60 dark:border-slate-800 dark:bg-[#0f172a] dark:hover:border-blue-900 dark:hover:bg-slate-900"
      }`}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-center gap-3">
          <span className={`flex h-11 w-11 items-center justify-center rounded-2xl ${active ? "bg-white/15" : "bg-slate-100 text-blue-600 dark:bg-slate-900 dark:text-blue-400"}`}>
            <Icon size={20} />
          </span>
          <div>
            <div className={`text-[10px] font-black uppercase tracking-[0.26em] ${active ? "text-white/70" : "text-slate-400"}`}>
              Context
            </div>
            <div className={`mt-1 text-2xl font-black tracking-tight ${active ? "text-white" : "text-slate-950 dark:text-slate-50"}`}>
              {context.label}
            </div>
          </div>
        </div>
        {active ? <ArrowRight size={18} className="mt-1 text-white/80" /> : <ScorePill value={context.score} />}
      </div>

      <div className="mt-5 flex items-center justify-between gap-3">
        <div>
          <div className={`text-[10px] font-black uppercase tracking-[0.24em] ${active ? "text-white/65" : "text-slate-400"}`}>
            Status
          </div>
          <div className={`mt-1 text-sm font-black uppercase tracking-[0.18em] ${active ? "text-white" : "text-slate-700 dark:text-slate-200"}`}>
            {context.status}
          </div>
        </div>
        {active ? <ScorePill value={context.score} /> : null}
      </div>

      <p className={`mt-4 text-sm font-medium leading-relaxed ${active ? "text-white/82" : "text-slate-500 dark:text-slate-400"}`}>
        {context.summary}
      </p>

      <div className="mt-4 flex flex-wrap gap-2">
        {context.signals.map((signal) => (
          <span
            key={signal}
            className={`rounded-full px-3 py-1 text-[11px] font-bold ${
              active
                ? "bg-white/14 text-white"
                : "bg-slate-100 text-slate-600 dark:bg-slate-900 dark:text-slate-300"
            }`}
          >
            {signal}
          </span>
        ))}
      </div>
    </button>
  );
}

function DetailSection({ title, description, children, action = null }) {
  return (
    <section className="rounded-[30px] border border-slate-200/80 bg-white p-5 shadow-[0_18px_50px_-40px_rgba(15,23,42,0.32)] dark:border-slate-800 dark:bg-[#0f172a] lg:p-6">
      <div className="mb-6 flex flex-col gap-4 border-b border-slate-100 pb-5 dark:border-slate-800 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <div className="text-[10px] font-black uppercase tracking-[0.28em] text-blue-600 dark:text-blue-400">
            Gedeelde detailzone
          </div>
          <h3 className="mt-2 text-3xl font-black tracking-tight text-slate-950 dark:text-slate-50">
            {title}
          </h3>
          <p className="mt-1 text-sm font-medium text-slate-500 dark:text-slate-400">
            {description}
          </p>
        </div>
        {action}
      </div>
      {children}
    </section>
  );
}

export default function AssetWorkspaceV3({ initialTab = "market", variant = "v3" }) {
  const pathname = usePathname();
  const router = useRouter();
  const searchParams = useSearchParams();
  const { selectedAsset, setSelectedAsset, availableAssets = [] } = useAsset();
  const { t, locale } = useTranslation();
  const symbolFromUrl = searchParams.get("symbol")?.toUpperCase();
  const activeSymbol = symbolFromUrl || selectedAsset || "BTC";
  const resolvedContext = resolveContext({ pathname, searchParams, initialTab });
  const [activeContext, setActiveContext] = useState(resolvedContext);
  const [macroTimeframe, setMacroTimeframe] = useState("day");
  const [technicalTimeframe, setTechnicalTimeframe] = useState("day");
  const [selectedTechnicalIndicator, setSelectedTechnicalIndicator] = useState(null);
  const [technicalConfigModal, setTechnicalConfigModal] = useState(null);
  const appliedIndicatorsRef = useRef(new Set());
  const focusedTechnicalIndicatorRef = useRef(null);

  const indicatorFromUrl = searchParams.get("indicator");
  const marketIndicatorFromUrl = searchParams.get("marketIndicator");
  const macroIndicatorFromUrl = searchParams.get("macroIndicator");
  const technicalIndicatorFromUrl = searchParams.get("technicalIndicator") || indicatorFromUrl;
  const indicatorAction = searchParams.get("indicatorAction");

  useEffect(() => {
    if (symbolFromUrl && symbolFromUrl !== selectedAsset) {
      setSelectedAsset(symbolFromUrl);
    }
  }, [selectedAsset, setSelectedAsset, symbolFromUrl]);

  useEffect(() => {
    if (resolvedContext !== activeContext) {
      setActiveContext(resolvedContext);
    }
  }, [activeContext, resolvedContext]);

  const {
    sevenDayData,
    forwardReturns,
    availableIndicators,
    activeMarketIndicatorNames,
    addMarket,
    selectedIndicator,
    selectIndicator,
    btcLive,
    loading: marketLoading,
    marketDayData,
  } = useMarketData(activeSymbol, { includeDailyScores: false });

  const {
    macroData,
    addMacroIndicator,
    removeMacroIndicator,
    activeMacroIndicatorNames,
    loading: macroLoading,
    error: macroError,
  } = useMacroData(macroTimeframe, activeSymbol);

  const {
    technicalData,
    addTechnicalIndicator,
    removeTechnicalIndicator,
    loading: technicalLoading,
    error: technicalError,
  } = useTechnicalData(technicalTimeframe, activeSymbol, { includeScoreSummary: false });

  const { market, macro, technical } = useScoresData(activeSymbol, {
    includeHistory: false,
    includeMaster: false,
  });

  useEffect(() => {
    if (technicalIndicatorFromUrl && activeContext === "technical") return;
    if (selectedTechnicalIndicator) return;
    if (!technicalData?.length) return;
    setSelectedTechnicalIndicator(technicalData[0]?.name || null);
  }, [activeContext, selectedTechnicalIndicator, technicalData, technicalIndicatorFromUrl]);

  useEffect(() => {
    if (!selectedTechnicalIndicator) return;
    if (technicalData?.some((item) => item?.name === selectedTechnicalIndicator)) return;
    setSelectedTechnicalIndicator(technicalData?.[0]?.name || null);
  }, [selectedTechnicalIndicator, technicalData]);

  useEffect(() => {
    if (!technicalIndicatorFromUrl || activeContext !== "technical") return;
    if (indicatorAction === "select") return;

    if (technicalData?.some((item) => item?.name === technicalIndicatorFromUrl)) {
      setSelectedTechnicalIndicator(technicalIndicatorFromUrl);
      return;
    }

    const key = `technical:${technicalIndicatorFromUrl}`;
    if (appliedIndicatorsRef.current.has(key)) return;

    appliedIndicatorsRef.current.add(key);
    setSelectedTechnicalIndicator(technicalIndicatorFromUrl);

    Promise.resolve(addTechnicalIndicator(technicalIndicatorFromUrl)).catch((error) => {
      console.error("Failed to add technical indicator from command search:", error);
    });
  }, [activeContext, addTechnicalIndicator, indicatorAction, technicalData, technicalIndicatorFromUrl]);

  useEffect(() => {
    if (!technicalIndicatorFromUrl || activeContext !== "technical") return;
    if (!technicalData?.length) return;

    const matchingIndicator = technicalData.find((item) => item?.name === technicalIndicatorFromUrl);
    if (!matchingIndicator) return;

    if (selectedTechnicalIndicator !== matchingIndicator.name) {
      setSelectedTechnicalIndicator(matchingIndicator.name);
    }

    if (focusedTechnicalIndicatorRef.current === matchingIndicator.name) return;
    focusedTechnicalIndicatorRef.current = matchingIndicator.name;

    requestAnimationFrame(() => {
      document.getElementById("technical-indicator-pills")?.scrollIntoView({
        behavior: "smooth",
        block: "start",
      });
    });
  }, [activeContext, selectedTechnicalIndicator, technicalData, technicalIndicatorFromUrl]);

  useEffect(() => {
    if (!marketIndicatorFromUrl || activeContext !== "market") return;
    const key = `market:${marketIndicatorFromUrl}`;
    if (appliedIndicatorsRef.current.has(key)) return;

    appliedIndicatorsRef.current.add(key);

    Promise.resolve(addMarket(marketIndicatorFromUrl))
      .then(() => {
        selectIndicator?.({
          name: marketIndicatorFromUrl,
          display_name: marketIndicatorFromUrl,
        });
      })
      .catch((error) => {
        console.error("Failed to add market indicator from command search:", error);
      });
  }, [activeContext, addMarket, marketIndicatorFromUrl, selectIndicator]);

  useEffect(() => {
    if (!macroIndicatorFromUrl || activeContext !== "macro") return;
    const key = `macro:${macroIndicatorFromUrl}`;
    if (appliedIndicatorsRef.current.has(key)) return;

    appliedIndicatorsRef.current.add(key);

    Promise.resolve(addMacroIndicator(macroIndicatorFromUrl)).catch((error) => {
      console.error("Failed to add macro indicator from command search:", error);
    });
  }, [activeContext, addMacroIndicator, macroIndicatorFromUrl]);

  const contextMeta = useMemo(
    () => getContextMeta(activeSymbol, { market, macro, technical }, t, btcLive),
    [activeSymbol, btcLive, macro, market, t, technical]
  );

  const currentContext = contextMeta[activeContext] || contextMeta.market;
  const selectedTechnicalIndicatorData = technicalData?.find(
    (item) => item?.name === selectedTechnicalIndicator
  );
  const assetOptions = useMemo(() => {
    const base = Array.isArray(availableAssets) && availableAssets.length ? availableAssets : ["BTC", "ETH", "SOL", "ADA", "DOT"];
    return Array.from(new Set([activeSymbol, ...base]));
  }, [activeSymbol, availableAssets]);

  const handleContextChange = (nextContext) => {
    setActiveContext(nextContext);
    router.push(buildContextHref({ pathname, symbol: activeSymbol, context: nextContext, variant }), {
      scroll: false,
    });
  };

  const handleAssetChange = (event) => {
    const nextSymbol = String(event.target.value || activeSymbol).toUpperCase();
    setSelectedAsset(nextSymbol);
    router.push(buildContextHref({ pathname, symbol: nextSymbol, context: activeContext, variant }), {
      scroll: false,
    });
  };

  const openIndicatorSearch = () => {
    if (typeof window === "undefined") return;
    window.dispatchEvent(
      new CustomEvent(SEARCH_OPEN_EVENT, {
        detail: {
          mode: "indicator",
          category: "technical",
        },
      })
    );
  };

  return (
    <section className="space-y-6">
      <section className="rounded-[30px] border border-slate-200/80 bg-white p-5 shadow-[0_18px_50px_-40px_rgba(15,23,42,0.32)] dark:border-slate-800 dark:bg-[#0f172a] lg:p-6">
        <div className="mb-5 flex items-center justify-between gap-3">
          <div className="inline-flex items-center gap-2 rounded-full border border-blue-200 bg-blue-50 px-3 py-1.5 text-[10px] font-black uppercase tracking-[0.22em] text-blue-700 dark:border-blue-900 dark:bg-blue-950/30 dark:text-blue-300">
            <Brain size={12} />
            Analyse 3.0 Review
          </div>
        </div>

        <div className="grid gap-5 xl:grid-cols-[1.4fr_0.9fr]">
          <div>
            <div className="flex items-center gap-2 text-[10px] font-black uppercase tracking-[0.28em] text-blue-600 dark:text-blue-400">
              <Brain size={12} />
              Analyse
            </div>
            <h1 className="mt-3 text-4xl font-black tracking-tight text-slate-950 dark:text-slate-50 lg:text-5xl">
              {activeSymbol} Analyse
            </h1>
            <p className="mt-3 max-w-3xl text-sm font-medium leading-relaxed text-slate-500 dark:text-slate-400">
              Complete markt-, macro- en technische context voor {activeSymbol} in een gedeeld analysecanvas.
            </p>

            <div className="mt-6 flex flex-wrap gap-3">
              <MetricBlock label="Prijs" value={formatPrice(btcLive?.price, locale)} />
              <MetricBlock
                label="24u"
                value={formatPercent(btcLive?.change_24h)}
                tone={Number(btcLive?.change_24h) >= 0 ? "positive" : "negative"}
              />
              <MetricBlock label="Laatste update" value={formatTimestamp(btcLive?.timestamp, locale)} />
            </div>
          </div>

          <div className="rounded-[26px] border border-slate-200 bg-slate-50/70 p-5 dark:border-slate-800 dark:bg-[#06101f]">
            <div className="text-[10px] font-black uppercase tracking-[0.28em] text-slate-400">
              Asset switcher
            </div>
            <div className="mt-3 flex items-center gap-3">
              <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-blue-600 text-lg font-black text-white shadow-lg shadow-blue-600/20">
                {activeSymbol.slice(0, 3)}
              </div>
              <div className="min-w-0">
                <div className="text-lg font-black tracking-tight text-slate-950 dark:text-slate-50">
                  {activeSymbol}
                </div>
                <div className="text-sm font-medium text-slate-500 dark:text-slate-400">
                  Zelfde Analyse page, andere assetcontext.
                </div>
              </div>
            </div>

            <label className="mt-5 block text-[10px] font-black uppercase tracking-[0.24em] text-slate-400">
              Kies asset
            </label>
            <select
              value={activeSymbol}
              onChange={handleAssetChange}
              className="mt-2 w-full rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm font-black uppercase tracking-[0.18em] text-slate-900 outline-none transition focus:border-blue-500 dark:border-slate-700 dark:bg-slate-950 dark:text-slate-100"
            >
              {assetOptions.map((asset) => (
                <option key={asset} value={asset}>
                  {asset}
                </option>
              ))}
            </select>
          </div>
        </div>
      </section>

      <section className="grid gap-4 xl:grid-cols-3">
        {CONTEXT_ORDER.map((contextId) => (
          <ContextCard
            key={contextId}
            context={contextMeta[contextId]}
            active={activeContext === contextId}
            onClick={() => handleContextChange(contextId)}
          />
        ))}
      </section>

      <DetailSection
        title={currentContext.detailTitle}
        description={currentContext.detailDescription}
        action={
          activeContext === "technical" ? (
            <button
              type="button"
              onClick={openIndicatorSearch}
              className="inline-flex items-center gap-2 rounded-2xl bg-blue-600 px-4 py-2.5 text-[11px] font-black uppercase tracking-[0.22em] text-white shadow-lg shadow-blue-600/20 transition hover:bg-blue-700"
            >
              <Plus size={14} />
              Indicator toevoegen
            </button>
          ) : null
        }
      >
        <div className="grid gap-6">
          {activeContext === "market" ? (
            <>
              <DashboardErrorBoundary>
                <MarketTerminalHUD
                  score={market?.score ?? null}
                  bias={market?.bias ?? t?.pages?.market?.biasNeutral}
                  btc={btcLive}
                  loading={marketLoading || !market}
                  symbol={activeSymbol}
                />
              </DashboardErrorBoundary>

              <DashboardErrorBoundary>
                <AgentInsightPanel category="market" symbol={activeSymbol} />
              </DashboardErrorBoundary>

              <div className="grid gap-6">
                <MarketIndicatorScoreView
                  availableIndicators={availableIndicators || []}
                  selectedIndicator={selectedIndicator}
                  selectIndicator={selectIndicator}
                  addMarketIndicator={addMarket}
                  activeIndicators={activeMarketIndicatorNames || []}
                />

                <div className="rounded-[24px] border border-slate-200 bg-slate-50/60 p-5 dark:border-slate-800 dark:bg-slate-900/40">
                  <div className="mb-4 flex items-center gap-2 text-[10px] font-black uppercase tracking-[0.26em] text-slate-400">
                    <Activity size={12} />
                    Live signal table
                  </div>
                  <TechnicalTerminalGrid
                    title={`Market signals for ${activeSymbol}`}
                    data={marketDayData || []}
                    loading={marketLoading}
                  />
                </div>

                <div className="rounded-[24px] border border-slate-200 bg-white p-5 shadow-sm dark:border-slate-800 dark:bg-[#06101f]">
                  <div className="mb-4 text-[10px] font-black uppercase tracking-[0.26em] text-slate-400">
                    Historie
                  </div>
                  <div className="grid gap-6">
                    <MarketSevenDayTable history={sevenDayData || []} loading={marketLoading} />
                    <MarketForwardReturnTabs data={forwardReturns || {}} />
                  </div>
                </div>
              </div>
            </>
          ) : null}

          {activeContext === "macro" ? (
            <>
              <DashboardErrorBoundary>
                <MacroTerminalHUD
                  score={macro?.score ?? null}
                  bias={macro?.bias ?? t?.pages?.macro?.neutral}
                  trend={macro?.trend ?? t?.pages?.macro?.unknown}
                  risk={macro?.risk ?? t?.pages?.macro?.unknown}
                  loading={macroLoading || !macro}
                />
              </DashboardErrorBoundary>

              <DashboardErrorBoundary>
                <AgentInsightPanel category="macro" symbol={activeSymbol} />
              </DashboardErrorBoundary>

              <div className="grid gap-6">
                <MacroIndicatorScoreView
                  addMacroIndicator={addMacroIndicator}
                  activeMacroIndicatorNames={activeMacroIndicatorNames || []}
                  initialSelectedName={macroIndicatorFromUrl}
                />

                <div className="rounded-[24px] border border-slate-200 bg-white p-5 shadow-sm dark:border-slate-800 dark:bg-[#06101f]">
                  <div className="mb-4 text-[10px] font-black uppercase tracking-[0.26em] text-slate-400">
                    Historie en timeframe context
                  </div>
                  <MacroTabs
                    activeTab={macroTimeframe}
                    setActiveTab={setMacroTimeframe}
                    macroData={macroData}
                    loading={macroLoading}
                    error={macroError}
                    handleRemove={(name) => removeMacroIndicator(name)}
                  />
                </div>
              </div>
            </>
          ) : null}

          {activeContext === "technical" ? (
            <>
              <DashboardErrorBoundary>
                <TechnicalTerminalHUD
                  score={technical?.score ?? null}
                  bias={technical?.bias}
                  trend={technical?.trend}
                  risk={technical?.risk}
                  loading={technicalLoading || !technical}
                />
              </DashboardErrorBoundary>

              <DashboardErrorBoundary>
                <AgentInsightPanel category="technical" symbol={activeSymbol} />
              </DashboardErrorBoundary>

              <div className="grid gap-6">
                <div className="rounded-[24px] border border-slate-200 bg-slate-50/60 p-5 dark:border-slate-800 dark:bg-slate-900/40">
                  <div className="mb-4 flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
                    <div className="flex items-center gap-2 text-[10px] font-black uppercase tracking-[0.26em] text-slate-400">
                      <Target size={12} />
                      Actieve technische indicatoren
                    </div>

                    {selectedTechnicalIndicatorData ? (
                      <div className="flex flex-wrap items-center gap-3">
                        <button
                          type="button"
                          onClick={() => setTechnicalConfigModal(selectedTechnicalIndicatorData.name)}
                          className="rounded-2xl border border-blue-200 bg-blue-50 px-4 py-2 text-[11px] font-black uppercase tracking-[0.2em] text-blue-600 transition hover:border-blue-300 hover:bg-blue-100"
                        >
                          {selectedTechnicalIndicatorData.name} bewerken
                        </button>
                        <button
                          type="button"
                          onClick={() => removeTechnicalIndicator(selectedTechnicalIndicatorData.name)}
                          className="rounded-2xl border border-slate-200 px-4 py-2 text-[11px] font-black uppercase tracking-[0.2em] text-slate-500 transition hover:border-red-200 hover:text-red-600 dark:border-slate-700 dark:text-slate-300"
                        >
                          Remove
                        </button>
                      </div>
                    ) : null}
                  </div>

                  {technicalData?.length ? (
                    <div id="technical-indicator-pills" className="flex flex-wrap gap-2">
                      {technicalData.map((item) => {
                        const isSelected = selectedTechnicalIndicator === item.name;
                        return (
                          <button
                            key={item.name}
                            type="button"
                            onClick={() => {
                              setSelectedTechnicalIndicator(item.name);
                              setTechnicalConfigModal(item.name);
                            }}
                            className={`rounded-full border px-4 py-2 text-[11px] font-black uppercase tracking-[0.2em] transition ${
                              isSelected
                                ? "border-blue-500 bg-blue-600 text-white"
                                : "border-slate-200 bg-white text-slate-600 hover:border-blue-200 hover:text-blue-600 dark:border-slate-700 dark:bg-slate-950 dark:text-slate-300"
                            }`}
                          >
                            {item.name}
                          </button>
                        );
                      })}
                    </div>
                  ) : (
                    <div className="rounded-[20px] border border-dashed border-slate-200 bg-white px-5 py-6 text-sm font-semibold text-slate-500 dark:border-slate-800 dark:bg-[#0b1325] dark:text-slate-400">
                      Nog geen technische indicator geselecteerd. Gebruik de zoekbalk of de knop hierboven.
                    </div>
                  )}
                </div>

                <div className="rounded-[24px] border border-slate-200 bg-white p-5 shadow-sm dark:border-slate-800 dark:bg-[#06101f]">
                  <div className="mb-4 text-[10px] font-black uppercase tracking-[0.26em] text-slate-400">
                    Historie en signaaltabellen
                  </div>
                  <TechnicalTabs
                    activeTab={technicalTimeframe}
                    setActiveTab={setTechnicalTimeframe}
                    technicalData={technicalData}
                    loading={technicalLoading}
                    error={technicalError}
                    handleRemove={(name) => removeTechnicalIndicator(name)}
                  />
                </div>
              </div>
            </>
          ) : null}
        </div>
      </DetailSection>

      <IndicatorConfigModal
        isOpen={Boolean(technicalConfigModal)}
        category="technical"
        indicator={technicalConfigModal}
        assetSymbol={activeSymbol}
        mode="edit"
        onClose={() => setTechnicalConfigModal(null)}
      />
    </section>
  );
}

function MetricBlock({ label, value, tone = "neutral" }) {
  const toneClass =
    tone === "positive"
      ? "text-emerald-600"
      : tone === "negative"
      ? "text-red-600"
      : "text-slate-950 dark:text-slate-50";

  return (
    <div className="rounded-[22px] border border-slate-200 bg-slate-50/70 px-4 py-3 dark:border-slate-800 dark:bg-[#06101f]">
      <div className="text-[10px] font-black uppercase tracking-[0.24em] text-slate-400">
        {label}
      </div>
      <div className={`mt-2 text-lg font-black tracking-tight ${toneClass}`}>
        {value}
      </div>
    </div>
  );
}
