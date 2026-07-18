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
  Save,
  Settings2,
  Sliders,
  Target,
  TrendingUp,
  X,
} from "lucide-react";

import { useAsset } from "@/app/providers/AssetProvider";
import { useTranslation } from "@/app/providers/I18nProvider";
import { useMarketData } from "@/hooks/useMarketData";
import { useMacroData } from "@/hooks/useMacroData";
import { useTechnicalData } from "@/hooks/useTechnicalData";
import { useScoresData } from "@/hooks/useScoresData";
import { useWatchlist } from "@/hooks/useWatchlist";
import IndicatorConfigModal from "@/components/scoring/IndicatorConfigModal";
import { fetchLatestPrice } from "@/lib/api/market";
import { getDailyScores } from "@/lib/api/scores";
import { useOverviewSnapshot } from "@/hooks/useOverviewSnapshot";
import TradingViewSmartChart from "@/components/charts/TradingViewSmartChart";
import GlobalMarketDecisionCard from "@/components/dashboard/GlobalMarketDecisionCard";

const SEARCH_OPEN_EVENT = "finn-command-search:open";

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
  change_24h: "Prijsverandering 24 uur",
  change_7d: "Prijsverandering 7 dagen",
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
  volume_change_24h: "Volumeverandering 24 uur",
  volume_trend: "Volume-trend",
};

const ASSET_NAMES = {
  BTC: "Bitcoin",
  ETH: "Ethereum",
  SOL: "Solana",
  ADA: "Cardano",
  DOT: "Polkadot",
};

const ASSET_GROUPS = [
  { id: "crypto", label: "Crypto", active: true },
  { id: "stocks", label: "Stocks", active: false },
  { id: "etf", label: "ETF", active: false },
];

function getUiCopy(locale = "nl") {
  const normalized = String(locale || "nl").toLowerCase();
  if (normalized.startsWith("en")) {
    return {
      activeAnalysis: "Active analysis",
      updated: "Updated",
      combinedScore: "Combined score",
      confidence: "Confidence",
      bias: "Bias",
      watchlist: "Watchlist",
      addAsset: "Add asset",
      latest: "Last",
      chartTitle: "TradingView chart",
      chartClose: "Close chart",
      chartOpen: "Open chart",
      contextScores: "Context scores",
      setupRoute: "Setup via My Plan",
      marketRegime: "Market regime",
      addIndicator: "Add indicator",
      positive: "Positive",
      negative: "Negative",
      neutral: "Neutral",
      unavailable: "Insufficient data",
      market: "Market",
      macro: "Macro",
      technical: "Technical",
      combined: "Combined",
      nextStep: "Next step",
      planBridgeTitle: "Continue this setup in My Plan",
      planBridgeDescription: "Review setup quality, position sizing and risk/reward before taking action.",
      openMyPlan: "Open My Plan",
      setupScore: "Setup score",
      setup: "Setup",
      tuneEngine: "Tune engine",
      closeTuning: "Close tuning",
      weight: "Weight",
      weightInfluence: "Influence on the combined score",
      balancedWeights: "The weights add up to 100%.",
      unbalancedWeights: "The weights must add up to 100%.",
      applyWeights: "Apply weights",
      savingWeights: "Saving...",
      day: "Day",
      week: "Week",
      month: "Month",
      quarter: "Quarter",
      macroPeriod: "Macro period",
    };
  }
  if (normalized.startsWith("de")) {
    return {
      activeAnalysis: "Aktive analyse",
      updated: "Aktualisiert",
      combinedScore: "Kombinierter score",
      confidence: "Vertrauen",
      bias: "Bias",
      watchlist: "Watchlist",
      addAsset: "Asset hinzufügen",
      latest: "Letzte",
      chartTitle: "TradingView-chart",
      chartClose: "Chart schließen",
      chartOpen: "Chart öffnen",
      contextScores: "Kontext-scores",
      setupRoute: "Setup über Mein Plan",
      marketRegime: "Marktregime",
      addIndicator: "Indikator hinzufügen",
      positive: "Positiv",
      negative: "Negativ",
      neutral: "Neutral",
      unavailable: "Unzureichende Daten",
      market: "Markt",
      macro: "Makro",
      technical: "Technisch",
      combined: "Kombiniert",
      nextStep: "Nächster Schritt",
      planBridgeTitle: "Dieses Setup in Mein Plan ausarbeiten",
      planBridgeDescription: "Prüfe Setup-Qualität, Positionsgröße und Risiko-Rendite vor der Ausführung.",
      openMyPlan: "Mein Plan öffnen",
      setupScore: "Setup-Score",
      setup: "Setup",
      tuneEngine: "Engine abstimmen",
      closeTuning: "Abstimmung schließen",
      weight: "Gewichtung",
      weightInfluence: "Einfluss auf den kombinierten Score",
      balancedWeights: "Die Gewichtungen ergeben zusammen 100 %.",
      unbalancedWeights: "Die Gewichtungen müssen zusammen 100 % ergeben.",
      applyWeights: "Gewichtungen anwenden",
      savingWeights: "Speichern...",
      day: "Tag",
      week: "Woche",
      month: "Monat",
      quarter: "Quartal",
      macroPeriod: "Makrozeitraum",
    };
  }
  return {
    activeAnalysis: "Actieve analyse",
    updated: "Bijgewerkt",
    combinedScore: "Gecombineerde score",
    confidence: "Vertrouwen",
    bias: "Bias",
    watchlist: "Watchlist",
    addAsset: "Asset toevoegen",
    latest: "Laatste",
    chartTitle: "TradingView-chart",
    chartClose: "Chart sluiten",
    chartOpen: "Chart openen",
    contextScores: "Contextscores",
    setupRoute: "Setup via Mijn Plan",
    marketRegime: "Marktregime",
    addIndicator: "Indicator toevoegen",
    positive: "Positief",
    negative: "Negatief",
    neutral: "Neutraal",
    unavailable: "Onvoldoende data",
    market: "Markt",
    macro: "Macro",
    technical: "Technisch",
    combined: "Gecombineerd",
    nextStep: "Volgende stap",
    planBridgeTitle: "Werk deze setup uit in Mijn Plan",
    planBridgeDescription: "Controleer setupkwaliteit, positiegrootte en risk/reward voordat je handelt.",
    openMyPlan: "Open Mijn Plan",
    setupScore: "Setupscore",
    setup: "Setup",
    tuneEngine: "Engine afstemmen",
    closeTuning: "Afstemmen sluiten",
    weight: "Weging",
    weightInfluence: "Invloed op de gecombineerde score",
    balancedWeights: "De wegingen komen samen uit op 100%.",
    unbalancedWeights: "De wegingen moeten samen op 100% uitkomen.",
    applyWeights: "Wegingen toepassen",
    savingWeights: "Opslaan...",
    day: "Dag",
    week: "Week",
    month: "Maand",
    quarter: "Kwartaal",
    macroPeriod: "Macroperiode",
  };
}

const DEFAULT_INTELLIGENCE_WEIGHTS = {
  market: 1 / 3,
  macro: 1 / 3,
  technical: 1 / 3,
};

const MACRO_TIMEFRAMES = ["day", "week", "month", "quarter"];

function normalizeWeights(weights) {
  const next = Object.fromEntries(
    Object.keys(DEFAULT_INTELLIGENCE_WEIGHTS).map((key) => {
      const value = Number(weights?.[key]);
      return [key, Number.isFinite(value) && value >= 0 ? value : DEFAULT_INTELLIGENCE_WEIGHTS[key]];
    })
  );
  const total = Object.values(next).reduce((sum, value) => sum + value, 0);
  if (!total) return { ...DEFAULT_INTELLIGENCE_WEIGHTS };
  return Object.fromEntries(Object.entries(next).map(([key, value]) => [key, value / total]));
}

function normalizeScore(value) {
  if (value === null || value === undefined || value === "") return null;
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) return null;
  return Math.max(0, Math.min(100, parsed));
}

function formatScore(value) {
  const score = normalizeScore(value);
  return score === null ? "—" : Math.round(score);
}

function summarizeContextScores(values, ui) {
  const scores = values.map(normalizeScore).filter((value) => value !== null);
  if (!scores.length) {
    return {
      score: null,
      confidence: null,
      bias: ui.unavailable,
      tone: scoreTone(null, ui),
    };
  }

  const average = Math.round(scores.reduce((sum, value) => sum + value, 0) / scores.length);
  const spread = scores.length > 1 ? Math.max(...scores) - Math.min(...scores) : 100;
  const coverage = scores.length / values.length;
  const confidence = Math.round(Math.max(0, 100 - spread) * coverage);
  const tone = scoreTone(average, ui);

  return { score: average, confidence, bias: tone.label, tone };
}

function summarizeWeightedScores(scores, weights, ui) {
  const normalizedWeights = normalizeWeights(weights);
  const available = Object.entries(normalizedWeights)
    .map(([key, weight]) => ({ score: normalizeScore(scores?.[key]), weight }))
    .filter((item) => item.score !== null && item.weight > 0);

  if (!available.length) return summarizeContextScores([], ui);

  const includedWeight = available.reduce((sum, item) => sum + item.weight, 0);
  const weightedScore = Math.round(
    available.reduce((sum, item) => sum + item.score * item.weight, 0) / includedWeight
  );
  const baseSummary = summarizeContextScores(available.map((item) => item.score), ui);
  const tone = scoreTone(weightedScore, ui);

  return {
    ...baseSummary,
    score: weightedScore,
    bias: tone.label,
    tone,
  };
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

function formatPercent(value, digits = 2) {
  const numericValue = Number(value);
  if (!Number.isFinite(numericValue)) return "—";
  return `${numericValue >= 0 ? "+" : ""}${numericValue.toFixed(digits)}%`;
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
  if (source.length <= 150) return source;
  return `${source.slice(0, 147).trim()}...`;
}

function prettifyName(name) {
  if (!name) return "Onbekende indicator";
  const normalized = String(name).trim();
  const lowered = normalized.toLowerCase();
  if (INDICATOR_LABELS[lowered]) return INDICATOR_LABELS[lowered];
  return normalized.replace(/_/g, " ").replace(/\b([a-z])/g, (match) => match.toUpperCase());
}

function formatCompactNumber(value, locale, digits = 2) {
  return new Intl.NumberFormat(locale || "en-US", {
    maximumFractionDigits: digits,
  }).format(value);
}

function formatMagnitude(value, locale) {
  const numericValue = Number(value);
  if (!Number.isFinite(numericValue)) return "—";
  if (Math.abs(numericValue) >= 1e12) return `${formatCompactNumber(numericValue / 1e12, locale, 2)}T`;
  if (Math.abs(numericValue) >= 1e9) return `${formatCompactNumber(numericValue / 1e9, locale, 2)} mld.`;
  if (Math.abs(numericValue) >= 1e6) return `${formatCompactNumber(numericValue / 1e6, locale, 2)} mln.`;
  return formatCompactNumber(numericValue, locale, 2);
}

function normalizePotentialRatio(value, { percent = false } = {}) {
  const numericValue = Number(value);
  if (!Number.isFinite(numericValue)) return null;
  if (!percent) return numericValue;
  if (Math.abs(numericValue) <= 1) return numericValue * 100;
  return numericValue;
}

function formatIndicatorValue(name, value, locale) {
  if (value === null || value === undefined || value === "") return "Onvoldoende data";

  const label = String(name || "").toLowerCase();
  const raw = typeof value === "string" ? value.trim() : value;
  const rawString = typeof raw === "string" ? raw : "";
  const numericValue = Number(
    typeof raw === "string"
      ? raw.replace(/,/g, ".").replace(/[^0-9.+-]/g, "")
      : raw
  );

  if (typeof raw === "string" && /buy|sell|above|below|bull|bear|neutral|hoog|laag|stijg|daal|trend/i.test(rawString)) {
    return raw;
  }

  if (label === "ma_200" && Number.isFinite(numericValue)) {
    return numericValue >= 1 ? "Boven MA200" : "Onder MA200";
  }

  if ((label.includes("change") || label.includes("dominance")) && Number.isFinite(numericValue)) {
    const percentValue = normalizePotentialRatio(numericValue, { percent: true });
    return formatPercent(percentValue, 2);
  }

  if ((label === "us10y" || label === "us2y") && Number.isFinite(numericValue)) {
    const percentValue = normalizePotentialRatio(numericValue, { percent: true });
    return `${formatCompactNumber(percentValue, locale, 2)}%`;
  }

  if (label.includes("volume") || label.includes("flow")) {
    if (!Number.isFinite(numericValue) || numericValue <= 0) return "Onvoldoende data";
    return `$${formatMagnitude(numericValue, locale)}`;
  }

  if (label.includes("price")) {
    if (!Number.isFinite(numericValue)) return "Onvoldoende data";
    if (Math.abs(numericValue) <= 1 && label.includes("change")) {
      return formatPercent(numericValue * 100, 2);
    }
    return formatPrice(numericValue, locale);
  }

  if (label.includes("rsi") || label.includes("fear") || label.includes("dxy")) {
    if (!Number.isFinite(numericValue)) return "Onvoldoende data";
    return formatCompactNumber(numericValue, locale, 2);
  }

  if (label.includes("participation") || label.includes("volatility")) {
    if (!Number.isFinite(numericValue)) return "Onvoldoende data";
    const percentValue = normalizePotentialRatio(numericValue, { percent: true });
    return `${formatCompactNumber(percentValue, locale, 2)}%`;
  }

  if (Number.isFinite(numericValue)) {
    return formatCompactNumber(numericValue, locale, 2);
  }

  return rawString || "Onvoldoende data";
}

function toDirectionLabel(item, score) {
  const trendSource = String(item?.trend || item?.action || item?.interpretation || "").trim().toLowerCase();
  if (trendSource.includes("improv") || trendSource.includes("stijg") || trendSource.includes("herstel")) return "Verbetert";
  if (trendSource.includes("verslecht") || trendSource.includes("dal") || trendSource.includes("tegenwind")) return "Verslechtert";
  if (trendSource.includes("stable") || trendSource.includes("stab")) return "Stabiel";
  if (trendSource.includes("buy")) return "Actief";
  if (trendSource.includes("sell")) return "Verzwakt";
  if (score === null) return "Onvoldoende data";
  if (score >= 70) return "Verbetert";
  if (score <= 35) return "Verslechtert";
  return "Stabiel";
}

function scoreTone(value, ui = getUiCopy("nl")) {
  const numericValue = normalizeScore(value);
  if (numericValue === null) {
    return {
      label: ui.unavailable,
      pill: "border-slate-200 bg-slate-50 text-slate-500",
      text: "text-slate-500",
      dot: "bg-slate-300",
    };
  }
  if (numericValue >= 70) {
    return {
      label: ui.positive,
      pill: "border-emerald-200 bg-emerald-50 text-emerald-700",
      text: "text-emerald-700",
      dot: "bg-emerald-500",
    };
  }
  if (numericValue <= 35) {
    return {
      label: ui.negative,
      pill: "border-red-200 bg-red-50 text-red-700",
      text: "text-red-700",
      dot: "bg-red-500",
    };
  }
  return {
    label: ui.neutral,
    pill: "border-slate-200 bg-slate-50 text-slate-700",
    text: "text-slate-700",
    dot: "bg-slate-400",
  };
}

function fallbackAssessment(label, direction, tone) {
  return `${label} ${direction === "Stabiel" ? "blijft stabiel" : direction === "Verbetert" ? "verbetert" : direction === "Verslechtert" ? "verslechtert" : "blijft actief"} en geeft nu een ${tone.label.toLowerCase()} signaal.`;
}

function buildRows(items, locale) {
  const source = Array.isArray(items) ? items : [];

  return source.map((item, index) => {
    const name = item?.name || item?.indicator || `indicator_${index}`;
    const label = prettifyName(name);
    const score = normalizeScore(item?.score);
    const tone = scoreTone(score);
    const direction = toDirectionLabel(item, score);
    const detail = trimSentence(
      item?.interpretation || item?.uitleg || "",
      fallbackAssessment(label, direction, tone)
    );

    return {
      id: `${name}-${index}`,
      name,
      label,
      value: formatIndicatorValue(name, item?.value ?? item?.waarde, locale),
      direction,
      score,
      signalTone: tone,
      scoreLabel: score === null ? tone.label : `${tone.label} · ${Math.round(score)}`,
      detail,
      timestamp: item?.timestamp || item?.date || null,
      raw: item,
    };
  });
}

function buildSectionInsight(sectionId, sectionScore, rows) {
  const score = normalizeScore(sectionScore);
  const focus = rows.slice(0, 2).map((row) => row.label.toLowerCase());

  if (score === null) return "Onvoldoende scoredata voor een betrouwbare groepsconclusie.";

  if (sectionId === "market") {
    if (score <= 35) {
      return focus.length
        ? `Prijsactie oogt zwak en bevestiging vanuit ${focus.join(" en ")} blijft beperkt.`
        : "Prijsactie oogt zwak en bevestiging vanuit volume en liquiditeit blijft beperkt.";
    }
    if (score >= 70) {
      return focus.length
        ? `${focus[0][0].toUpperCase()}${focus[0].slice(1)} ondersteunt de beweging en marktinternals blijven meewerken.`
        : "Prijsactie en marktinternals ondersteunen de beweging.";
    }
    return "Marktbeeld is gemengd: beweging is zichtbaar, maar bevestiging blijft nog onvolledig.";
  }

  if (sectionId === "macro") {
    if (score <= 35) return "Stijgende yields en een sterke dollar blijven macro-tegenwind geven.";
    if (score >= 70) return "Macroregime werkt mee en hogere druklagen ondersteunen het risicobeeld.";
    return "Macrocontext blijft gemengd en vraagt om bevestiging vanuit rates, flows en sentiment.";
  }

  if (score <= 35) return "Trendstructuur is kwetsbaar en momentum levert nog geen sterke bevestiging.";
  if (score >= 70) return "Trend en actieve indicatoren staan op één lijn en ondersteunen follow-through.";
  return "Technisch beeld is werkbaar, maar momentum en trendbevestiging blijven neutraal.";
}

function ScoreOverview({ market, macro, technical, combined, weights, loading, onSaveWeights, ui }) {
  const [isEditing, setIsEditing] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [localWeights, setLocalWeights] = useState(() => normalizeWeights(weights));

  useEffect(() => {
    if (!isEditing) setLocalWeights(normalizeWeights(weights));
  }, [isEditing, weights]);

  const items = [
    {
      id: "market",
      label: ui.market,
      score: normalizeScore(market?.score),
    },
    {
      id: "macro",
      label: ui.macro,
      score: normalizeScore(macro?.score),
    },
    {
      id: "technical",
      label: ui.technical,
      score: normalizeScore(technical?.score),
    },
    {
      id: "combined",
      label: ui.combined,
      score: normalizeScore(combined?.score),
    },
  ];

  const weightItems = [
    { id: "market", label: ui.market, score: normalizeScore(market?.score) },
    { id: "macro", label: ui.macro, score: normalizeScore(macro?.score) },
    { id: "technical", label: ui.technical, score: normalizeScore(technical?.score) },
  ];

  const handleWeightChange = (key, nextValue) => {
    const value = Math.max(0, Math.min(1, Number(nextValue)));
    setLocalWeights((current) => {
      const otherKeys = Object.keys(current).filter((itemKey) => itemKey !== key);
      const otherTotal = otherKeys.reduce((sum, itemKey) => sum + current[itemKey], 0);
      const remaining = 1 - value;
      const next = { ...current, [key]: value };

      otherKeys.forEach((itemKey) => {
        next[itemKey] = otherTotal > 0
          ? remaining * (current[itemKey] / otherTotal)
          : remaining / otherKeys.length;
      });

      return next;
    });
  };

  const handleSave = async () => {
    setIsSaving(true);
    try {
      await onSaveWeights(localWeights);
      setIsEditing(false);
    } finally {
      setIsSaving(false);
    }
  };

  const totalWeight = Object.values(localWeights).reduce((sum, value) => sum + value, 0);
  const isBalanced = Math.abs(totalWeight - 1) < 0.01;

  return (
    <section className="rounded-[24px] border border-slate-200/80 bg-white shadow-[0_18px_40px_-36px_rgba(15,23,42,0.26)]">
      <div className="flex items-center justify-between gap-3 border-b border-slate-100 px-4 py-3">
        <div className="text-[10px] font-black uppercase tracking-[0.24em] text-blue-600">
          {ui.contextScores}
        </div>
        <button
          type="button"
          onClick={() => setIsEditing((current) => !current)}
          className={`inline-flex items-center gap-2 rounded-full border px-3 py-1.5 text-[9px] font-black uppercase tracking-[0.15em] transition ${
            isEditing
              ? "border-slate-300 bg-slate-900 text-white"
              : "border-slate-200 bg-slate-50 text-slate-600 hover:border-blue-200 hover:text-blue-600"
          }`}
        >
          {isEditing ? <X size={12} /> : <Sliders size={12} />}
          {isEditing ? ui.closeTuning : ui.tuneEngine}
        </button>
      </div>

      <div className="grid gap-2.5 px-4 py-2.5 lg:grid-cols-4">
        {items.map((item) => {
          const tone = scoreTone(item.score, ui);
          const summary = item.id === "combined" ? combined?.bias || tone.label : tone.label;
          return (
            <div key={item.id} className={`rounded-[16px] border px-3.5 py-2.5 ${tone.pill}`}>
              <div className="text-[9px] font-black uppercase tracking-[0.2em] opacity-70">
                {item.label}
              </div>
              <div className="mt-1 flex items-baseline gap-1.5">
                <span className="text-[24px] font-black leading-none tracking-tight">{formatScore(item.score)}</span>
                <span className="text-[11px] font-bold uppercase tracking-[0.12em] opacity-80">
                  {summary}
                </span>
              </div>
            </div>
          );
        })}
      </div>

      {isEditing ? (
        <div className="border-t border-slate-100 bg-slate-50/60 px-4 py-3.5">
          <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
            <div>
              <div className="text-[9px] font-black uppercase tracking-[0.2em] text-slate-500">
                {ui.weightInfluence}
              </div>
              <div className={`mt-0.5 text-[11px] font-semibold ${isBalanced ? "text-emerald-600" : "text-amber-600"}`}>
                {isBalanced ? ui.balancedWeights : ui.unbalancedWeights}
              </div>
            </div>
            <div className="rounded-full border border-slate-200 bg-white px-3 py-1 text-[11px] font-black text-slate-700">
              {Math.round(totalWeight * 100)}%
            </div>
          </div>

          <div className="grid gap-2.5 md:grid-cols-3">
            {weightItems.map((item) => {
              const weight = localWeights[item.id] ?? 0;
              return (
                <div key={item.id} className="rounded-2xl border border-slate-200 bg-white px-3 py-2.5 shadow-sm">
                  <div className="flex items-center justify-between gap-3">
                    <div>
                      <div className="text-[9px] font-black uppercase tracking-[0.16em] text-slate-500">
                        {item.label}
                      </div>
                      <div className="mt-0.5 text-[11px] font-semibold text-slate-400">
                        {ui.weight} · {formatScore(item.score)}/100
                      </div>
                    </div>
                    <div className="text-[18px] font-black tracking-tight text-slate-950">
                      {Math.round(weight * 100)}%
                    </div>
                  </div>
                  <input
                    type="range"
                    min="0"
                    max="1"
                    step="0.05"
                    value={weight}
                    onChange={(event) => handleWeightChange(item.id, event.target.value)}
                    aria-label={`${ui.weight} ${item.label}`}
                    className="mt-2 h-1.5 w-full cursor-pointer appearance-none rounded-full bg-slate-200 accent-blue-600"
                  />
                </div>
              );
            })}
          </div>

          <div className="mt-3 flex justify-end">
            <button
              type="button"
              onClick={handleSave}
              disabled={loading || isSaving || !isBalanced}
              className="inline-flex items-center gap-2 rounded-full bg-blue-600 px-4 py-2.5 text-[10px] font-black uppercase tracking-[0.14em] text-white shadow-sm transition hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-50"
            >
              <Save size={13} />
              {isSaving ? ui.savingWeights : ui.applyWeights}
            </button>
          </div>
        </div>
      ) : null}
    </section>
  );
}

function AnalysisChartSection({ symbol, isOpen, onToggle, ui }) {
  const tvSymbol = `BINANCE:${symbol}USDT`;

  return (
    <section className="rounded-[24px] border border-slate-200/80 bg-white shadow-[0_18px_40px_-36px_rgba(15,23,42,0.26)]">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-100 px-4 py-3">
        <div>
          <div className="text-[10px] font-black uppercase tracking-[0.24em] text-blue-600">
            {ui.chartTitle}
          </div>
          <p className="mt-1 text-[12px] font-medium text-slate-500">
            Prijsstructuur en visueel bewijs voor de actieve assetanalyse.
          </p>
        </div>
        <button
          type="button"
          onClick={onToggle}
          className="inline-flex items-center gap-2 rounded-full border border-slate-200 bg-slate-50 px-3 py-1 text-[10px] font-black uppercase tracking-[0.16em] text-slate-600 transition hover:border-blue-200 hover:text-blue-600"
        >
          {isOpen ? ui.chartClose : ui.chartOpen}
        </button>
      </div>

      {isOpen ? (
        <div className="p-3">
          <TradingViewSmartChart
            symbol={tvSymbol}
            interval="D"
            indicators={[]}
            focusedBotId={null}
            setFocusedBotId={() => {}}
            height={400}
          />
        </div>
      ) : (
        <div className="px-4 py-5 text-[13px] font-medium text-slate-500">
          De chart blijft inklapbaar zodat de bewijslijsten hun leesbare hoogte behouden.
        </div>
      )}
    </section>
  );
}

function PlanBridge({ setup, onOpenPlan, ui }) {
  const setupScore = normalizeScore(setup?.score);
  const scoreLabel = setupScore === null ? "—" : `${Math.round(setupScore)}/100`;

  return (
    <section className="relative overflow-hidden rounded-[24px] border border-blue-100 bg-gradient-to-r from-blue-50/80 via-white to-white px-4 py-3.5 shadow-[0_18px_40px_-38px_rgba(37,99,235,0.45)]">
      <div className="absolute inset-y-0 left-0 w-1 bg-blue-600" />
      <div className="grid gap-4 sm:grid-cols-[minmax(0,1fr)_auto] sm:items-center">
        <div className="flex min-w-0 items-start gap-3">
          <div className="mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-xl border border-blue-100 bg-white text-blue-600 shadow-sm">
            <Target size={17} />
          </div>
          <div className="min-w-0">
            <div className="text-[9px] font-black uppercase tracking-[0.22em] text-blue-600">
              {ui.nextStep}
            </div>
            <h3 className="mt-0.5 text-[15px] font-black tracking-tight text-slate-950">
              {ui.planBridgeTitle}
            </h3>
            <p className="mt-0.5 text-[12px] font-medium leading-5 text-slate-500">
              {ui.planBridgeDescription}
            </p>
          </div>
        </div>

        <div className="flex items-center justify-between gap-3 sm:justify-end">
          <div className="min-w-[92px]">
            <div className="flex items-baseline justify-between gap-2">
              <span className="text-[9px] font-black uppercase tracking-[0.16em] text-slate-400">
                {ui.setupScore}
              </span>
              <span className="text-[13px] font-black text-slate-900">{scoreLabel}</span>
            </div>
            <div className="mt-1.5 h-1.5 overflow-hidden rounded-full bg-slate-200/80">
              <div
                className="h-full rounded-full bg-blue-600 transition-[width] duration-500"
                style={{ width: `${setupScore ?? 0}%` }}
              />
            </div>
          </div>
          <button
            type="button"
            onClick={onOpenPlan}
            className="inline-flex shrink-0 items-center gap-2 rounded-full bg-blue-600 px-4 py-2.5 text-[10px] font-black uppercase tracking-[0.14em] text-white shadow-sm transition hover:bg-blue-700"
          >
            {ui.openMyPlan}
            <ArrowRight size={13} />
          </button>
        </div>
      </div>
    </section>
  );
}

function formatBiasLabel(value, ui = getUiCopy("nl")) {
  const source = String(value || "").trim();
  if (!source || source === "—") return ui.neutral;
  const normalized = source.toLowerCase();
  if (/(bull|posit)/.test(normalized)) return ui.positive;
  if (/(bear|negat)/.test(normalized)) return ui.negative;
  if (/(neutr|stab|side)/.test(normalized)) return ui.neutral;
  return source;
}

function ActiveAssetCard({
  activeSymbol,
  assetName,
  price,
  change24h,
  updatedAt,
  combinedSummary,
  onSelectAsset,
  ui,
}) {
  const changeValue = Number(change24h);
  const changeClass = Number.isFinite(changeValue)
    ? changeValue >= 0
      ? "text-emerald-600"
      : "text-red-600"
    : "text-slate-400";
  const biasToneClass =
    combinedSummary.tone.label === ui.positive
      ? "text-emerald-700"
      : combinedSummary.tone.label === ui.negative
      ? "text-red-700"
      : "text-slate-700";

  const summaryItems = [
    {
      label: ui.combinedScore,
      value: combinedSummary.score === null ? "—" : `${combinedSummary.score}/100`,
      className: "text-slate-950",
    },
    { label: ui.bias, value: combinedSummary.bias, className: biasToneClass },
    {
      label: ui.confidence,
      value: combinedSummary.confidence === null ? "—" : `${combinedSummary.confidence}%`,
      className: "text-slate-950",
    },
  ];

  return (
    <section className="relative overflow-hidden rounded-[24px] border border-slate-200/80 bg-white px-4 py-3.5 shadow-[0_18px_40px_-36px_rgba(15,23,42,0.26)]">
      <div className="absolute inset-x-0 top-0 h-px bg-gradient-to-r from-blue-500 via-blue-200 to-transparent" />
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2 text-[10px] font-black uppercase tracking-[0.22em] text-blue-600">
            <Brain size={12} />
            {ui.activeAnalysis}
        </div>
        <div className="shrink-0 text-right text-[11px] font-semibold text-slate-400">
          {ui.updated} <span className="text-slate-600">{updatedAt}</span>
        </div>
      </div>

      <div className="mt-2.5 grid gap-3 lg:grid-cols-[minmax(0,1fr)_minmax(350px,auto)] lg:items-end">
        <div className="flex min-w-0 items-center gap-3 overflow-hidden">
            <button
              type="button"
              onClick={onSelectAsset}
              className="inline-flex shrink-0 items-center gap-2 rounded-full border border-slate-200 bg-slate-50 px-3 py-1.5 text-[13px] font-black tracking-tight text-slate-950 transition hover:border-blue-200 hover:text-blue-600"
            >
              <span>{activeSymbol}</span>
              <span className="hidden text-slate-400 sm:inline">{assetName || "Asset"}</span>
            </button>
            <span className="min-w-0 truncate text-[31px] font-black leading-none tracking-tight text-slate-950 sm:text-[34px] lg:text-[36px]">
              {price}
            </span>
            <span className={`shrink-0 text-base font-black ${changeClass}`}>
              {formatPercent(change24h)}
            </span>
            <span className="shrink-0 text-[12px] font-black uppercase tracking-[0.14em] text-slate-400">1D</span>
        </div>

        <div className="grid grid-cols-3 divide-x divide-slate-100 overflow-hidden rounded-2xl border border-slate-200 bg-slate-50/70">
          {summaryItems.map((item) => (
            <div key={item.label} className="min-w-0 px-3 py-2 text-center">
              <div className="truncate text-[8px] font-black uppercase tracking-[0.16em] text-slate-400">
                {item.label}
              </div>
              <div className={`mt-0.5 truncate text-[12px] font-black ${item.className}`}>
                {item.value}
              </div>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

function AssetList({ rows, activeSymbol, onSelect, onAddAsset, ui }) {
  return (
    <section className="rounded-[24px] border border-slate-200/80 bg-white p-3.5 shadow-[0_18px_40px_-36px_rgba(15,23,42,0.26)]">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <span className="text-[10px] font-black uppercase tracking-[0.24em] text-slate-400">
            {ui.watchlist}
          </span>
          <div className="flex flex-wrap gap-2">
            {ASSET_GROUPS.map((group) => (
              <button
                key={group.id}
                type="button"
                className={`rounded-full border px-2.5 py-0.5 text-[10px] font-black uppercase tracking-[0.16em] ${
                  group.active
                    ? "border-slate-900 bg-slate-900 text-white"
                    : "border-slate-200 bg-white text-slate-500"
                }`}
              >
                {group.label}
              </button>
            ))}
          </div>
        </div>

        <button
          type="button"
          onClick={onAddAsset}
          className="inline-flex items-center gap-2 rounded-full border border-dashed border-slate-300 px-3 py-1 text-[10px] font-black uppercase tracking-[0.16em] text-slate-500 transition hover:border-blue-300 hover:text-blue-600"
        >
          <Plus size={12} />
          {ui.addAsset}
        </button>
      </div>

      <div className="mt-3 overflow-hidden rounded-[18px] border border-slate-200 bg-white">
        <div className="grid grid-cols-[minmax(0,1.5fr)_120px_100px_80px_120px] gap-3 border-b border-slate-100 px-4 py-2.5 text-[9px] font-black uppercase tracking-[0.2em] text-slate-400">
          <div>Asset</div>
          <div className="text-right">{ui.latest}</div>
          <div className="text-right">24u</div>
          <div className="text-right">Score</div>
          <div className="text-right">{ui.bias}</div>
        </div>
        <div>
          {rows.map((row) => {
            const active = row.symbol === activeSymbol;
            return (
              <button
                key={row.symbol}
                type="button"
                onClick={() => onSelect(row.symbol)}
                className={`grid w-full grid-cols-[minmax(0,1.5fr)_120px_100px_80px_120px] gap-3 border-b border-slate-100 px-4 py-2.5 text-left transition last:border-b-0 ${
                  active ? "bg-blue-50/70" : "hover:bg-slate-50/80"
                }`}
              >
                <div className="min-w-0">
                  <div className="flex items-center gap-2">
                    <span className={`h-2.5 w-2.5 rounded-full ${active ? "bg-blue-600" : "bg-slate-300"}`} />
                    <span className="text-[15px] font-black text-slate-950">{row.symbol}</span>
                  </div>
                  <div className="mt-0.5 truncate text-[13px] font-medium text-slate-500">
                    {ASSET_NAMES[row.symbol] || "Asset context"}
                  </div>
                </div>
                <div className="text-right text-[15px] font-black text-slate-950">{row.lastPrice}</div>
                <div className={`text-right text-[15px] font-black ${row.changeTone}`}>
                  {row.change24h}
                </div>
                <div className="text-right text-[15px] font-black text-slate-950">{row.score}</div>
                <div className="text-right">
                  <span className={`inline-flex rounded-full border px-2 py-0.5 text-[9px] font-black uppercase tracking-[0.14em] ${row.biasTone}`}>
                    {row.bias}
                  </span>
                </div>
              </button>
            );
          })}
        </div>
      </div>
    </section>
  );
}

function SectionScorePill({ score }) {
  const tone = scoreTone(score);
  return (
    <div className={`inline-flex items-center rounded-full border px-2.5 py-0.5 text-[10px] font-black uppercase tracking-[0.18em] ${tone.pill}`}>
      {normalizeScore(score) === null ? "—" : `${Math.round(normalizeScore(score))}/100`}
    </div>
  );
}

function EvidenceRow({ row, expanded, onToggle, renderExpandedActions }) {
  return (
    <div className="border-t border-slate-100">
      <button
        type="button"
        onClick={onToggle}
        className="w-full px-4 py-2.5 text-left transition hover:bg-slate-50/80"
      >
        <div className="grid gap-3 lg:grid-cols-[minmax(0,1.15fr)_minmax(120px,0.45fr)_minmax(150px,0.5fr)_minmax(220px,0.8fr)] lg:items-center">
          <div className="flex items-start gap-3">
            <span className={`mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-full border transition ${
              expanded ? "border-blue-200 bg-blue-50 text-blue-600" : "border-slate-200 bg-white text-slate-400"
            }`}>
              <ChevronDown size={14} className={`transition ${expanded ? "rotate-180" : ""}`} />
            </span>
            <div className="min-w-0">
              <div className="text-[10px] font-black uppercase tracking-[0.22em] text-slate-400 lg:hidden">
                Indicator
              </div>
              <div className="text-[14px] font-black leading-tight text-slate-950">{row.label}</div>
            </div>
          </div>

          <div className="lg:text-right">
            <div className="text-[10px] font-black uppercase tracking-[0.22em] text-slate-400 lg:hidden">
              Waarde
            </div>
            <div className="text-[14px] font-black text-slate-950">{row.value}</div>
          </div>

          <div>
            <div className="text-[10px] font-black uppercase tracking-[0.22em] text-slate-400 lg:hidden">
              Ontwikkeling
            </div>
            <span className="inline-flex items-center gap-2 rounded-full bg-slate-100 px-2.5 py-0.5 text-[9px] font-bold text-slate-600">
              <span className={`h-2 w-2 rounded-full ${row.signalTone.dot}`} />
              {row.direction}
            </span>
          </div>

          <div>
            <div className="text-[10px] font-black uppercase tracking-[0.22em] text-slate-400 lg:hidden">
              Beoordeling
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <span className={`inline-flex items-center rounded-full border px-2.5 py-0.5 text-[9px] font-black uppercase tracking-[0.12em] ${row.signalTone.pill}`}>
                {row.scoreLabel}
              </span>
            </div>
            <p className="mt-1 text-[12px] font-medium leading-5 text-slate-500">
              {row.detail}
            </p>
          </div>
        </div>
      </button>

      {expanded ? (
        <div className="bg-slate-50/70 px-4 py-3">
          <div className="grid gap-4 lg:grid-cols-[1.4fr_0.8fr]">
            <div>
              <div className="text-[10px] font-black uppercase tracking-[0.22em] text-slate-400">
                Verdieping
              </div>
              <p className="mt-1.5 text-[13px] font-medium leading-6 text-slate-600">
                {row.raw?.interpretation || row.raw?.uitleg || row.raw?.action || row.detail}
              </p>
            </div>

            <div className="flex flex-col gap-3 lg:items-end">
              <div className="text-left lg:text-right">
                <div className="text-[10px] font-black uppercase tracking-[0.22em] text-slate-400">
                  Laatste signaal
                </div>
                <div className="mt-1.5 text-[13px] font-black text-slate-900">
                  {row.timestamp ? formatTimestamp(row.timestamp) : "Live"}
                </div>
              </div>
              {renderExpandedActions ? renderExpandedActions(row) : null}
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}

function EvidenceSection({
  id,
  title,
  eyebrow,
  icon: Icon,
  score,
  insight,
  rows,
  expandedRowKey,
  onToggleRow,
  action,
  renderExpandedActions,
  emptyState,
}) {
  return (
    <section className="rounded-[24px] border border-slate-200/80 bg-white shadow-[0_18px_40px_-36px_rgba(15,23,42,0.26)]">
      <div className="flex flex-wrap items-start justify-between gap-3 border-b border-slate-100 px-4 py-3.5">
        <div className="min-w-0">
          <div className="flex items-center gap-2 text-[10px] font-black uppercase tracking-[0.26em] text-blue-600">
            <Icon size={12} />
            {eyebrow}
          </div>
          <div className="mt-1 flex items-center gap-3">
            <h2 className="text-[18px] font-black tracking-tight text-slate-950">{title}</h2>
            <SectionScorePill score={score} />
          </div>
          <p className="mt-1.5 max-w-3xl text-[12px] font-medium leading-5 text-slate-500">
            {insight}
          </p>
        </div>
        {action}
      </div>

      <div className="hidden border-b border-slate-100 px-4 py-2 lg:grid lg:grid-cols-[minmax(0,1.15fr)_minmax(120px,0.45fr)_minmax(150px,0.5fr)_minmax(220px,0.8fr)] lg:gap-3">
        {["Indicator", "Waarde", "Ontwikkeling", "Beoordeling"].map((label, index) => (
          <div
            key={label}
            className={`text-[10px] font-black uppercase tracking-[0.24em] text-slate-400 ${
              index === 1 ? "text-right" : ""
            }`}
          >
            {label}
          </div>
        ))}
      </div>

      <div>
        {rows.length ? (
          rows.map((row) => {
            const rowKey = `${id}:${row.id}`;
            return (
              <EvidenceRow
                key={rowKey}
                row={row}
                expanded={expandedRowKey === rowKey}
                onToggle={() => onToggleRow(rowKey)}
                renderExpandedActions={renderExpandedActions}
              />
            );
          })
        ) : (
          <div className="px-5 py-12 text-center text-sm font-semibold text-slate-400">
            {emptyState}
          </div>
        )}
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
  const ui = useMemo(() => getUiCopy(locale), [locale]);
  const { watchlist } = useWatchlist();
  const symbolFromUrl = searchParams.get("symbol")?.toUpperCase();
  const activeSymbol = symbolFromUrl || selectedAsset || "BTC";
  const [macroTimeframe, setMacroTimeframe] = useState("day");
  const [technicalTimeframe] = useState("day");
  const [expandedRowKey, setExpandedRowKey] = useState(null);
  const [technicalConfigModal, setTechnicalConfigModal] = useState(null);
  const [watchlistRows, setWatchlistRows] = useState([]);
  const [showChart, setShowChart] = useState(true);
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

  const {
    market,
    macro,
    technical,
    setup,
    master,
    loading: scoresLoading,
    hasData: hasScoreData,
    saveWeights,
  } = useScoresData(activeSymbol, {
    includeHistory: false,
    includeMaster: true,
    fallbackOnError: false,
  });
  const { snapshot: overviewSnapshot, loading: overviewLoading } = useOverviewSnapshot(activeSymbol, {
    includeLive: false,
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
          setTechnicalConfigModal(technicalIndicatorFromUrl);
        }
      })
      .catch((error) => {
        console.error("Failed to add technical indicator from command search:", error);
      });
  }, [addTechnicalIndicator, indicatorAction, technicalIndicatorFromUrl]);

  const watchlistSymbols = useMemo(() => {
    const preferred =
      Array.isArray(watchlist) && watchlist.length
        ? watchlist
        : Array.isArray(availableAssets) && availableAssets.length
        ? availableAssets
        : ["BTC", "ETH", "SOL", "ADA", "DOT"];
    return Array.from(
      new Set(preferred.map((symbol) => String(symbol || "").toUpperCase()).filter(Boolean))
    ).slice(0, 6);
  }, [availableAssets, watchlist]);

  useEffect(() => {
    let cancelled = false;

    async function loadWatchlistRows() {
      const nextRows = await Promise.all(
        watchlistSymbols.map(async (symbol) => {
          try {
            if (symbol === activeSymbol) {
              const combined = hasScoreData
                ? summarizeWeightedScores(
                    {
                      market: market?.score,
                      macro: macro?.score,
                      technical: technical?.score,
                    },
                    master?.weights,
                    ui
                  )
                : summarizeContextScores([], ui);
              const changeValue = Number(btcLive?.change_24h);

              return {
                symbol,
                lastPrice: formatPrice(btcLive?.price, locale),
                change24h: formatPercent(changeValue, 2),
                changeTone: Number.isFinite(changeValue)
                  ? changeValue >= 0 ? "text-emerald-600" : "text-red-600"
                  : "text-slate-400",
                score: formatScore(combined.score),
                bias: combined.bias,
                biasTone: combined.tone.pill,
              };
            }

            const [latestResult, scoresResult] = await Promise.allSettled([
              fetchLatestPrice(symbol, { forceFresh: false }),
              getDailyScores(symbol, { fallbackOnError: false }),
            ]);

            const latest = latestResult.status === "fulfilled" ? latestResult.value : null;
            const scores = scoresResult.status === "fulfilled" ? scoresResult.value : null;
            const combined = summarizeWeightedScores(
              {
                market: scores?.market?.score,
                macro: scores?.macro?.score,
                technical: scores?.technical?.score,
              },
              master?.weights,
              ui
            );
            const changeValue = Number(latest?.change_24h);

            return {
              symbol,
              lastPrice: formatPrice(latest?.price, locale),
              change24h: formatPercent(changeValue, 2),
              changeTone: Number.isFinite(changeValue)
                ? changeValue >= 0 ? "text-emerald-600" : "text-red-600"
                : "text-slate-400",
              score: formatScore(combined.score),
              bias: combined.bias,
              biasTone: combined.tone.pill,
            };
          } catch {
            return {
              symbol,
              lastPrice: "—",
              change24h: "—",
              changeTone: "text-slate-400",
              score: "—",
              bias: ui.neutral,
              biasTone: "border-slate-200 bg-slate-50 text-slate-700",
            };
          }
        })
      );

      if (!cancelled) {
        setWatchlistRows(nextRows);
      }
    }

    loadWatchlistRows();
    return () => {
      cancelled = true;
    };
  }, [activeSymbol, btcLive, hasScoreData, locale, macro, master, market, technical, ui, watchlistSymbols]);

  const combinedSummary = useMemo(() => {
    if (!hasScoreData) return summarizeContextScores([], ui);
    const summary = summarizeWeightedScores(
      {
        market: market?.score,
        macro: macro?.score,
        technical: technical?.score,
      },
      master?.weights,
      ui
    );

    return {
      ...summary,
      bias: master?.bias && master.bias !== "—" ? formatBiasLabel(master.bias, ui) : summary.bias,
    };
  }, [hasScoreData, macro, market, master, technical, ui]);

  const sections = useMemo(() => {
    const marketRows = buildRows(marketDayData, locale);
    const macroRows = buildRows(macroData, locale);
    const technicalRows = buildRows(technicalData, locale);

    return [
      {
        id: "market",
        title: locale?.startsWith("en") ? "Market" : locale?.startsWith("de") ? "Markt" : SECTION_META.market.label,
        eyebrow: locale?.startsWith("en") ? "Market evidence" : locale?.startsWith("de") ? "Marktbelege" : "Marktbewijs",
        icon: SECTION_META.market.icon,
        score: hasScoreData ? market?.score : null,
        insight: buildSectionInsight("market", hasScoreData ? market?.score : null, marketRows),
        rows: marketRows,
        emptyState: marketLoading ? (locale?.startsWith("en") ? "Loading market data..." : locale?.startsWith("de") ? "Marktdaten werden geladen..." : "Marktdata laden...") : SECTION_META.market.empty,
      },
      {
        id: "macro",
        title: locale?.startsWith("en") ? "Macro" : locale?.startsWith("de") ? "Makro" : SECTION_META.macro.label,
        eyebrow: locale?.startsWith("en") ? "Macro evidence" : locale?.startsWith("de") ? "Makrobelege" : "Macro-bewijs",
        icon: SECTION_META.macro.icon,
        score: hasScoreData ? macro?.score : null,
        insight: buildSectionInsight("macro", hasScoreData ? macro?.score : null, macroRows),
        rows: macroRows,
        emptyState: macroLoading ? (locale?.startsWith("en") ? "Loading macro data..." : locale?.startsWith("de") ? "Makrodaten werden geladen..." : "Macrodata laden...") : SECTION_META.macro.empty,
      },
      {
        id: "technical",
        title: locale?.startsWith("en") ? "Technical" : locale?.startsWith("de") ? "Technisch" : SECTION_META.technical.label,
        eyebrow: locale?.startsWith("en") ? "Technical evidence" : locale?.startsWith("de") ? "Technische belege" : "Technisch bewijs",
        icon: SECTION_META.technical.icon,
        score: hasScoreData ? technical?.score : null,
        insight: buildSectionInsight("technical", hasScoreData ? technical?.score : null, technicalRows),
        rows: technicalRows,
        emptyState: technicalLoading ? (locale?.startsWith("en") ? "Loading technical data..." : locale?.startsWith("de") ? "Technische daten werden geladen..." : "Technische data laden...") : SECTION_META.technical.empty,
      },
    ];
  }, [hasScoreData, locale, macro, macroData, macroLoading, market, marketDayData, marketLoading, technical, technicalData, technicalLoading]);

  const handleAssetSelect = (symbol) => {
    const nextSymbol = String(symbol || activeSymbol).toUpperCase();
    setSelectedAsset(nextSymbol);
    router.push(buildContextHref({ pathname, symbol: nextSymbol, context: initialTab, variant }), {
      scroll: false,
    });
  };

  const openSearch = (detail = undefined) => {
    if (typeof window === "undefined") return;
    window.dispatchEvent(new CustomEvent(SEARCH_OPEN_EVENT, { detail }));
  };

  return (
    <section className="space-y-3">
      <ActiveAssetCard
        activeSymbol={activeSymbol}
        assetName={ASSET_NAMES[activeSymbol]}
        price={formatPrice(btcLive?.price, locale)}
        change24h={btcLive?.change_24h}
        updatedAt={formatTimestamp(btcLive?.timestamp, locale)}
        combinedSummary={combinedSummary}
        onSelectAsset={() => openSearch()}
        ui={ui}
      />

      <AssetList
        rows={watchlistRows}
        activeSymbol={activeSymbol}
        onSelect={handleAssetSelect}
        onAddAsset={() => openSearch()}
        ui={ui}
      />

      <AnalysisChartSection
        symbol={activeSymbol}
        isOpen={showChart}
        onToggle={() => setShowChart((current) => !current)}
        ui={ui}
      />

      <section className="rounded-[24px] border border-slate-200/80 bg-white p-3.5 shadow-[0_18px_40px_-36px_rgba(15,23,42,0.26)]">
        <div className="mb-2.5 flex flex-wrap items-center justify-between gap-2">
          <div className="text-[10px] font-black uppercase tracking-[0.24em] text-blue-600">
            {ui.marketRegime}
          </div>
          <div className="text-[10px] font-black uppercase tracking-[0.14em] text-slate-400">
            {ui.setupRoute}
          </div>
        </div>
        <GlobalMarketDecisionCard
          symbol={activeSymbol}
          snapshot={{
            data: overviewSnapshot?.intelligence ?? null,
            loading: overviewLoading && !overviewSnapshot?.intelligence,
          }}
          compact
        />
      </section>

      <ScoreOverview
        market={hasScoreData ? market : null}
        macro={hasScoreData ? macro : null}
        technical={hasScoreData ? technical : null}
        combined={combinedSummary}
        weights={master?.weights}
        loading={scoresLoading}
        onSaveWeights={saveWeights}
        ui={ui}
      />

      <section className="space-y-3">
        {sections.map((section) => (
          <EvidenceSection
            key={section.id}
            id={section.id}
            title={section.title}
            eyebrow={section.eyebrow}
            icon={section.icon}
            score={section.score}
            insight={section.insight}
            rows={section.rows}
            expandedRowKey={expandedRowKey}
            onToggleRow={(key) => setExpandedRowKey((current) => (current === key ? null : key))}
            emptyState={section.emptyState}
            action={
              section.id === "market" ? (
                <button
                  type="button"
                  onClick={() => openSearch({ mode: "indicator", category: "market" })}
                  className="inline-flex items-center gap-2 rounded-full border border-slate-200 bg-white px-3 py-1.5 text-[10px] font-black uppercase tracking-[0.16em] text-slate-700 transition hover:border-blue-200 hover:text-blue-600"
                >
                  <Plus size={12} />
                  {ui.addIndicator}
                </button>
              ) : section.id === "macro" ? (
                <div className="flex flex-wrap items-center justify-end gap-2">
                  <div
                    role="group"
                    aria-label={ui.macroPeriod}
                    className={`inline-flex rounded-full border border-slate-200 bg-slate-50 p-0.5 transition-opacity ${
                      macroLoading ? "opacity-60" : "opacity-100"
                    }`}
                  >
                    {MACRO_TIMEFRAMES.map((timeframe) => (
                      <button
                        key={timeframe}
                        type="button"
                        onClick={() => setMacroTimeframe(timeframe)}
                        aria-pressed={macroTimeframe === timeframe}
                        className={`rounded-full px-2.5 py-1 text-[9px] font-black uppercase tracking-[0.12em] transition ${
                          macroTimeframe === timeframe
                            ? "bg-white text-blue-600 shadow-sm ring-1 ring-slate-200"
                            : "text-slate-400 hover:text-slate-700"
                        }`}
                      >
                        {ui[timeframe]}
                      </button>
                    ))}
                  </div>
                  <button
                    type="button"
                    onClick={() => openSearch({ mode: "indicator", category: "macro" })}
                    className="inline-flex items-center gap-2 rounded-full border border-slate-200 bg-white px-3 py-1.5 text-[10px] font-black uppercase tracking-[0.16em] text-slate-700 transition hover:border-blue-200 hover:text-blue-600"
                  >
                    <Plus size={12} />
                    {ui.addIndicator}
                  </button>
                </div>
              ) : section.id === "technical" ? (
                <button
                  type="button"
                  onClick={() => openSearch({ mode: "indicator", category: "technical" })}
                  className="inline-flex items-center gap-2 rounded-full border border-slate-200 bg-white px-3 py-1.5 text-[10px] font-black uppercase tracking-[0.16em] text-slate-700 transition hover:border-blue-200 hover:text-blue-600"
                >
                  <Plus size={12} />
                  {ui.addIndicator}
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

      <PlanBridge
        setup={hasScoreData ? setup : null}
        onOpenPlan={() => router.push(`/setup?symbol=${encodeURIComponent(activeSymbol)}`)}
        ui={ui}
      />

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
