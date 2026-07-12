"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import {
  Activity,
  Brain,
  ChevronDown,
  ChevronRight,
  Compass,
  Globe,
  LineChart,
  Plus,
  Sparkles,
  Target,
} from "lucide-react";

import { useCurrentAsset } from "@/hooks/useCurrentAsset";
import { useMarketData } from "@/hooks/useMarketData";
import { useMacroData } from "@/hooks/useMacroData";
import { useTechnicalData } from "@/hooks/useTechnicalData";
import { useScoresData } from "@/hooks/useScoresData";
import { useTranslation } from "@/app/providers/I18nProvider";

import AgentInsightPanel from "@/components/agents/AgentInsightPanel";
import DashboardErrorBoundary from "@/components/ui/DashboardErrorBoundary";
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

const STEP_ORDER = ["market", "macro", "technical", "conclusion"];

function getStepMeta(symbol) {
  return {
    market: {
      id: "market",
      label: "Market Context",
      icon: Compass,
      eyebrow: "Step 1",
      description: `Liquidity, participation, price behaviour and recent market structure for ${symbol}.`,
    },
    macro: {
      id: "macro",
      label: "Macro Context",
      icon: Globe,
      eyebrow: "Step 2",
      description: `Macro regime, rates, flows and higher-level pressure around ${symbol}.`,
    },
    technical: {
      id: "technical",
      label: "Technical Context",
      icon: LineChart,
      eyebrow: "Step 3",
      description: `Trend, momentum and active indicator logic for ${symbol}.`,
    },
    conclusion: {
      id: "conclusion",
      label: "FINN Conclusion",
      icon: Sparkles,
      eyebrow: "Step 4",
      description: `Combine market, macro and technical into one working bias and next step.`,
    },
  };
}

function resolveActiveStep({ pathname, searchParams, initialStep = "market" }) {
  const explicitStep = searchParams.get("step");
  if (STEP_ORDER.includes(explicitStep)) {
    return explicitStep;
  }

  if (pathname === "/macro") return "macro";
  if (pathname === "/technical") return "technical";
  if (pathname === "/market") return "market";

  const tab = searchParams.get("tab");
  if (STEP_ORDER.includes(tab)) {
    return tab;
  }

  return initialStep;
}

function buildStepHref({ pathname, symbol, stepId }) {
  const safeSymbol = encodeURIComponent(symbol || "BTC");

  if (pathname === "/asset") {
    const tab = stepId === "conclusion" ? "market" : stepId;
    return `/asset?symbol=${safeSymbol}&tab=${tab}&step=${stepId}`;
  }

  if (stepId === "market") return `/market?symbol=${safeSymbol}&step=market`;
  if (stepId === "macro") return `/macro?symbol=${safeSymbol}&step=macro`;
  if (stepId === "technical") return `/technical?symbol=${safeSymbol}&step=technical`;
  return `/technical?symbol=${safeSymbol}&step=conclusion`;
}

function clampNumber(value, fallback = 50) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}

function getConclusionCopy({ marketScore, macroScore, technicalScore }) {
  const average = Math.round((marketScore + macroScore + technicalScore) / 3);
  const spread = Math.max(marketScore, macroScore, technicalScore) - Math.min(marketScore, macroScore, technicalScore);

  let bias = "Neutral";
  let action = "Hold existing plan and wait for cleaner confirmation.";
  let conditions = "Only press size when at least two of the three context layers improve together.";

  if (average >= 70) {
    bias = "Constructive";
    action = "Lean into validated continuation setups with normal sizing.";
    conditions = "Keep following through only while macro and technical remain aligned.";
  } else if (average <= 35) {
    bias = "Defensive";
    action = "Reduce forcing, protect cash and only act on high-conviction setups.";
    conditions = "Wait for either macro relief or stronger technical confirmation before increasing risk.";
  }

  const confidence =
    spread <= 15 ? "High" :
    spread <= 30 ? "Medium" :
    "Low";

  return {
    average,
    bias,
    confidence,
    action,
    conditions,
  };
}

function SectionShell({ title, description, children, action = null }) {
  return (
    <section className="rounded-[28px] border border-slate-200/80 bg-white p-5 shadow-[0_18px_50px_-40px_rgba(15,23,42,0.28)] dark:border-slate-800 dark:bg-[#0f172a] lg:p-6">
      <div className="mb-5 flex flex-col gap-3 border-b border-slate-100 pb-5 dark:border-slate-800 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <div className="text-[10px] font-black uppercase tracking-[0.28em] text-blue-600 dark:text-blue-400">
            Details
          </div>
          <h3 className="mt-2 text-2xl font-black tracking-tight text-slate-950 dark:text-slate-50">
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

export default function MarketAnalysisWorkflow({ initialStep = "market" }) {
  const pathname = usePathname();
  const router = useRouter();
  const searchParams = useSearchParams();
  const { symbol } = useCurrentAsset();
  const { t } = useTranslation();
  const activeSymbol = symbol || "BTC";
  const [macroTimeframe, setMacroTimeframe] = useState("day");
  const [technicalTimeframe, setTechnicalTimeframe] = useState("day");
  const [showDetails, setShowDetails] = useState({
    market: true,
    macro: true,
    technical: true,
    conclusion: false,
  });
  const [selectedTechnicalIndicator, setSelectedTechnicalIndicator] = useState(null);
  const appliedIndicatorsRef = useRef(new Set());
  const focusedTechnicalIndicatorRef = useRef(null);
  const [technicalConfigModal, setTechnicalConfigModal] = useState(null);

  const stepMeta = useMemo(() => getStepMeta(activeSymbol), [activeSymbol]);
  const activeStep = resolveActiveStep({ pathname, searchParams, initialStep });
  const indicatorFromUrl = searchParams.get("indicator");
  const marketIndicatorFromUrl = searchParams.get("marketIndicator");
  const macroIndicatorFromUrl = searchParams.get("macroIndicator");
  const technicalIndicatorFromUrl = searchParams.get("technicalIndicator") || indicatorFromUrl;
  const indicatorAction = searchParams.get("indicatorAction");

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
    if (technicalIndicatorFromUrl && activeStep === "technical") return;
    if (selectedTechnicalIndicator) return;
    if (!technicalData?.length) return;
    setSelectedTechnicalIndicator(technicalData[0]?.name || null);
  }, [activeStep, selectedTechnicalIndicator, technicalData, technicalIndicatorFromUrl]);

  useEffect(() => {
    if (!selectedTechnicalIndicator) return;
    if (technicalData?.some((item) => item?.name === selectedTechnicalIndicator)) return;
    setSelectedTechnicalIndicator(technicalData?.[0]?.name || null);
  }, [selectedTechnicalIndicator, technicalData]);

  useEffect(() => {
    if (!technicalIndicatorFromUrl || activeStep !== "technical") return;
    if (indicatorAction === "select") return;

    if (technicalData?.some((item) => item?.name === technicalIndicatorFromUrl)) {
      setSelectedTechnicalIndicator(technicalIndicatorFromUrl);
      setShowDetails((current) => ({ ...current, technical: true }));
      return;
    }

    const key = `technical:${technicalIndicatorFromUrl}`;
    if (appliedIndicatorsRef.current.has(key)) return;

    appliedIndicatorsRef.current.add(key);
    setSelectedTechnicalIndicator(technicalIndicatorFromUrl);
    setShowDetails((current) => ({ ...current, technical: true }));

    Promise.resolve(addTechnicalIndicator(technicalIndicatorFromUrl)).catch((error) => {
      console.error("Failed to add technical indicator from command search:", error);
    });
  }, [activeStep, addTechnicalIndicator, indicatorAction, technicalData, technicalIndicatorFromUrl]);

  useEffect(() => {
    if (!technicalIndicatorFromUrl || activeStep !== "technical") return;
    if (!technicalData?.length) return;

    const matchingIndicator = technicalData.find((item) => item?.name === technicalIndicatorFromUrl);
    if (!matchingIndicator) return;

    if (selectedTechnicalIndicator !== matchingIndicator.name) {
      setSelectedTechnicalIndicator(matchingIndicator.name);
    }

    setShowDetails((current) => (
      current.technical ? current : { ...current, technical: true }
    ));

    if (focusedTechnicalIndicatorRef.current === matchingIndicator.name) return;
    focusedTechnicalIndicatorRef.current = matchingIndicator.name;

    requestAnimationFrame(() => {
      document.getElementById("technical-indicator-pills")?.scrollIntoView({
        behavior: "smooth",
        block: "start",
      });
    });
  }, [activeStep, selectedTechnicalIndicator, technicalData, technicalIndicatorFromUrl]);

  useEffect(() => {
    if (!marketIndicatorFromUrl || activeStep !== "market") return;
    const key = `market:${marketIndicatorFromUrl}`;
    if (appliedIndicatorsRef.current.has(key)) return;

    appliedIndicatorsRef.current.add(key);
    setShowDetails((current) => ({ ...current, market: true }));

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
  }, [activeStep, addMarket, marketIndicatorFromUrl, selectIndicator]);

  useEffect(() => {
    if (!macroIndicatorFromUrl || activeStep !== "macro") return;
    const key = `macro:${macroIndicatorFromUrl}`;
    if (appliedIndicatorsRef.current.has(key)) return;

    appliedIndicatorsRef.current.add(key);
    setShowDetails((current) => ({ ...current, macro: true }));

    Promise.resolve(addMacroIndicator(macroIndicatorFromUrl)).catch((error) => {
      console.error("Failed to add macro indicator from command search:", error);
    });
  }, [activeStep, addMacroIndicator, macroIndicatorFromUrl]);

  const conclusion = useMemo(
    () =>
      getConclusionCopy({
        marketScore: clampNumber(market?.score),
        macroScore: clampNumber(macro?.score),
        technicalScore: clampNumber(technical?.score),
      }),
    [macro?.score, market?.score, technical?.score]
  );

  const handleStepNavigation = (stepId) => {
    const href = buildStepHref({ pathname, symbol: activeSymbol, stepId });
    router.push(href, { scroll: false });
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

  const toggleDetails = (stepId) => {
    setShowDetails((current) => ({
      ...current,
      [stepId]: !current[stepId],
    }));
  };

  const selectedTechnicalIndicatorData = technicalData?.find(
    (item) => item?.name === selectedTechnicalIndicator
  );

  return (
    <div className="space-y-6">
      <section className="rounded-[28px] border border-slate-200/80 bg-white p-5 shadow-[0_18px_50px_-40px_rgba(15,23,42,0.28)] dark:border-slate-800 dark:bg-[#0f172a] lg:p-6">
        <div className="mb-5 flex flex-col gap-4 border-b border-slate-100 pb-5 dark:border-slate-800">
          <div className="text-[10px] font-black uppercase tracking-[0.28em] text-blue-600 dark:text-blue-400">
            Shared Workflow
          </div>
          <div className="flex flex-col gap-4 xl:flex-row xl:items-end xl:justify-between">
            <div>
              <h3 className="text-2xl font-black tracking-tight text-slate-950 dark:text-slate-50">
                Market Analysis Workflow
              </h3>
              <p className="mt-1 text-sm font-medium text-slate-500 dark:text-slate-400">
                One routine across market, macro and technical with a final FINN conclusion.
              </p>
            </div>
            <div className="inline-flex items-center gap-2 self-start rounded-full border border-emerald-200 bg-emerald-50 px-3 py-1.5 text-[10px] font-black uppercase tracking-[0.2em] text-emerald-700 dark:border-emerald-900/50 dark:bg-emerald-950/20 dark:text-emerald-300">
              <span className="h-2 w-2 rounded-full bg-emerald-500" />
              Workflow Linked To URL
            </div>
          </div>
        </div>

        <div className="grid gap-3 xl:grid-cols-4">
          {STEP_ORDER.map((stepId, index) => {
            const meta = stepMeta[stepId];
            const Icon = meta.icon;
            const isActive = activeStep === stepId;

            return (
              <button
                key={stepId}
                type="button"
                onClick={() => handleStepNavigation(stepId)}
                className={`rounded-[24px] border p-4 text-left transition-all ${
                  isActive
                    ? "border-blue-500 bg-blue-600 text-white shadow-lg shadow-blue-600/20"
                    : "border-slate-200 bg-slate-50/70 hover:border-blue-200 hover:bg-blue-50 dark:border-slate-800 dark:bg-slate-900/50 dark:hover:border-blue-900"
                }`}
              >
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <div className={`text-[10px] font-black uppercase tracking-[0.26em] ${isActive ? "text-white/75" : "text-slate-400"}`}>
                      {meta.eyebrow}
                    </div>
                    <div className="mt-2 flex items-center gap-2">
                      <span className={`flex h-9 w-9 items-center justify-center rounded-2xl ${isActive ? "bg-white/15" : "bg-white text-blue-600 shadow-sm dark:bg-slate-800"}`}>
                        <Icon size={18} />
                      </span>
                      <div>
                        <div className={`text-xs font-black uppercase tracking-[0.22em] ${isActive ? "text-white" : "text-slate-500"}`}>
                          {index + 1}
                        </div>
                        <div className={`text-base font-black tracking-tight ${isActive ? "text-white" : "text-slate-950 dark:text-slate-50"}`}>
                          {meta.label}
                        </div>
                      </div>
                    </div>
                  </div>
                  {isActive ? <ChevronRight size={18} className="text-white/80" /> : null}
                </div>
                <p className={`mt-4 text-sm font-medium leading-relaxed ${isActive ? "text-white/80" : "text-slate-500 dark:text-slate-400"}`}>
                  {meta.description}
                </p>
              </button>
            );
          })}
        </div>
      </section>

      {activeStep === "market" ? (
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

          <section className="rounded-[28px] border border-slate-200/80 bg-white p-5 shadow-[0_18px_50px_-40px_rgba(15,23,42,0.28)] dark:border-slate-800 dark:bg-[#0f172a] lg:p-6">
            <div className="flex w-full items-center justify-between gap-4">
              <div>
                <div className="text-[10px] font-black uppercase tracking-[0.28em] text-blue-600 dark:text-blue-400">
                  Market Details
                </div>
                <h3 className="mt-2 text-2xl font-black tracking-tight text-slate-950 dark:text-slate-50">
                  Configuration, signals and history
                </h3>
              </div>
            </div>

            <div className="mt-6 grid gap-6">
              <MarketIndicatorScoreView
                availableIndicators={availableIndicators || []}
                selectedIndicator={selectedIndicator}
                selectIndicator={selectIndicator}
                addMarketIndicator={addMarket}
                activeIndicators={activeMarketIndicatorNames || []}
              />

              <TechnicalTerminalGrid
                title={`Market signals for ${activeSymbol}`}
                data={marketDayData || []}
                loading={marketLoading}
              />

              <MarketSevenDayTable history={sevenDayData || []} loading={marketLoading} />
              <MarketForwardReturnTabs data={forwardReturns || {}} />
            </div>
          </section>
        </>
      ) : null}

      {activeStep === "macro" ? (
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

          <section className="rounded-[28px] border border-slate-200/80 bg-white p-5 shadow-[0_18px_50px_-40px_rgba(15,23,42,0.28)] dark:border-slate-800 dark:bg-[#0f172a] lg:p-6">
            <div className="flex w-full items-center justify-between gap-4">
              <div>
                <div className="text-[10px] font-black uppercase tracking-[0.28em] text-blue-600 dark:text-blue-400">
                  Macro Details
                </div>
                <h3 className="mt-2 text-2xl font-black tracking-tight text-slate-950 dark:text-slate-50">
                  Indicator setup and timeframe drilldown
                </h3>
              </div>
            </div>

            <div className="mt-6 grid gap-6">
              <MacroIndicatorScoreView
                addMacroIndicator={addMacroIndicator}
                activeMacroIndicatorNames={activeMacroIndicatorNames || []}
                initialSelectedName={macroIndicatorFromUrl}
              />

              <MacroTabs
                activeTab={macroTimeframe}
                setActiveTab={setMacroTimeframe}
                macroData={macroData}
                loading={macroLoading}
                error={macroError}
                handleRemove={(name) => removeMacroIndicator(name)}
              />
            </div>
          </section>
        </>
      ) : null}

      {activeStep === "technical" ? (
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

          <SectionShell
            title="Technical Details"
            description="Add indicators from the command search, then refine or review them here."
            action={
              <button
                type="button"
                onClick={openIndicatorSearch}
                className="inline-flex items-center gap-2 rounded-2xl bg-blue-600 px-4 py-2.5 text-[11px] font-black uppercase tracking-[0.22em] text-white shadow-lg shadow-blue-600/20 transition hover:bg-blue-700"
              >
                <Plus size={14} />
                Indicator toevoegen
              </button>
            }
          >
            <div className="grid gap-6">
              <div className="rounded-[24px] border border-slate-200 bg-slate-50/60 p-4 dark:border-slate-800 dark:bg-slate-900/40">
                <div className="mb-3 flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
                  <div className="flex items-center gap-2 text-[10px] font-black uppercase tracking-[0.26em] text-slate-400">
                    <Target size={12} />
                    Active Technical Indicators
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
                    No indicator selected yet. Use the top search or the button above to add one.
                  </div>
                )}
              </div>

              <div className="rounded-[24px] border border-slate-200 bg-white p-5 shadow-sm dark:border-slate-800 dark:bg-[#06101f]">
                <div className="mb-4 flex items-center gap-2 text-[10px] font-black uppercase tracking-[0.26em] text-slate-400">
                  <Activity size={12} />
                  Signal Tables
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
          </SectionShell>
        </>
      ) : null}

      {activeStep === "conclusion" ? (
        <SectionShell
          title="FINN Conclusion"
          description="A combined working bias built from the current market, macro and technical layers."
        >
          <div className="grid gap-6 xl:grid-cols-[1.3fr_0.7fr]">
            <div className="rounded-[24px] border border-slate-200 bg-slate-50/60 p-5 dark:border-slate-800 dark:bg-slate-900/40">
              <div className="mb-5 flex items-center gap-2 text-[10px] font-black uppercase tracking-[0.26em] text-blue-600 dark:text-blue-400">
                <Brain size={12} />
                Combined Bias
              </div>
              <div className="grid gap-4 md:grid-cols-3">
                <MetricCard label="Market" value={`${clampNumber(market?.score)}/100`} tone={market?.score} />
                <MetricCard label="Macro" value={`${clampNumber(macro?.score)}/100`} tone={macro?.score} />
                <MetricCard label="Technical" value={`${clampNumber(technical?.score)}/100`} tone={technical?.score} />
              </div>
              <div className="mt-6 grid gap-4 lg:grid-cols-3">
                <SummaryPill title="Bias" value={conclusion.bias} />
                <SummaryPill title="Confidence" value={conclusion.confidence} />
                <SummaryPill title="Average" value={`${conclusion.average}/100`} />
              </div>
              <div className="mt-6 rounded-[22px] border border-slate-200 bg-white p-5 dark:border-slate-800 dark:bg-[#06101f]">
                <div className="text-[10px] font-black uppercase tracking-[0.26em] text-slate-400">
                  Next Action
                </div>
                <p className="mt-3 text-xl font-black tracking-tight text-slate-950 dark:text-slate-50">
                  {conclusion.action}
                </p>
                <p className="mt-3 text-sm font-medium leading-relaxed text-slate-500 dark:text-slate-400">
                  {conclusion.conditions}
                </p>
              </div>
            </div>

            <div className="space-y-4">
              <div className="rounded-[24px] border border-slate-200 bg-white p-5 shadow-sm dark:border-slate-800 dark:bg-[#06101f]">
                <div className="text-[10px] font-black uppercase tracking-[0.26em] text-slate-400">
                  Step Links
                </div>
                <div className="mt-4 space-y-2">
                  {["market", "macro", "technical"].map((stepId) => (
                    <button
                      key={stepId}
                      type="button"
                      onClick={() => handleStepNavigation(stepId)}
                      className="flex w-full items-center justify-between rounded-2xl border border-slate-200 px-4 py-3 text-left transition hover:border-blue-200 hover:bg-blue-50 dark:border-slate-800 dark:hover:border-blue-900"
                    >
                      <span className="text-sm font-black text-slate-900 dark:text-slate-100">
                        {stepMeta[stepId].label}
                      </span>
                      <ChevronRight size={16} className="text-slate-400" />
                    </button>
                  ))}
                </div>
              </div>

              <DashboardErrorBoundary>
                <AgentInsightPanel category="market" symbol={activeSymbol} />
              </DashboardErrorBoundary>
            </div>
          </div>
        </SectionShell>
      ) : null}

      <IndicatorConfigModal
        isOpen={Boolean(technicalConfigModal)}
        category="technical"
        indicator={technicalConfigModal}
        assetSymbol={activeSymbol}
        mode="edit"
        onClose={() => setTechnicalConfigModal(null)}
      />
    </div>
  );
}

function MetricCard({ label, value, tone }) {
  const numericTone = clampNumber(tone);
  const toneClass =
    numericTone >= 70
      ? "border-emerald-200 bg-emerald-50 text-emerald-700"
      : numericTone <= 35
      ? "border-red-200 bg-red-50 text-red-700"
      : "border-slate-200 bg-white text-slate-700";

  return (
    <div className={`rounded-[22px] border p-4 ${toneClass}`}>
      <div className="text-[10px] font-black uppercase tracking-[0.26em] opacity-70">
        {label}
      </div>
      <div className="mt-3 text-3xl font-black tracking-tight">
        {value}
      </div>
    </div>
  );
}

function SummaryPill({ title, value }) {
  return (
    <div className="rounded-[22px] border border-slate-200 bg-white px-4 py-4 dark:border-slate-800 dark:bg-[#06101f]">
      <div className="text-[10px] font-black uppercase tracking-[0.26em] text-slate-400">
        {title}
      </div>
      <div className="mt-2 text-lg font-black tracking-tight text-slate-950 dark:text-slate-50">
        {value}
      </div>
    </div>
  );
}
