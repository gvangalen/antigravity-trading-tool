"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import {
  ArrowRight,
  Brain,
  ChevronDown,
  Globe,
  LineChart,
  Plus,
  Settings2,
  Sparkles,
  Target,
  TrendingUp,
} from "lucide-react";

import { useAsset } from "@/app/providers/AssetProvider";
import { useTranslation } from "@/app/providers/I18nProvider";
import { useMarketData } from "@/hooks/useMarketData";
import { useMacroData } from "@/hooks/useMacroData";
import { useTechnicalData } from "@/hooks/useTechnicalData";
import { useScoresData } from "@/hooks/useScoresData";
import IndicatorConfigModal from "@/components/scoring/IndicatorConfigModal";

const SEARCH_OPEN_EVENT = "finn-command-search:open";
const CONTEXT_ORDER = ["market", "macro", "technical"];

const SECTION_META = {
  market: {
    label: "Markt",
    eyebrow: "Market Evidence",
    icon: TrendingUp,
    empty: "Nog geen marktindicatoren geladen.",
  },
  macro: {
    label: "Macro",
    eyebrow: "Macro Evidence",
    icon: Globe,
    empty: "Nog geen macro-indicatoren geladen.",
  },
  technical: {
    label: "Technisch",
    eyebrow: "Technical Evidence",
    icon: LineChart,
    empty: "Nog geen technische indicatoren geladen.",
  },
};

const INDICATOR_LABELS = {
  atr_model: "ATR-model",
  btc_dominance: "Bitcoin-dominantie",
  change_24h: "Prijs 24u",
  change_7d: "Prijs 7d",
  dxy: "DXY",
  etf_flows: "ETF-flows",
  fear_greed_index: "Fear & Greed",
  liquidity: "Liquiditeit",
  ma_200: "200-daags gemiddelde",
  market_structure: "Marktstructuur",
  market_volume: "Volume",
  momentum: "Momentum",
  participation: "Participatie",
  price: "Prijs",
  rsi: "RSI",
  us10y: "US10Y",
  us2y: "US2Y",
  volatility: "Volatiliteit",
  volume: "Volume",
  volume_change: "Volumeverandering",
  volume_change_24h: "Volume 24u",
  volume_trend: "Volume-trend",
};

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

function trimSentence(value, fallback) {
  const source = String(value || "").trim();
  if (!source) return fallback;
  if (source.length <= 160) return source;
  return `${source.slice(0, 157).trim()}...`;
}

function prettifyName(name) {
  if (!name) return "Onbekende indicator";
  const normalized = String(name).trim();
  const lowered = normalized.toLowerCase();
  if (INDICATOR_LABELS[lowered]) return INDICATOR_LABELS[lowered];
  return normalized
    .replace(/_/g, " ")
    .replace(/\b([a-z])/g, (match) => match.toUpperCase());
}

function formatBillions(value, locale) {
  const numericValue = Number(value);
  if (!Number.isFinite(numericValue)) return "—";
  if (Math.abs(numericValue) >= 1e12) {
    return `${new Intl.NumberFormat(locale || "en-US", { maximumFractionDigits: 1 }).format(
      numericValue / 1e12
    )}T`;
  }
  if (Math.abs(numericValue) >= 1e9) {
    return `${new Intl.NumberFormat(locale || "en-US", { maximumFractionDigits: 1 }).format(
      numericValue / 1e9
    )}B`;
  }
  if (Math.abs(numericValue) >= 1e6) {
    return `${new Intl.NumberFormat(locale || "en-US", { maximumFractionDigits: 1 }).format(
      numericValue / 1e6
    )}M`;
  }
  return new Intl.NumberFormat(locale || "en-US", {
    maximumFractionDigits: 2,
  }).format(numericValue);
}

function formatIndicatorValue(name, value, locale) {
  if (value === null || value === undefined || value === "") return "—";
  const label = String(name || "").toLowerCase();
  const raw = typeof value === "string" ? value.trim() : value;
  const numericValue = Number(typeof raw === "string" ? raw.replace(/,/g, ".") : raw);

  if (typeof raw === "string" && /buy|sell|above|below|bull|bear|neutral|hoog|laag|stijg|daal/i.test(raw)) {
    return raw;
  }

  if (label.includes("price")) return formatPrice(numericValue, locale);
  if (label.includes("change") || label.includes("yield") || label.includes("dominance")) {
    if (Number.isFinite(numericValue)) return `${numericValue.toFixed(2)}%`;
  }
  if (label.includes("volume") || label.includes("flow")) {
    if (Number.isFinite(numericValue)) return `$${formatBillions(numericValue, locale)}`;
  }
  if (label.includes("rsi") || label.includes("fear")) {
    if (Number.isFinite(numericValue)) return numericValue.toFixed(1);
  }
  if (label.includes("dxy")) {
    if (Number.isFinite(numericValue)) return numericValue.toFixed(1);
  }

  if (Number.isFinite(numericValue)) {
    if (Math.abs(numericValue) >= 1000) return formatBillions(numericValue, locale);
    return new Intl.NumberFormat(locale || "en-US", {
      maximumFractionDigits: 2,
    }).format(numericValue);
  }

  return String(raw);
}

function toDirectionLabel(item, score) {
  const trendSource = String(item?.trend || item?.action || "").trim().toLowerCase();

  if (trendSource.includes("improv") || trendSource.includes("stijg") || trendSource.includes("bull")) {
    return "Verbeterend";
  }
  if (trendSource.includes("verslecht") || trendSource.includes("dal") || trendSource.includes("bear")) {
    return "Verslechterend";
  }
  if (trendSource.includes("stable") || trendSource.includes("stab")) {
    return "Stabiel";
  }
  if (trendSource.includes("buy")) return "Actief";
  if (trendSource.includes("sell")) return "Verzwakkend";

  if (score >= 70) return "Verbeterend";
  if (score <= 35) return "Verslechterend";
  return "Stabiel";
}

function scoreTone(value) {
  const numericValue = clampNumber(value);
  if (numericValue >= 70) {
    return {
      label: "Positief",
      pill: "border-emerald-200 bg-emerald-50 text-emerald-700",
      text: "text-emerald-700",
      dot: "bg-emerald-500",
    };
  }
  if (numericValue <= 35) {
    return {
      label: "Negatief",
      pill: "border-red-200 bg-red-50 text-red-700",
      text: "text-red-700",
      dot: "bg-red-500",
    };
  }
  return {
    label: "Neutraal",
    pill: "border-slate-200 bg-slate-50 text-slate-700",
    text: "text-slate-700",
    dot: "bg-slate-400",
  };
}

function getCombinedSummary({ market, macro, technical, master }) {
  const marketScore = clampNumber(market?.score);
  const macroScore = clampNumber(macro?.score);
  const technicalScore = clampNumber(technical?.score);
  const combined = Math.round((marketScore + macroScore + technicalScore) / 3);
  const spread = Math.max(marketScore, macroScore, technicalScore) - Math.min(marketScore, macroScore, technicalScore);
  const confidence = Math.max(32, Math.min(92, 100 - spread));
  const tone = scoreTone(combined);
  const summary = trimSentence(
    master?.summary || master?.outlook,
    "Scant markt-, macro- en technische context als een gezamenlijke beslislaag."
  );

  return {
    score: combined,
    confidence,
    bias: master?.bias || tone.label,
    outlook: master?.outlook || tone.label,
    summary,
    tone,
  };
}

function buildRows(items, locale) {
  const source = Array.isArray(items) ? items : [];

  return source.map((item, index) => {
    const name = item?.name || item?.indicator || `indicator_${index}`;
    const score = clampNumber(item?.score, 50);
    const tone = scoreTone(score);
    const assessment = trimSentence(
      item?.interpretation || item?.uitleg || item?.action,
      tone.label
    );

    return {
      id: `${name}-${index}`,
      name,
      label: prettifyName(name),
      value: formatIndicatorValue(name, item?.value ?? item?.waarde, locale),
      direction: toDirectionLabel(item, score),
      score,
      assessment,
      signalLabel: tone.label,
      signalTone: tone,
      timestamp: item?.timestamp || item?.date || null,
      raw: item,
    };
  });
}

function SummaryPill({ label, value, tone = "neutral" }) {
  const toneClass =
    tone === "positive"
      ? "border-emerald-200 bg-emerald-50 text-emerald-700"
      : tone === "negative"
      ? "border-red-200 bg-red-50 text-red-700"
      : "border-slate-200 bg-white text-slate-700";

  return (
    <div className={`inline-flex items-center gap-2 rounded-full border px-3 py-1.5 text-[11px] font-black ${toneClass}`}>
      <span className="uppercase tracking-[0.22em]">{label}</span>
      <span className="tracking-tight">{value}</span>
    </div>
  );
}

function SectionScorePill({ score }) {
  const tone = scoreTone(score);
  return (
    <div className={`inline-flex items-center rounded-full border px-3 py-1 text-[11px] font-black uppercase tracking-[0.22em] ${tone.pill}`}>
      {clampNumber(score)}/100
    </div>
  );
}

function EvidenceSection({
  id,
  title,
  eyebrow,
  icon: Icon,
  score,
  bias,
  summary,
  rows,
  expandedRowKey,
  onToggleRow,
  action,
  renderExpandedActions,
  emptyState,
}) {
  return (
    <section className="rounded-[28px] border border-slate-200/80 bg-white shadow-[0_20px_60px_-42px_rgba(15,23,42,0.35)]">
      <div className="flex flex-wrap items-start justify-between gap-4 border-b border-slate-100 px-5 py-5">
        <div className="min-w-0">
          <div className="flex items-center gap-2 text-[10px] font-black uppercase tracking-[0.26em] text-blue-600">
            <Icon size={12} />
            {eyebrow}
          </div>
          <div className="mt-2 flex items-center gap-3">
            <h2 className="text-2xl font-black tracking-tight text-slate-950">{title}</h2>
            <SectionScorePill score={score} />
          </div>
          <div className="mt-2 text-[11px] font-black uppercase tracking-[0.22em] text-slate-400">
            {bias}
          </div>
          <p className="mt-3 max-w-2xl text-sm font-medium leading-relaxed text-slate-500">
            {summary}
          </p>
        </div>
        {action}
      </div>

      <div className="overflow-x-auto">
        <table className="min-w-full table-auto">
          <thead>
            <tr className="border-b border-slate-100 text-left text-[10px] font-black uppercase tracking-[0.24em] text-slate-400">
              <th className="px-5 py-3">Indicator</th>
              <th className="px-4 py-3 text-right">Huidige waarde</th>
              <th className="px-4 py-3">Richting</th>
              <th className="px-4 py-3 text-right">Score</th>
              <th className="px-5 py-3">Beoordeling</th>
            </tr>
          </thead>
          <tbody>
            {rows.length ? (
              rows.map((row) => {
                const expanded = expandedRowKey === `${id}:${row.id}`;
                return (
                  <>
                    <tr
                      key={`${id}:${row.id}`}
                      className="cursor-pointer border-b border-slate-100/80 transition hover:bg-slate-50/70"
                      onClick={() => onToggleRow(`${id}:${row.id}`)}
                    >
                      <td className="px-5 py-4">
                        <div className="flex items-center gap-3">
                          <button
                            type="button"
                            tabIndex={-1}
                            className={`flex h-8 w-8 items-center justify-center rounded-full border transition ${
                              expanded
                                ? "border-blue-200 bg-blue-50 text-blue-600"
                                : "border-slate-200 bg-white text-slate-400"
                            }`}
                          >
                            <ChevronDown size={14} className={`transition ${expanded ? "rotate-180" : ""}`} />
                          </button>
                          <div>
                            <div className="text-sm font-black text-slate-900">{row.label}</div>
                            <div className="mt-1 text-[11px] font-medium text-slate-400">{row.signalLabel}</div>
                          </div>
                        </div>
                      </td>
                      <td className="px-4 py-4 text-right text-sm font-black text-slate-900">{row.value}</td>
                      <td className="px-4 py-4">
                        <div className="inline-flex items-center gap-2 rounded-full bg-slate-100 px-3 py-1 text-[11px] font-bold text-slate-600">
                          <span className={`h-2 w-2 rounded-full ${row.signalTone.dot}`} />
                          {row.direction}
                        </div>
                      </td>
                      <td className="px-4 py-4 text-right">
                        <div className={`text-sm font-black ${row.signalTone.text}`}>{row.score}</div>
                      </td>
                      <td className="px-5 py-4 text-sm font-medium leading-relaxed text-slate-500">
                        {row.assessment}
                      </td>
                    </tr>

                    {expanded ? (
                      <tr key={`${id}:${row.id}:expanded`} className="border-b border-slate-100 bg-slate-50/65">
                        <td colSpan={5} className="px-5 py-4">
                          <div className="grid gap-4 lg:grid-cols-[1.5fr_0.8fr]">
                            <div>
                              <div className="text-[10px] font-black uppercase tracking-[0.24em] text-slate-400">
                                Verdieping
                              </div>
                              <p className="mt-2 text-sm font-medium leading-relaxed text-slate-600">
                                {row.raw?.interpretation || row.raw?.uitleg || row.raw?.action || "Nog geen extra interpretatie beschikbaar."}
                              </p>
                            </div>

                            <div className="flex flex-col gap-3 lg:items-end">
                              <div className="text-right">
                                <div className="text-[10px] font-black uppercase tracking-[0.24em] text-slate-400">
                                  Laatste signaal
                                </div>
                                <div className="mt-2 text-sm font-black text-slate-900">
                                  {row.timestamp ? formatTimestamp(row.timestamp) : "Live"}
                                </div>
                              </div>
                              {renderExpandedActions ? renderExpandedActions(row) : null}
                            </div>
                          </div>
                        </td>
                      </tr>
                    ) : null}
                  </>
                );
              })
            ) : (
              <tr>
                <td colSpan={5} className="px-5 py-12 text-center text-sm font-semibold text-slate-400">
                  {emptyState}
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </section>
  );
}

export default function AssetWorkspaceV3({ initialTab = "market", variant = "v3" }) {
  const pathname = usePathname();
  const router = useRouter();
  const searchParams = useSearchParams();
  const { selectedAsset, setSelectedAsset, availableAssets = [] } = useAsset();
  const { locale } = useTranslation();
  const symbolFromUrl = searchParams.get("symbol")?.toUpperCase();
  const activeSymbol = symbolFromUrl || selectedAsset || "BTC";
  const [macroTimeframe] = useState("day");
  const [technicalTimeframe] = useState("day");
  const [expandedRowKey, setExpandedRowKey] = useState(null);
  const [technicalConfigModal, setTechnicalConfigModal] = useState(null);
  const appliedIndicatorsRef = useRef(new Set());

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

  const {
    availableIndicators,
    addMarket,
    btcLive,
    loading: marketLoading,
    marketDayData,
  } = useMarketData(activeSymbol, {
    includeDailyScores: false,
    includeSevenDayData: false,
    includeForwardData: false,
  });

  const {
    macroData,
    addMacroIndicator,
    loading: macroLoading,
    removeMacroIndicator,
  } = useMacroData(macroTimeframe, activeSymbol);

  const {
    technicalData,
    addTechnicalIndicator,
    loading: technicalLoading,
    removeTechnicalIndicator,
  } = useTechnicalData(technicalTimeframe, activeSymbol, { includeScoreSummary: false });

  const { market, macro, technical, master } = useScoresData(activeSymbol, {
    includeHistory: false,
    includeMaster: true,
  });

  useEffect(() => {
    if (!marketIndicatorFromUrl) return;
    const key = `market:${marketIndicatorFromUrl}`;
    if (appliedIndicatorsRef.current.has(key)) return;

    appliedIndicatorsRef.current.add(key);
    Promise.resolve(addMarket(marketIndicatorFromUrl)).catch((error) => {
      console.error("Failed to add market indicator from command search:", error);
    });
  }, [addMarket, marketIndicatorFromUrl]);

  useEffect(() => {
    if (!macroIndicatorFromUrl) return;
    const key = `macro:${macroIndicatorFromUrl}`;
    if (appliedIndicatorsRef.current.has(key)) return;

    appliedIndicatorsRef.current.add(key);
    Promise.resolve(addMacroIndicator(macroIndicatorFromUrl)).catch((error) => {
      console.error("Failed to add macro indicator from command search:", error);
    });
  }, [addMacroIndicator, macroIndicatorFromUrl]);

  useEffect(() => {
    if (!technicalIndicatorFromUrl) return;
    const key = `technical:${technicalIndicatorFromUrl}`;
    if (appliedIndicatorsRef.current.has(key)) return;

    appliedIndicatorsRef.current.add(key);
    Promise.resolve(addTechnicalIndicator(technicalIndicatorFromUrl))
      .then(() => {
        if (indicatorAction !== "select") {
          setExpandedRowKey(`technical:${technicalIndicatorFromUrl}-0`);
          setTechnicalConfigModal(technicalIndicatorFromUrl);
        }
      })
      .catch((error) => {
        console.error("Failed to add technical indicator from command search:", error);
      });
  }, [addTechnicalIndicator, indicatorAction, technicalIndicatorFromUrl]);

  const assetOptions = useMemo(() => {
    const base =
      Array.isArray(availableAssets) && availableAssets.length
        ? availableAssets
        : ["BTC", "ETH", "SOL", "ADA", "DOT"];
    return Array.from(new Set([activeSymbol, ...base]));
  }, [activeSymbol, availableAssets]);

  const combinedSummary = useMemo(
    () => getCombinedSummary({ market, macro, technical, master }),
    [macro, market, master, technical]
  );

  const sections = useMemo(() => {
    const marketRows = buildRows(marketDayData, locale);
    const macroRows = buildRows(macroData, locale);
    const technicalRows = buildRows(technicalData, locale);

    return [
      {
        id: "market",
        title: SECTION_META.market.label,
        eyebrow: SECTION_META.market.eyebrow,
        icon: SECTION_META.market.icon,
        score: market?.score,
        bias: market?.bias || market?.trend || "Neutraal",
        summary: trimSentence(
          market?.uitleg,
          `Prijs, volume, participatie en liquiditeit voor ${activeSymbol}.`
        ),
        rows: marketRows,
        emptyState: marketLoading ? "Marktdata laden..." : SECTION_META.market.empty,
      },
      {
        id: "macro",
        title: SECTION_META.macro.label,
        eyebrow: SECTION_META.macro.eyebrow,
        icon: SECTION_META.macro.icon,
        score: macro?.score,
        bias: macro?.bias || macro?.trend || "Neutraal",
        summary: trimSentence(
          macro?.uitleg,
          `Regime, yields, flows en hogere macrodruk rond ${activeSymbol}.`
        ),
        rows: macroRows,
        emptyState: macroLoading ? "Macrodata laden..." : SECTION_META.macro.empty,
      },
      {
        id: "technical",
        title: SECTION_META.technical.label,
        eyebrow: SECTION_META.technical.eyebrow,
        icon: SECTION_META.technical.icon,
        score: technical?.score,
        bias: technical?.bias || technical?.trend || "Neutraal",
        summary: trimSentence(
          technical?.uitleg,
          `Trend, momentum en actieve indicatorlogica voor ${activeSymbol}.`
        ),
        rows: technicalRows,
        emptyState: technicalLoading ? "Technische data laden..." : SECTION_META.technical.empty,
      },
    ];
  }, [activeSymbol, locale, macro, macroData, macroLoading, market, marketDayData, marketLoading, technical, technicalData, technicalLoading]);

  const handleAssetChange = (event) => {
    const nextSymbol = String(event.target.value || activeSymbol).toUpperCase();
    setSelectedAsset(nextSymbol);
    router.push(buildContextHref({ pathname, symbol: nextSymbol, context: initialTab, variant }), {
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
    <section className="space-y-5">
      <section className="rounded-[32px] border border-slate-200/80 bg-white p-5 shadow-[0_22px_60px_-42px_rgba(15,23,42,0.38)] lg:p-6">
        <div className="flex flex-col gap-5 xl:flex-row xl:items-start xl:justify-between">
          <div className="min-w-0">
            <div className="flex items-center gap-2 text-[10px] font-black uppercase tracking-[0.28em] text-blue-600">
              <Brain size={12} />
              Asset Intelligence Overview
            </div>

            <div className="mt-3 flex flex-wrap items-center gap-x-3 gap-y-2">
              <h1 className="text-4xl font-black tracking-tight text-slate-950 lg:text-5xl">
                {activeSymbol} Analyse
              </h1>
              <span className="text-sm font-semibold text-slate-400">·</span>
              <span className="text-lg font-black text-slate-950">{formatPrice(btcLive?.price, locale)}</span>
              <span className="text-sm font-semibold text-slate-400">·</span>
              <span className={`text-lg font-black ${Number(btcLive?.change_24h) >= 0 ? "text-emerald-600" : "text-red-600"}`}>
                {formatPercent(btcLive?.change_24h)}
              </span>
              <span className="text-sm font-semibold text-slate-400">·</span>
              <span className="text-sm font-black uppercase tracking-[0.18em] text-slate-500">1D</span>
              <span className="text-sm font-semibold text-slate-400">·</span>
              <span className="text-sm font-semibold text-slate-500">
                Updated {formatTimestamp(btcLive?.timestamp, locale)}
              </span>
            </div>

            <div className="mt-4 flex flex-wrap gap-2">
              <SummaryPill label="Combined score" value={`${combinedSummary.score}/100`} />
              <SummaryPill label="Bias" value={combinedSummary.bias} tone={combinedSummary.tone.label === "Positief" ? "positive" : combinedSummary.tone.label === "Negatief" ? "negative" : "neutral"} />
              <SummaryPill label="Confidence" value={`${combinedSummary.confidence}%`} />
            </div>

            <div className="mt-4 rounded-[24px] border border-slate-200 bg-slate-50/75 p-4">
              <div className="flex items-center gap-2 text-[10px] font-black uppercase tracking-[0.24em] text-slate-400">
                <Sparkles size={12} />
                FINN conclusie
              </div>
              <p className="mt-2 text-sm font-medium leading-relaxed text-slate-600">
                {combinedSummary.summary}
              </p>
            </div>
          </div>

          <div className="w-full rounded-[26px] border border-slate-200 bg-slate-50/70 p-4 xl:max-w-[320px]">
            <div className="text-[10px] font-black uppercase tracking-[0.24em] text-slate-400">
              Asset wisselen
            </div>
            <div className="mt-3 flex items-center gap-3">
              <div className="flex h-11 w-11 items-center justify-center rounded-2xl bg-blue-600 text-sm font-black uppercase tracking-[0.14em] text-white">
                {activeSymbol.slice(0, 3)}
              </div>
              <div className="min-w-0">
                <div className="text-lg font-black text-slate-950">{activeSymbol}</div>
                <div className="text-sm font-medium text-slate-500">
                  Zelfde analysecanvas, andere assetcontext.
                </div>
              </div>
            </div>
            <select
              value={activeSymbol}
              onChange={handleAssetChange}
              className="mt-4 w-full rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm font-black uppercase tracking-[0.18em] text-slate-900 outline-none transition focus:border-blue-500"
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
        {sections.map((section) => (
          <EvidenceSection
            key={section.id}
            id={section.id}
            title={section.title}
            eyebrow={section.eyebrow}
            icon={section.icon}
            score={section.score}
            bias={section.bias}
            summary={section.summary}
            rows={section.rows}
            expandedRowKey={expandedRowKey}
            onToggleRow={(key) => setExpandedRowKey((current) => (current === key ? null : key))}
            emptyState={section.emptyState}
            action={
              section.id === "technical" ? (
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
            renderExpandedActions={
              section.id === "technical"
                ? (row) => (
                    <div className="flex flex-wrap justify-end gap-2">
                      <button
                        type="button"
                        onClick={(event) => {
                          event.stopPropagation();
                          setTechnicalConfigModal(row.name);
                        }}
                        className="inline-flex items-center gap-2 rounded-2xl border border-blue-200 bg-blue-50 px-3 py-2 text-[11px] font-black uppercase tracking-[0.18em] text-blue-700 transition hover:bg-blue-100"
                      >
                        <Settings2 size={12} />
                        Bewerken
                      </button>
                      <button
                        type="button"
                        onClick={(event) => {
                          event.stopPropagation();
                          removeTechnicalIndicator(row.name);
                          setExpandedRowKey(null);
                        }}
                        className="inline-flex items-center gap-2 rounded-2xl border border-slate-200 bg-white px-3 py-2 text-[11px] font-black uppercase tracking-[0.18em] text-slate-600 transition hover:border-red-200 hover:text-red-600"
                      >
                        <Target size={12} />
                        Verwijderen
                      </button>
                    </div>
                  )
                : section.id === "macro"
                ? (row) => (
                    <button
                      type="button"
                      onClick={(event) => {
                        event.stopPropagation();
                        removeMacroIndicator(row.name);
                        setExpandedRowKey(null);
                      }}
                      className="inline-flex items-center gap-2 rounded-2xl border border-slate-200 bg-white px-3 py-2 text-[11px] font-black uppercase tracking-[0.18em] text-slate-600 transition hover:border-red-200 hover:text-red-600"
                    >
                      <Target size={12} />
                      Verwijderen
                    </button>
                  )
                : null
            }
          />
        ))}
      </section>

      <div className="rounded-[28px] border border-slate-200/80 bg-white p-4 shadow-[0_16px_50px_-42px_rgba(15,23,42,0.35)]">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <div className="text-[10px] font-black uppercase tracking-[0.24em] text-slate-400">
              Analyseflow
            </div>
            <p className="mt-1 text-sm font-medium text-slate-500">
              Markt, Macro en Technisch blijven altijd zichtbaar. Klik alleen op een rij voor verdieping.
            </p>
          </div>
          <div className="inline-flex items-center gap-2 rounded-full border border-slate-200 bg-slate-50 px-4 py-2 text-[11px] font-black uppercase tracking-[0.18em] text-slate-600">
            <ArrowRight size={12} />
            Eén canvas, drie evidence-lijsten
          </div>
        </div>
      </div>

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
