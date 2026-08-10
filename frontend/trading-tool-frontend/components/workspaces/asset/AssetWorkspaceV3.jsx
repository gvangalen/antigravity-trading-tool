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
  Sliders,
  Target,
  TrendingUp,
  X,
} from "lucide-react";

import { useAsset } from "@/app/providers/AssetProvider";
import { useTranslation } from "@/app/providers/I18nProvider";
import { useAssetWorkspaceData } from "@/hooks/useAssetWorkspaceData";
import { useStrategyData } from "@/hooks/useStrategyData";
import IndicatorConfigModal from "@/components/scoring/IndicatorConfigModal";
import MarketForwardReturnTabs from "@/components/market/MarketForwardReturnTabs";
import {
  fetchForwardReturnsMonth,
  fetchForwardReturnsQuarter,
  fetchForwardReturnsWeek,
  fetchForwardReturnsYear,
  marketIndicatorAdd,
} from "@/lib/api/market";
import { macroDataAdd } from "@/lib/api/macro";
import { fetchActiveSetup } from "@/lib/api/setups";
import { technicalDataAdd } from "@/lib/api/technical";
import { updateIntelligenceWeights } from "@/lib/api/scores";
import { getAssistantPreferences, updateAssistantPreferences } from "@/lib/api/ai";
import TradingViewSmartChart from "@/components/charts/TradingViewSmartChart";
import {
  ANALYSIS_CHART_INTERVAL_KEY,
  DEFAULT_TRADINGVIEW_INTERVAL,
  normalizeTradingViewInterval,
  toTradingViewSymbol,
} from "../../../../../shared/tradingViewConfig";
import GlobalMarketDecisionCard from "@/components/dashboard/GlobalMarketDecisionCard";
import { FINN_INDICATOR_MODAL_COMPLETED_EVENT } from "@/lib/finnCommandSearch";
import { requestIndicatorContext } from "@/lib/api/workspace";

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

function resolveAssetLogoUrl(symbol, explicitLogoUrl = null, assetClass = null) {
  if (explicitLogoUrl) return explicitLogoUrl;
  const normalized = String(symbol || "").trim().toUpperCase();
  const normalizedAssetClass = String(assetClass || "").trim().toLowerCase();
  if (!normalized) return null;
  if (normalizedAssetClass === "crypto" && /^[A-Z]{2,10}$/.test(normalized)) {
    return `https://assets.coincap.io/assets/icons/${normalized.toLowerCase()}@2x.png`;
  }
  return null;
}

const ASSET_GROUPS = [
  { id: "crypto", label: "Crypto" },
  { id: "stocks", label: "Stocks" },
];

function normalizeAssetGroup(assetClass) {
  const normalized = String(assetClass || "").trim().toLowerCase();
  if (normalized === "crypto") return "crypto";
  if (normalized === "stock" || normalized === "stocks" || normalized === "etf" || normalized === "etfs") {
    return "stocks";
  }
  return "crypto";
}

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
      planBridgeTitle: "Best matching plan for current market conditions",
      planBridgeDescription: "Open My Plan to review the linked plan, setup and strategy before bot execution.",
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
      marketPeriod: "Market period",
      macroPeriod: "Macro period",
      technicalPeriod: "Technical period",
      forwardReturnsTitle: "Historical forward returns",
      forwardReturnsSubtitle: "Compare recurring returns by week, month, quarter and year.",
      forwardReturnsLoading: "Loading historical returns...",
      improving: "Improving",
      worsening: "Weakening",
      stable: "Stable",
      active: "Active",
      weakened: "Weak",
      indicator: "Indicator",
      value: "Value",
      development: "Development",
      assessment: "Assessment",
      details: "Details",
      latestSignal: "Latest signal",
      dataSource: "Source",
      periodLabel: "Period",
      freshness: "Freshness",
      currentData: "Current",
      fallbackData: "Fallback",
      staleData: "Stale",
      fallbackReady: "Fallback data is available. Detailed context will return automatically once the full workspace feed responds again.",
      scoreContribution: "Score contribution",
      sampleSize: "Samples",
      askFinnContext: "Ask FINN for context",
      finnContext: "FINN context",
      finnContextLoading: "FINN is reviewing this indicator...",
      finnContextUnavailable: "Extra AI context is currently unavailable. The current data and rule-based explanation above remain available.",
      whyCounts: "Why this counts",
      confirmation: "What to monitor",
      conflicts: "Conflicts and caveats",
      live: "Live",
      edit: "Edit",
      remove: "Remove",
      marketEmpty: "No market indicators loaded yet.",
      macroEmpty: "No macro indicators loaded yet.",
      technicalEmpty: "No technical indicators loaded yet.",
      loadingMarket: "Loading market data...",
      loadingMacro: "Loading macro data...",
      loadingTechnical: "Loading technical data...",
      indicatorAssessment: (label, direction, signal) => `${label} is ${direction.toLowerCase()} and currently gives a ${signal.toLowerCase()} signal.`,
      positiveMoveWeakScore: (value, score) => `Price is up ${value}, but the configured scoring thresholds still place this move in the weak zone (${score}/100).`,
      aboveMa200: "Above MA200",
      belowMa200: "Below MA200",
      aboveMa50: "Above MA50",
      belowMa50: "Below MA50",
      indicatorLabels: {
        change_24h: "24-hour price change",
        volume: "Volume",
        market_volume: "Volume",
        btc_dominance: "Bitcoin dominance",
        fear_greed_index: "Fear & Greed",
        ma_50: "50-day moving average",
        ma_200: "200-day moving average",
        ema_20_gap_pct: "EMA20 Gap %",
        ema_50_gap_pct: "EMA50 Gap %",
        macd_hist_pct: "MACD Histogram %",
        atr_pct: "ATR %",
        adx: "ADX",
        rsi: "RSI",
      },
      sectionInsights: {
        missing: "Not enough score data for a reliable group conclusion.",
        marketNegative: "Price action is weak and confirmation from volume and liquidity remains limited.",
        marketPositive: "Price action and market internals support the move.",
        marketNeutral: "The market picture is mixed: movement is visible, but confirmation remains incomplete.",
        macroNegative: "Rising yields and a strong dollar remain macro headwinds.",
        macroPositive: "The macro regime supports the current risk picture.",
        macroNeutral: "Macro context remains mixed and needs confirmation from rates, flows and sentiment.",
        technicalNegative: "Trend structure is vulnerable and momentum does not yet provide strong confirmation.",
        technicalPositive: "Trend and active indicators align and support follow-through.",
        technicalNeutral: "The technical picture is workable, but momentum and trend confirmation remain neutral.",
      },
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
      planBridgeTitle: "Bester Plan für die aktuellen Marktbedingungen",
      planBridgeDescription: "Öffne Mein Plan, um den verknüpften Plan, das Setup und die Strategie vor der Bot-Ausführung zu prüfen.",
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
      marketPeriod: "Marktzeitraum",
      macroPeriod: "Makrozeitraum",
      technicalPeriod: "Technischer Zeitraum",
      forwardReturnsTitle: "Historische Forward Returns",
      forwardReturnsSubtitle: "Vergleiche wiederkehrende Renditen nach Woche, Monat, Quartal und Jahr.",
      forwardReturnsLoading: "Historische Renditen werden geladen...",
      improving: "Verbessert sich",
      worsening: "Verschlechtert sich",
      stable: "Stabil",
      active: "Aktiv",
      weakened: "Schwach",
      indicator: "Indikator",
      value: "Wert",
      development: "Entwicklung",
      assessment: "Bewertung",
      details: "Details",
      latestSignal: "Letztes Signal",
      dataSource: "Quelle",
      periodLabel: "Zeitraum",
      freshness: "Aktualität",
      currentData: "Aktuell",
      fallbackData: "Fallback",
      staleData: "Veraltet",
      fallbackReady: "Fallback-Daten sind verfügbar. Die Detailkontexte erscheinen automatisch wieder, sobald der vollständige Workspace-Feed erneut antwortet.",
      scoreContribution: "Score-Beitrag",
      sampleSize: "Stichproben",
      askFinnContext: "FINN nach Kontext fragen",
      finnContext: "FINN-Kontext",
      finnContextLoading: "FINN prüft diesen Indikator...",
      finnContextUnavailable: "Zusätzlicher AI-Kontext ist derzeit nicht verfügbar. Die aktuellen Daten und die regelbasierte Erklärung oben bleiben verfügbar.",
      whyCounts: "Warum dies zählt",
      confirmation: "Was zu beobachten ist",
      conflicts: "Konflikte und Einschränkungen",
      live: "Live",
      edit: "Bearbeiten",
      remove: "Entfernen",
      marketEmpty: "Noch keine Marktindikatoren geladen.",
      macroEmpty: "Noch keine Makroindikatoren geladen.",
      technicalEmpty: "Noch keine technischen Indikatoren geladen.",
      loadingMarket: "Marktdaten werden geladen...",
      loadingMacro: "Makrodaten werden geladen...",
      loadingTechnical: "Technische Daten werden geladen...",
      indicatorAssessment: (label, direction, signal) => `${label} ist ${direction.toLowerCase()} und liefert derzeit ein ${signal.toLowerCase()} Signal.`,
      positiveMoveWeakScore: (value, score) => `Der Kurs steigt um ${value}, aber die konfigurierten Score-Grenzen ordnen diese Bewegung noch der schwachen Zone zu (${score}/100).`,
      aboveMa200: "Über MA200",
      belowMa200: "Unter MA200",
      aboveMa50: "Über MA50",
      belowMa50: "Unter MA50",
      indicatorLabels: {
        change_24h: "24-Stunden-Preisänderung",
        volume: "Volumen",
        market_volume: "Volumen",
        btc_dominance: "Bitcoin-Dominanz",
        fear_greed_index: "Fear & Greed",
        ma_50: "50-Tage-Durchschnitt",
        ma_200: "200-Tage-Durchschnitt",
        ema_20_gap_pct: "EMA20 Abstand %",
        ema_50_gap_pct: "EMA50 Abstand %",
        macd_hist_pct: "MACD Histogramm %",
        atr_pct: "ATR %",
        adx: "ADX",
        rsi: "RSI",
      },
      sectionInsights: {
        missing: "Für eine zuverlässige Gruppenbewertung fehlen Score-Daten.",
        marketNegative: "Die Preisbewegung ist schwach; Volumen und Liquidität bestätigen sie nur begrenzt.",
        marketPositive: "Preisbewegung und Marktinternas unterstützen die Bewegung.",
        marketNeutral: "Das Marktbild ist gemischt: Bewegung ist sichtbar, die Bestätigung bleibt unvollständig.",
        macroNegative: "Steigende Renditen und ein starker Dollar bleiben makroökonomischer Gegenwind.",
        macroPositive: "Das Makroregime unterstützt das aktuelle Risikobild.",
        macroNeutral: "Der Makrokontext bleibt gemischt und benötigt Bestätigung durch Zinsen, Flows und Sentiment.",
        technicalNegative: "Die Trendstruktur ist anfällig und das Momentum bestätigt noch nicht ausreichend.",
        technicalPositive: "Trend und aktive Indikatoren stimmen überein und unterstützen eine Fortsetzung.",
        technicalNeutral: "Das technische Bild ist brauchbar, Momentum und Trendbestätigung bleiben jedoch neutral.",
      },
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
    planBridgeTitle: "Best passende plan voor de huidige marktomstandigheden",
    planBridgeDescription: "Open Mijn Plan om het gekoppelde plan, de setup en strategie te beoordelen voordat de bot uitvoert.",
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
    marketPeriod: "Marktperiode",
    macroPeriod: "Macroperiode",
    technicalPeriod: "Technische periode",
    forwardReturnsTitle: "Historische forward returns",
    forwardReturnsSubtitle: "Vergelijk terugkerende rendementen per week, maand, kwartaal en jaar.",
    forwardReturnsLoading: "Historische rendementen laden...",
    improving: "Verbetert",
    worsening: "Verslechtert",
    stable: "Stabiel",
    active: "Actief",
    weakened: "Verzwakt",
    indicator: "Indicator",
    value: "Waarde",
    development: "Ontwikkeling",
    assessment: "Beoordeling",
    details: "Verdieping",
    latestSignal: "Laatste signaal",
    dataSource: "Bron",
    periodLabel: "Periode",
    freshness: "Actualiteit",
    currentData: "Actueel",
    fallbackData: "Fallback",
    staleData: "Verouderd",
    fallbackReady: "Fallback-data is beschikbaar. De detailcontext komt automatisch terug zodra de volledige workspace-feed weer antwoord geeft.",
    scoreContribution: "Scorebijdrage",
    sampleSize: "Meetpunten",
    askFinnContext: "Vraag FINN om context",
    finnContext: "FINN-context",
    finnContextLoading: "FINN beoordeelt deze indicator...",
    finnContextUnavailable: "Extra AI-context is nu niet beschikbaar. De actuele data en regeluitleg hierboven blijven wel beschikbaar.",
    whyCounts: "Waarom dit meetelt",
    confirmation: "Wat je kunt volgen",
    conflicts: "Conflicten en kanttekeningen",
    live: "Live",
    edit: "Bewerken",
    remove: "Verwijderen",
    marketEmpty: "Nog geen marktindicatoren geladen.",
    macroEmpty: "Nog geen macro-indicatoren geladen.",
    technicalEmpty: "Nog geen technische indicatoren geladen.",
    loadingMarket: "Marktdata laden...",
    loadingMacro: "Macrodata laden...",
    loadingTechnical: "Technische data laden...",
    indicatorAssessment: (label, direction, signal) => `${label} ${direction.toLowerCase()} en geeft nu een ${signal.toLowerCase()} signaal.`,
    positiveMoveWeakScore: (value, score) => `De koers stijgt ${value}, maar de ingestelde scoregrenzen plaatsen deze beweging nog in de zwakke zone (${score}/100).`,
    aboveMa200: "Boven MA200",
    belowMa200: "Onder MA200",
    aboveMa50: "Boven MA50",
    belowMa50: "Onder MA50",
    indicatorLabels: {
      change_24h: "Prijsverandering 24 uur",
      volume: "Volume",
      market_volume: "Volume",
      btc_dominance: "Bitcoin-dominantie",
      fear_greed_index: "Fear & Greed",
      ma_50: "50-daags gemiddelde",
      ma_200: "200-daags gemiddelde",
      ema_20_gap_pct: "EMA20-afstand %",
      ema_50_gap_pct: "EMA50-afstand %",
      macd_hist_pct: "MACD-histogram %",
      atr_pct: "ATR %",
      adx: "ADX",
      rsi: "RSI",
    },
    sectionInsights: {
      missing: "Onvoldoende scoredata voor een betrouwbare groepsconclusie.",
      marketNegative: "Prijsactie oogt zwak en bevestiging vanuit volume en liquiditeit blijft beperkt.",
      marketPositive: "Prijsactie en marktinternals ondersteunen de beweging.",
      marketNeutral: "Het marktbeeld is gemengd: beweging is zichtbaar, maar bevestiging blijft nog onvolledig.",
      macroNegative: "Stijgende yields en een sterke dollar blijven macro-tegenwind geven.",
      macroPositive: "Het macroregime ondersteunt het actuele risicobeeld.",
      macroNeutral: "De macrocontext blijft gemengd en vraagt om bevestiging vanuit rates, flows en sentiment.",
      technicalNegative: "De trendstructuur is kwetsbaar en momentum levert nog geen sterke bevestiging.",
      technicalPositive: "Trend en actieve indicatoren staan op één lijn en ondersteunen follow-through.",
      technicalNeutral: "Het technische beeld is werkbaar, maar momentum en trendbevestiging blijven neutraal.",
    },
  };
}

const DEFAULT_INTELLIGENCE_WEIGHTS = {
  market: 1 / 3,
  macro: 1 / 3,
  technical: 1 / 3,
};

const ANALYSIS_TIMEFRAMES = ["day", "week", "month", "quarter"];
const ANALYSIS_HIDDEN_INDICATORS_KEY = "analysis_hidden_indicators";

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

function normalizeHiddenIndicatorKeys(value) {
  if (!Array.isArray(value)) return [];
  return value
    .map((item) => (typeof item === "string" ? item.trim().toLowerCase() : ""))
    .filter(Boolean);
}

function buildHiddenIndicatorKey(symbol, sectionId, label) {
  return `${String(symbol || "").toUpperCase()}:${sectionId}:${label}`.toLowerCase();
}

function filterVisibleRows(rows, symbol, sectionId, hiddenIndicatorKeys) {
  return (Array.isArray(rows) ? rows : []).filter(
    (row) => !hiddenIndicatorKeys.includes(buildHiddenIndicatorKey(symbol, sectionId, row.label || row.name))
  );
}

function averageVisibleSectionScore(rows) {
  const scores = (Array.isArray(rows) ? rows : [])
    .map((row) => normalizeScore(row?.score))
    .filter((score) => score !== null);

  if (!scores.length) return null;
  return Math.round(scores.reduce((sum, score) => sum + score, 0) / scores.length);
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
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "—";
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

  params.set("tab", context);
  return `/asset?${params.toString()}`;
}

function trimSentence(value, fallback) {
  const source = String(value || "").trim();
  if (!source) return fallback;
  if (source.length <= 150) return source;
  return `${source.slice(0, 147).trim()}...`;
}

function prettifyName(name, ui = getUiCopy("nl")) {
  if (!name) return "Onbekende indicator";
  const normalized = String(name).trim();
  const lowered = normalized.toLowerCase();
  if (ui.indicatorLabels?.[lowered]) return ui.indicatorLabels[lowered];
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

function parseIndicatorNumber(value) {
  return Number(
    typeof value === "string"
      ? value.replace(/,/g, ".").replace(/[^0-9.+-]/g, "")
      : value
  );
}

function hasUsableIndicatorValue(name, value) {
  if (value === null || value === undefined || value === "") return false;
  const rawString = String(value).trim().toLowerCase();
  if (!rawString || /^(?:-|–|—|n\/?a|null|undefined|onvoldoende data|insufficient data)$/.test(rawString)) {
    return false;
  }

  const numericValue = parseIndicatorNumber(value);
  const label = String(name || "").toLowerCase();
  if ((label.includes("volume") || label.includes("flow")) && Number.isFinite(numericValue)) {
    return numericValue > 0;
  }
  return true;
}

function formatIndicatorValue(name, value, locale, ui = getUiCopy(locale)) {
  if (!hasUsableIndicatorValue(name, value)) return ui.unavailable;

  const label = String(name || "").toLowerCase();
  const raw = typeof value === "string" ? value.trim() : value;
  const rawString = typeof raw === "string" ? raw : "";
  const numericValue = parseIndicatorNumber(raw);

  if (typeof raw === "string" && /buy|sell|above|below|bull|bear|neutral|hoog|laag|stijg|daal|trend/i.test(rawString)) {
    return raw;
  }

  if (label === "ma_200" && Number.isFinite(numericValue)) {
    return numericValue >= 1 ? ui.aboveMa200 : ui.belowMa200;
  }

  if (label === "ma_50" && Number.isFinite(numericValue)) {
    return numericValue >= 1 ? ui.aboveMa50 : ui.belowMa50;
  }

  if ((label.includes("change") || label.includes("dominance")) && Number.isFinite(numericValue)) {
    const percentValue = normalizePotentialRatio(numericValue, { percent: true });
    return formatPercent(percentValue, 2);
  }

  if ((label.includes("gap_pct") || label.includes("atr_pct")) && Number.isFinite(numericValue)) {
    return formatPercent(numericValue, 2);
  }

  if ((label === "us10y" || label === "us2y") && Number.isFinite(numericValue)) {
    const percentValue = normalizePotentialRatio(numericValue, { percent: true });
    return `${formatCompactNumber(percentValue, locale, 2)}%`;
  }

  if (label.includes("volume") || label.includes("flow")) {
    if (!Number.isFinite(numericValue) || numericValue <= 0) return ui.unavailable;
    return `$${formatMagnitude(numericValue, locale)}`;
  }

  if (label.includes("price")) {
    if (!Number.isFinite(numericValue)) return ui.unavailable;
    if (Math.abs(numericValue) <= 1 && label.includes("change")) {
      return formatPercent(numericValue * 100, 2);
    }
    return formatPrice(numericValue, locale);
  }

  if (label.includes("rsi") || label.includes("fear") || label.includes("dxy")) {
    if (!Number.isFinite(numericValue)) return ui.unavailable;
    return formatCompactNumber(numericValue, locale, 2);
  }

  if (label.includes("participation") || label.includes("volatility")) {
    if (!Number.isFinite(numericValue)) return ui.unavailable;
    const percentValue = normalizePotentialRatio(numericValue, { percent: true });
    return `${formatCompactNumber(percentValue, locale, 2)}%`;
  }

  if (Number.isFinite(numericValue)) {
    return formatCompactNumber(numericValue, locale, 2);
  }

  return rawString || ui.unavailable;
}

function toDirectionLabel(item, score, ui = getUiCopy("nl")) {
  const trendSource = String(item?.trend || item?.action || item?.interpretation || "").trim().toLowerCase();
  if (trendSource.includes("improv") || trendSource.includes("stijg") || trendSource.includes("herstel")) return ui.improving;
  if (trendSource.includes("verslecht") || trendSource.includes("dal") || trendSource.includes("tegenwind")) return ui.worsening;
  if (trendSource.includes("stable") || trendSource.includes("stab")) return ui.stable;
  if (trendSource.includes("buy")) return ui.active;
  if (trendSource.includes("sell")) return ui.weakened;
  if (score === null) return ui.unavailable;
  if (score >= 70) return ui.improving;
  if (score <= 35) return ui.worsening;
  return ui.stable;
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

function buildRows(items, locale, ui) {
  const source = Array.isArray(items) ? items : [];

  return source.map((item, index) => {
    const name = item?.name || item?.indicator || `indicator_${index}`;
    const label = prettifyName(name, ui);
    const rawValue = item?.value ?? item?.waarde;
    const hasValue = hasUsableIndicatorValue(name, rawValue);
    const score = hasValue ? normalizeScore(item?.score) : null;
    const tone = scoreTone(score, ui);
    const direction = hasValue ? toDirectionLabel(item, score, ui) : ui.unavailable;
    const value = formatIndicatorValue(name, rawValue, locale, ui);
    const numericValue = parseIndicatorNumber(rawValue);
    const scoreConflict =
      hasValue &&
      String(name).toLowerCase().includes("change") &&
      Number.isFinite(numericValue) &&
      numericValue > 0 &&
      score !== null &&
      score <= 35;
    const detail = scoreConflict
      ? ui.positiveMoveWeakScore(value, Math.round(score))
      : trimSentence(
          item?.interpretation || item?.uitleg || "",
          hasValue ? ui.indicatorAssessment(label, direction, tone.label) : ui.unavailable
        );

    return {
      id: `${name}-${index}`,
      name,
      label,
      value,
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

function buildSectionInsight(sectionId, sectionScore, ui) {
  const score = normalizeScore(sectionScore);
  const copy = ui.sectionInsights;

  if (score === null) return copy.missing;

  if (sectionId === "market") {
    if (score <= 35) return copy.marketNegative;
    if (score >= 70) return copy.marketPositive;
    return copy.marketNeutral;
  }

  if (sectionId === "macro") {
    if (score <= 35) return copy.macroNegative;
    if (score >= 70) return copy.macroPositive;
    return copy.macroNeutral;
  }

  if (score <= 35) return copy.technicalNegative;
  if (score >= 70) return copy.technicalPositive;
  return copy.technicalNeutral;
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

function AnalysisChartSection({ interval, onIntervalChange, symbol, tradingViewSymbol, isOpen, onToggle, ui }) {
  const tvSymbol = tradingViewSymbol || toTradingViewSymbol(symbol);

  return (
    <section className="rounded-[24px] border border-slate-200/80 bg-white shadow-[0_18px_40px_-36px_rgba(15,23,42,0.26)]">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-100 px-4 py-3">
        <div className="text-[10px] font-black uppercase tracking-[0.24em] text-blue-600">
          {ui.chartTitle}
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
            interval={interval}
            indicators={[]}
            focusedBotId={null}
            setFocusedBotId={() => {}}
            height={400}
            onIntervalChange={onIntervalChange}
          />
        </div>
      ) : null}
    </section>
  );
}

function PlanBridge({ candidate, onOpenPlan, ui }) {
  const setupScore = normalizeScore(candidate?.score);
  const scoreLabel = setupScore === null ? "—" : `${Math.round(setupScore)}/100`;
  const candidateName = String(candidate?.displayName || "").trim();
  const bridgeTitle = candidateName || ui.planBridgeTitle;

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
              {bridgeTitle}
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
  if (!source || /^[-–—]+$/.test(source)) return ui.neutral;
  const normalized = source.toLowerCase();
  if (/(bull|posit)/.test(normalized)) return ui.positive;
  if (/(bear|negat)/.test(normalized)) return ui.negative;
  if (/(neutr|stab|side)/.test(normalized)) return ui.neutral;
  return source;
}

function ActiveAssetCard({
  activeSymbol,
  assetName,
  assetLogoUrl,
  price,
  change24h,
  updatedAt,
  statusLabel,
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
  ].filter((item) => item.value !== "—");

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
          {statusLabel ? (
            <div className="mt-0.5 text-[10px] font-black uppercase tracking-[0.14em] text-amber-600">
              {statusLabel}
            </div>
          ) : null}
        </div>
      </div>

      <div className="mt-2.5 grid gap-3 lg:grid-cols-[minmax(0,1fr)_minmax(350px,auto)] lg:items-end">
        <div className="flex min-w-0 items-center gap-3 overflow-hidden">
            <button
              type="button"
              onClick={onSelectAsset}
              className="inline-flex shrink-0 items-center gap-2 rounded-full border border-slate-200 bg-slate-50 px-3 py-1.5 text-[13px] font-black tracking-tight text-slate-950 transition hover:border-blue-200 hover:text-blue-600"
            >
              {assetLogoUrl ? (
                <img
                  src={assetLogoUrl}
                  alt={`${assetName || activeSymbol} logo`}
                  className="h-5 w-5 rounded-full object-cover"
                  loading="lazy"
                  referrerPolicy="no-referrer"
                />
              ) : null}
              <span>{activeSymbol}</span>
              <span className="hidden text-slate-400 sm:inline">{assetName || "Asset"}</span>
            </button>
            <span className="min-w-0 truncate text-[26px] font-black leading-none tracking-tight text-slate-950 sm:text-[29px] lg:text-[31px]">
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

function AssetList({ rows, activeSymbol, activeGroup, onSelect, onGroupChange, onAddAsset, ui }) {
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
                onClick={() => onGroupChange(group.id)}
                className={`rounded-full border px-2.5 py-0.5 text-[10px] font-black uppercase tracking-[0.16em] ${
                  activeGroup === group.id
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
          {rows.length ? rows.map((row) => {
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
                    {row.logoUrl ? (
                      <img
                        src={row.logoUrl}
                        alt={`${row.displayName || row.symbol} logo`}
                        className="h-5 w-5 rounded-full object-cover"
                        loading="lazy"
                        referrerPolicy="no-referrer"
                      />
                    ) : (
                      <span className={`h-2.5 w-2.5 rounded-full ${active ? "bg-blue-600" : "bg-slate-300"}`} />
                    )}
                    <span className="text-[15px] font-black text-slate-950">{row.symbol}</span>
                  </div>
                  <div className="mt-0.5 truncate text-[13px] font-medium text-slate-500">
                    {row.displayName || ASSET_NAMES[row.symbol] || "Asset context"}
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
          }) : (
            <div className="px-4 py-6 text-center text-xs font-bold text-slate-400">
              {activeGroup === "stocks" ? "Nog geen stock-assets in je watchlist." : "Nog geen crypto-assets in je watchlist."}
            </div>
          )}
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

function EvidenceRow({
  row,
  expanded,
  onToggle,
  renderExpandedActions,
  category,
  symbol,
  period,
  locale,
  ui,
}) {
  const [finnResult, setFinnResult] = useState(null);
  const [finnLoading, setFinnLoading] = useState(false);

  const requestFinnContext = async () => {
    if (finnLoading) return;
    setFinnLoading(true);
    try {
      const result = await requestIndicatorContext({
        symbol,
        category,
        indicator: row.name,
        period,
        timeframe: period === "day" ? "1D" : period,
        locale,
      });
      setFinnResult(result);
    } catch (error) {
      setFinnResult({ status: "unavailable", reason: error?.message || "request_failed" });
    } finally {
      setFinnLoading(false);
    }
  };

  const contribution = row.raw?.score_contribution;
  const contributionText =
    contribution?.status === "available"
      ? `${Math.round(Number(contribution.weight || 0) * 100)}% · ${Number(contribution.weighted_points || 0).toFixed(1)} pt`
      : ui.unavailable;
  const freshness = row.raw?.freshness;
  const freshnessText =
    freshness?.status !== "available"
      ? ui.unavailable
      : freshness.stale
      ? ui.staleData
      : ui.currentData;
  const specialist = finnResult?.context;

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
                {ui.indicator}
              </div>
              <div className="text-[14px] font-black leading-tight text-slate-950">{row.label}</div>
            </div>
          </div>

          <div className="lg:text-right">
            <div className="text-[10px] font-black uppercase tracking-[0.22em] text-slate-400 lg:hidden">
              {ui.value}
            </div>
            <div className="text-[14px] font-black text-slate-950">{row.value}</div>
          </div>

          <div>
            <div className="text-[10px] font-black uppercase tracking-[0.22em] text-slate-400 lg:hidden">
              {ui.development}
            </div>
            <span className="inline-flex items-center gap-2 rounded-full bg-slate-100 px-2.5 py-0.5 text-[9px] font-bold text-slate-600">
              <span className={`h-2 w-2 rounded-full ${row.signalTone.dot}`} />
              {row.direction}
            </span>
          </div>

          <div>
            <div className="text-[10px] font-black uppercase tracking-[0.22em] text-slate-400 lg:hidden">
              {ui.assessment}
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
          <div className="grid gap-4 lg:grid-cols-[1.2fr_1fr]">
            <div>
              <div className="text-[10px] font-black uppercase tracking-[0.22em] text-slate-400">
                {ui.details}
              </div>
              <p className="mt-1.5 text-[13px] font-medium leading-6 text-slate-600">
                {row.raw?.interpretation || row.raw?.uitleg || row.raw?.action || row.detail}
              </p>
            </div>

            <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
              {[
                [ui.dataSource, String(row.raw?.source || "—").replaceAll("_", " ")],
                [ui.periodLabel, ui[row.raw?.period || period] || row.raw?.period || period],
                [ui.freshness, freshnessText],
                [ui.latestSignal, row.timestamp ? formatTimestamp(row.timestamp, locale) : ui.live],
                [ui.scoreContribution, contributionText],
                [ui.sampleSize, row.raw?.sample_size ?? 1],
              ].map(([label, value]) => (
                <div key={label} className="rounded-xl border border-slate-200 bg-white px-3 py-2">
                  <div className="text-[9px] font-black uppercase tracking-[0.18em] text-slate-400">{label}</div>
                  <div className="mt-1 text-[12px] font-bold capitalize text-slate-800">{value}</div>
                </div>
              ))}
            </div>
          </div>

          <div className="mt-3 flex flex-wrap items-center justify-between gap-2 border-t border-slate-200 pt-3">
            <button
              type="button"
              onClick={requestFinnContext}
              disabled={finnLoading}
              className="inline-flex items-center gap-2 rounded-xl bg-slate-950 px-3 py-2 text-[10px] font-black uppercase tracking-[0.16em] text-white transition hover:bg-blue-600 disabled:cursor-wait disabled:opacity-60"
            >
              <Brain size={13} />
              {finnLoading ? ui.finnContextLoading : ui.askFinnContext}
            </button>
            {renderExpandedActions ? renderExpandedActions(row) : null}
          </div>

          {finnResult ? (
            <div className="mt-3 rounded-2xl border border-blue-100 bg-blue-50/70 p-3.5">
              <div className="flex items-center gap-2 text-[10px] font-black uppercase tracking-[0.2em] text-blue-700">
                <Brain size={13} />
                {ui.finnContext}
              </div>
              {finnResult.status === "available" && specialist ? (
                <div className="mt-2.5 grid gap-3 text-[12px] leading-5 text-slate-700 lg:grid-cols-3">
                  <div><strong className="block text-slate-950">{ui.details}</strong>{specialist.summary}</div>
                  <div><strong className="block text-slate-950">{ui.whyCounts}</strong>{specialist.why_it_counts}</div>
                  <div><strong className="block text-slate-950">{ui.confirmation}</strong>{specialist.confirmation}</div>
                  {specialist.conflicts?.length ? (
                    <div className="lg:col-span-3"><strong className="block text-slate-950">{ui.conflicts}</strong>{specialist.conflicts.join(" · ")}</div>
                  ) : null}
                </div>
              ) : (
                <p className="mt-2 text-[12px] font-medium leading-5 text-slate-600">{ui.finnContextUnavailable}</p>
              )}
            </div>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}

function TimeframeTabs({ value, onChange, loading, label, ui }) {
  return (
    <div
      role="group"
      aria-label={label}
      className={`inline-flex rounded-full border border-slate-200 bg-slate-100/80 p-1 transition-opacity ${
        loading ? "pointer-events-none opacity-60" : "opacity-100"
      }`}
    >
      {ANALYSIS_TIMEFRAMES.map((timeframe) => (
        <button
          key={timeframe}
          type="button"
          onClick={() => onChange(timeframe)}
          aria-pressed={value === timeframe}
          className={`min-w-[58px] rounded-full px-3 py-1.5 text-[10px] font-black uppercase tracking-[0.12em] transition sm:min-w-[70px] ${
            value === timeframe
              ? "bg-white text-blue-600 shadow-sm ring-1 ring-slate-200"
              : "text-slate-500 hover:bg-white/60 hover:text-slate-800"
          }`}
        >
          {ui[timeframe]}
        </button>
      ))}
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
  toolbar,
  renderExpandedActions,
  emptyState,
  emptyAction,
  symbol,
  period,
  locale,
  ui,
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

      {toolbar ? (
        <div className="flex items-center justify-end border-b border-slate-100 bg-slate-50/50 px-4 py-2.5">
          {toolbar}
        </div>
      ) : null}

      <div className="hidden border-b border-slate-100 px-4 py-2 lg:grid lg:grid-cols-[minmax(0,1.15fr)_minmax(120px,0.45fr)_minmax(150px,0.5fr)_minmax(220px,0.8fr)] lg:gap-3">
        {[ui.indicator, ui.value, ui.development, ui.assessment].map((label, index) => (
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
                category={id}
                symbol={symbol}
                period={period}
                locale={locale}
                ui={ui}
              />
            );
          })
        ) : (
          <div className="px-5 py-12 text-center">
            <div className="text-sm font-semibold text-slate-400">{emptyState}</div>
            {emptyAction ? <div className="mt-4">{emptyAction}</div> : null}
          </div>
        )}
      </div>
    </section>
  );
}

const EMPTY_FORWARD_RETURNS = {
  week: [],
  month: [],
  quarter: [],
  year: [],
};

const FORWARD_RETURNS_REQUEST_TIMEOUT_MS = 12000;
const FORWARD_RETURNS_CACHE_TTL_MS = 5 * 60_000;
const forwardReturnsCache = new Map();
const forwardReturnsInflight = new Map();

function getFreshForwardReturns(symbol) {
  const normalized = String(symbol || "BTC").toUpperCase();
  const cached = forwardReturnsCache.get(normalized);
  if (!cached) return null;
  if (Date.now() - cached.savedAt > FORWARD_RETURNS_CACHE_TTL_MS) return null;
  return cached.data;
}

function ForwardReturnsSection({ symbol, ui }) {
  const cachedData = getFreshForwardReturns(symbol);
  const [data, setData] = useState(cachedData || EMPTY_FORWARD_RETURNS);
  const [loading, setLoading] = useState(!cachedData);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let cancelled = false;
    let idleId = null;
    let timeoutId = null;

    const loadForwardReturns = async () => {
      const normalizedSymbol = String(symbol || "BTC").toUpperCase();
      const cached = getFreshForwardReturns(normalizedSymbol);
      if (cached) {
        setData(cached);
        setLoading(false);
        setFailed(false);
        return;
      }

      setLoading(true);
      setFailed(false);
      const withTimeout = (promise) =>
        Promise.race([
          promise,
          new Promise((_, reject) =>
            window.setTimeout(() => reject(new Error("forward_returns_timeout")), FORWARD_RETURNS_REQUEST_TIMEOUT_MS)
          ),
        ]);

      let request = forwardReturnsInflight.get(normalizedSymbol);
      if (!request) {
        request = Promise.allSettled([
          withTimeout(fetchForwardReturnsWeek(normalizedSymbol)),
          withTimeout(fetchForwardReturnsMonth(normalizedSymbol)),
          withTimeout(fetchForwardReturnsQuarter(normalizedSymbol)),
          withTimeout(fetchForwardReturnsYear(normalizedSymbol)),
        ]).finally(() => {
          forwardReturnsInflight.delete(normalizedSymbol);
        });
        forwardReturnsInflight.set(normalizedSymbol, request);
      }

      const results = await request;

      if (cancelled) return;

      const value = (index) =>
        results[index]?.status === "fulfilled" && Array.isArray(results[index].value)
          ? results[index].value
          : [];

      const nextData = {
        week: value(0),
        month: value(1),
        quarter: value(2),
        year: value(3),
      };
      forwardReturnsCache.set(normalizedSymbol, {
        data: nextData,
        savedAt: Date.now(),
      });
      setData(nextData);
      setFailed(
        results.every((result) => result.status === "rejected")
        || results.every((result, index) => value(index).length === 0)
      );
      setLoading(false);
    };

    if (typeof window !== "undefined" && "requestIdleCallback" in window) {
      idleId = window.requestIdleCallback(loadForwardReturns, { timeout: 1200 });
    } else {
      timeoutId = window.setTimeout(loadForwardReturns, 0);
    }

    return () => {
      cancelled = true;
      if (idleId !== null && typeof window.cancelIdleCallback === "function") {
        window.cancelIdleCallback(idleId);
      }
      if (timeoutId !== null) window.clearTimeout(timeoutId);
    };
  }, [symbol]);

  return (
    <section className="rounded-[24px] border border-slate-200/80 bg-white shadow-[0_18px_40px_-36px_rgba(15,23,42,0.26)]">
      <header className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-100 px-5 py-4">
        <div>
          <div className="text-[10px] font-black uppercase tracking-[0.24em] text-blue-600">
            {symbol} · {ui.market}
          </div>
          <h2 className="mt-1 text-lg font-black tracking-tight text-slate-950">
            {ui.forwardReturnsTitle}
          </h2>
          <p className="mt-1 text-xs font-medium text-slate-500">
            {ui.forwardReturnsSubtitle}
          </p>
        </div>
      </header>

      <div className="p-4 sm:p-5">
        {loading ? (
          <div className="flex min-h-36 items-center justify-center rounded-2xl bg-slate-50 text-xs font-bold text-slate-400">
            {ui.forwardReturnsLoading}
          </div>
        ) : failed ? (
          <div className="flex min-h-36 items-center justify-center rounded-2xl bg-slate-50 text-xs font-bold text-slate-400">
            {ui.unavailable}
          </div>
        ) : (
          <MarketForwardReturnTabs data={data} />
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
  const symbolFromUrl = searchParams.get("symbol")?.toUpperCase();
  const activeSymbol = symbolFromUrl || selectedAsset || "BTC";
  const [marketTimeframe, setMarketTimeframe] = useState("day");
  const [macroTimeframe, setMacroTimeframe] = useState("day");
  const [technicalTimeframe, setTechnicalTimeframe] = useState("day");
  const [activeAssetGroup, setActiveAssetGroup] = useState("crypto");
  const [expandedRowKey, setExpandedRowKey] = useState(null);
  const [technicalConfigModal, setTechnicalConfigModal] = useState(null);
  const [watchlistRows, setWatchlistRows] = useState([]);
  const [showChart, setShowChart] = useState(true);
  const [analysisChartInterval, setAnalysisChartInterval] = useState(DEFAULT_TRADINGVIEW_INTERVAL);
  const [hiddenIndicatorKeys, setHiddenIndicatorKeys] = useState([]);
  const appliedIndicatorsRef = useRef(new Set());
  const previousActiveSymbolRef = useRef(null);

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

  const periods = useMemo(
    () => ({
      market: marketTimeframe,
      macro: macroTimeframe,
      technical: technicalTimeframe,
    }),
    [macroTimeframe, marketTimeframe, technicalTimeframe]
  );
  const {
    workspace,
    watchlist: watchlistData,
    loading: workspaceLoading,
    watchlistLoading,
    isFallbackWorkspace,
    reloadWorkspace,
    reloadWatchlist,
  } = useAssetWorkspaceData(activeSymbol, periods);
  const { strategies = [] } = useStrategyData({ includeSetups: false });
  const [marketBestSetup, setMarketBestSetup] = useState(null);

  const categoryData = workspace?.categories || {};
  const marketDayData = categoryData.market?.rows || [];
  const macroData = categoryData.macro?.rows || [];
  const technicalData = categoryData.technical?.rows || [];
  const market = { score: categoryData.market?.score?.score ?? null };
  const macro = { score: categoryData.macro?.score?.score ?? null };
  const technical = { score: categoryData.technical?.score?.score ?? null };
  const workspaceAsset = workspace?.asset || null;
  const master = {
    weights: workspace?.master?.weights || {},
    bias: workspace?.master?.master_bias || "–",
  };
  const assetLive = workspace?.quote || null;
  const hasScoreData = [market.score, macro.score, technical.score].some((score) => score !== null);
  const hasResolvedWorkspace = Boolean(workspace);
  const marketLoading = workspaceLoading && !hasResolvedWorkspace;
  const macroLoading = workspaceLoading && !hasResolvedWorkspace;
  const technicalLoading = workspaceLoading && !hasResolvedWorkspace;
  const scoresLoading = workspaceLoading && !hasResolvedWorkspace;

  useEffect(() => {
    const activeRow = watchlistRows.find((row) => row.symbol === activeSymbol);
    if (!activeRow) return;
    const previousActiveSymbol = previousActiveSymbolRef.current;
    previousActiveSymbolRef.current = activeSymbol;
    if (previousActiveSymbol === activeSymbol) return;
    const nextGroup = normalizeAssetGroup(activeRow.assetClass);
    setActiveAssetGroup((current) => (current === nextGroup ? current : nextGroup));
  }, [activeSymbol, watchlistRows]);

  useEffect(() => {
    let cancelled = false;

    async function loadMarketBestSetup() {
      try {
        const result = await fetchActiveSetup(activeSymbol);
        if (!cancelled) {
          setMarketBestSetup(
            result && String(result.symbol || activeSymbol).toUpperCase() === activeSymbol
              ? result
              : null
          );
        }
      } catch (error) {
        console.error("Failed to load active setup for asset workspace", error);
        if (!cancelled) setMarketBestSetup(null);
      }
    }

    loadMarketBestSetup();
    return () => {
      cancelled = true;
    };
  }, [activeSymbol]);

  const planBridgeCandidate = useMemo(() => {
    const activeSetups = Array.isArray(workspace?.daily?.setup?.active_setups)
      ? workspace.daily.setup.active_setups
      : [];

    const matchingSetups = activeSetups
      .filter((item) => String(item?.symbol || "").toUpperCase() === activeSymbol)
      .map((item) => ({
        ...item,
        resolvedSetupId: item?.id ?? item?.setup_id ?? null,
        resolvedScore: normalizeScore(item?.score),
      }))
      .filter((item) => item.resolvedSetupId !== null)
      .sort((left, right) => Number(right.resolvedScore ?? -1) - Number(left.resolvedScore ?? -1));

    const linkedStrategiesBySetupId = new Map();
    strategies.forEach((strategy) => {
      const setupId = strategy?.setup_id ?? strategy?.setup?.id ?? null;
      if (setupId === null || setupId === undefined) return;
      const key = String(setupId);
      const current = linkedStrategiesBySetupId.get(key);
      if (!current || strategy?.is_active) {
        linkedStrategiesBySetupId.set(key, strategy);
      }
    });

    if (!matchingSetups.length) {
      const runtimeSetupId = marketBestSetup?.setup_id ?? marketBestSetup?.id ?? null;
      const linkedStrategy = runtimeSetupId == null
        ? null
        : linkedStrategiesBySetupId.get(String(runtimeSetupId)) || null;

      if (!marketBestSetup) return null;

      return {
        ...marketBestSetup,
        resolvedSetupId: runtimeSetupId,
        score: normalizeScore(marketBestSetup?.score),
        strategyId: linkedStrategy?.id ?? null,
        displayName:
          linkedStrategy?.name ||
          marketBestSetup?.name ||
          ui.planBridgeTitle,
      };
    }

    const linkedMatch = matchingSetups.find((item) =>
      linkedStrategiesBySetupId.has(String(item.resolvedSetupId))
    );
    const runtimeSetupId = marketBestSetup?.setup_id ?? marketBestSetup?.id ?? null;
    const runtimeMatch = runtimeSetupId == null
      ? null
      : matchingSetups.find((item) => String(item.resolvedSetupId) === String(runtimeSetupId));
    const bestMatch = runtimeMatch || linkedMatch || matchingSetups[0];
    const linkedStrategy = linkedStrategiesBySetupId.get(String(bestMatch.resolvedSetupId)) || null;
    const fallbackScore = normalizeScore(marketBestSetup?.score);

    return {
      ...bestMatch,
      score: bestMatch.resolvedScore ?? fallbackScore,
      strategyId: linkedStrategy?.id ?? null,
      displayName:
        linkedStrategy?.name ||
        bestMatch?.name ||
        marketBestSetup?.name ||
        ui.planBridgeTitle,
    };
  }, [activeSymbol, marketBestSetup?.id, marketBestSetup?.name, marketBestSetup?.score, marketBestSetup?.setup_id, strategies, ui.planBridgeTitle, workspace?.daily?.setup?.active_setups]);

  const addMarket = async (name) => {
    await marketIndicatorAdd(name, activeSymbol);
    await reloadWorkspace();
  };
  const addMacroIndicator = async (name) => {
    await macroDataAdd(name, activeSymbol);
    await reloadWorkspace();
  };
  const addTechnicalIndicator = async (name) => {
    await technicalDataAdd(name, activeSymbol);
    await reloadWorkspace();
  };
  const saveWeights = async (weights) => {
    const result = await updateIntelligenceWeights(weights);
    await reloadWorkspace();
    return result;
  };

  useEffect(() => {
    let cancelled = false;

    async function loadHiddenIndicators() {
      try {
        const response = await getAssistantPreferences();
        if (cancelled) return;
        setHiddenIndicatorKeys(
          normalizeHiddenIndicatorKeys(response?.preferences?.[ANALYSIS_HIDDEN_INDICATORS_KEY])
        );
        setAnalysisChartInterval(
          normalizeTradingViewInterval(response?.preferences?.[ANALYSIS_CHART_INTERVAL_KEY])
        );
      } catch (error) {
        if (!cancelled) {
          console.error("Failed to load hidden analysis indicators:", error);
        }
      }
    }

    void loadHiddenIndicators();
    return () => {
      cancelled = true;
    };
  }, []);

  const hideAnalysisIndicator = async (sectionId, row) => {
    const nextKey = buildHiddenIndicatorKey(activeSymbol, sectionId, row?.label || row?.name);
    const nextHiddenIndicatorKeys = hiddenIndicatorKeys.includes(nextKey)
      ? hiddenIndicatorKeys
      : [...hiddenIndicatorKeys, nextKey];

    setHiddenIndicatorKeys(nextHiddenIndicatorKeys);
    setExpandedRowKey(null);

    try {
      await updateAssistantPreferences({
        [ANALYSIS_HIDDEN_INDICATORS_KEY]: nextHiddenIndicatorKeys,
      });
    } catch (error) {
      console.error("Failed to persist hidden analysis indicators:", error);
    }
  };

  const handleAnalysisChartIntervalChange = async (nextInterval) => {
    const normalized = normalizeTradingViewInterval(nextInterval);
    setAnalysisChartInterval((current) => (current === normalized ? current : normalized));

    try {
      await updateAssistantPreferences({
        [ANALYSIS_CHART_INTERVAL_KEY]: normalized,
      });
    } catch (error) {
      console.error("Failed to persist analysis chart interval:", error);
    }
  };

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

  useEffect(() => {
    const refreshCompletedIndicator = (event) => {
      const detail = event?.detail || {};
      if (String(detail.assetSymbol || "").toUpperCase() !== activeSymbol) return;

      if (["market", "macro", "technical"].includes(detail.category)) void reloadWorkspace();
    };

    window.addEventListener(FINN_INDICATOR_MODAL_COMPLETED_EVENT, refreshCompletedIndicator);
    return () =>
      window.removeEventListener(FINN_INDICATOR_MODAL_COMPLETED_EVENT, refreshCompletedIndicator);
  }, [activeSymbol, reloadWorkspace]);

  useEffect(() => {
    let cancelled = false;

    async function loadWatchlistRows() {
        const nextRows = (watchlistData || []).map((row) => {
          const changeValue = Number(row?.change_24h);
          const tone = scoreTone(row?.score, ui);
          const assetClass = String(row?.asset_class || "").toLowerCase();
          return {
            symbol: row.symbol,
            displayName: row?.display_name || row?.displayName || ASSET_NAMES[row.symbol] || row.symbol,
            logoUrl: resolveAssetLogoUrl(row?.symbol, row?.logo_url || row?.logoUrl || null, assetClass),
            tradingviewSymbol: row?.tradingview_symbol || row?.tradingviewSymbol || null,
            assetClass,
            assetGroup: normalizeAssetGroup(assetClass),
            lastPrice: formatPrice(row?.price, locale),
            change24h: formatPercent(changeValue, 2),
            changeTone: Number.isFinite(changeValue)
            ? changeValue >= 0 ? "text-emerald-600" : "text-red-600"
            : "text-slate-400",
          score: formatScore(row?.score),
          bias: row?.score === null ? ui.unavailable : tone.label,
          biasTone: tone.pill,
        };
      });

      if (!cancelled) {
        setWatchlistRows(nextRows);
      }
    }

    if (!watchlistLoading) loadWatchlistRows();
    return () => {
      cancelled = true;
    };
  }, [locale, ui, watchlistData, watchlistLoading]);

  const visibleWatchlistRows = useMemo(
    () => watchlistRows.filter((row) => row.assetGroup === activeAssetGroup),
    [activeAssetGroup, watchlistRows]
  );
  const activeWatchlistRow = useMemo(
    () => watchlistRows.find((row) => row.symbol === activeSymbol) || null,
    [activeSymbol, watchlistRows]
  );
  const activeAssetName =
    activeWatchlistRow?.displayName ||
    workspaceAsset?.display_name ||
    ASSET_NAMES[activeSymbol] ||
    activeSymbol;
  const activeAssetLogo = resolveAssetLogoUrl(
    activeSymbol,
    activeWatchlistRow?.logoUrl || workspaceAsset?.logo_url || null,
    activeWatchlistRow?.assetClass || workspaceAsset?.asset_class || null,
  );
  const activeTradingViewSymbol =
    activeWatchlistRow?.tradingviewSymbol ||
    workspaceAsset?.tradingview_symbol ||
    null;

  const sections = useMemo(() => {
    const marketRows = filterVisibleRows(buildRows(marketDayData, locale, ui), activeSymbol, "market", hiddenIndicatorKeys);
    const macroRows = filterVisibleRows(buildRows(macroData, locale, ui), activeSymbol, "macro", hiddenIndicatorKeys);
    const technicalRows = filterVisibleRows(buildRows(technicalData, locale, ui), activeSymbol, "technical", hiddenIndicatorKeys);
    const visibleScore = (rows) => averageVisibleSectionScore(rows);
    const fallbackEmptyState = (score, rows, loadingState, defaultEmptyState) =>
      loadingState
        ? defaultEmptyState
        : visibleScore(rows) !== null || isFallbackWorkspace
          ? ui.fallbackReady
          : defaultEmptyState;
    const showEmptyAction = (score, rows, loadingState) =>
      !loadingState && !isFallbackWorkspace && visibleScore(rows) === null && rows.length === 0 && !Number.isFinite(Number(score));
    const emptyActionButton = (category) => (
      <button
        type="button"
        onClick={() => openSearch({ mode: "indicator", category })}
        className="inline-flex items-center gap-2 rounded-full border border-slate-200 bg-white px-3 py-1.5 text-[10px] font-black uppercase tracking-[0.16em] text-slate-700 transition hover:border-blue-200 hover:text-blue-600"
      >
        <Plus size={12} />
        {ui.addIndicator}
      </button>
    );

    return [
      {
        id: "market",
        title: locale?.startsWith("en") ? "Market" : locale?.startsWith("de") ? "Markt" : SECTION_META.market.label,
        eyebrow: locale?.startsWith("en") ? "Market evidence" : locale?.startsWith("de") ? "Marktbelege" : "Marktbewijs",
        icon: SECTION_META.market.icon,
        score: visibleScore(marketRows),
        insight: buildSectionInsight("market", visibleScore(marketRows), ui),
        rows: marketRows,
        emptyState: fallbackEmptyState(market?.score, marketRows, marketLoading, ui.marketEmpty),
        emptyAction: showEmptyAction(market?.score, marketRows, marketLoading) ? emptyActionButton("market") : null,
      },
      {
        id: "macro",
        title: locale?.startsWith("en") ? "Macro" : locale?.startsWith("de") ? "Makro" : SECTION_META.macro.label,
        eyebrow: locale?.startsWith("en") ? "Macro evidence" : locale?.startsWith("de") ? "Makrobelege" : "Macro-bewijs",
        icon: SECTION_META.macro.icon,
        score: visibleScore(macroRows),
        insight: buildSectionInsight("macro", visibleScore(macroRows), ui),
        rows: macroRows,
        emptyState: fallbackEmptyState(macro?.score, macroRows, macroLoading, ui.macroEmpty),
        emptyAction: showEmptyAction(macro?.score, macroRows, macroLoading) ? emptyActionButton("macro") : null,
      },
      {
        id: "technical",
        title: locale?.startsWith("en") ? "Technical" : locale?.startsWith("de") ? "Technisch" : SECTION_META.technical.label,
        eyebrow: locale?.startsWith("en") ? "Technical evidence" : locale?.startsWith("de") ? "Technische belege" : "Technisch bewijs",
        icon: SECTION_META.technical.icon,
        score: visibleScore(technicalRows),
        insight: buildSectionInsight("technical", visibleScore(technicalRows), ui),
        rows: technicalRows,
        emptyState: fallbackEmptyState(technical?.score, technicalRows, technicalLoading, ui.technicalEmpty),
        emptyAction: showEmptyAction(technical?.score, technicalRows, technicalLoading) ? emptyActionButton("technical") : null,
      },
    ];
  }, [activeSymbol, hiddenIndicatorKeys, isFallbackWorkspace, locale, macro, macroData, macroLoading, market, marketDayData, marketLoading, technical, technicalData, technicalLoading, ui]);

  const combinedSummary = useMemo(() => {
    const visibleScores = {
      market: sections.find((section) => section.id === "market")?.score ?? null,
      macro: sections.find((section) => section.id === "macro")?.score ?? null,
      technical: sections.find((section) => section.id === "technical")?.score ?? null,
    };
    const summary = summarizeWeightedScores(visibleScores, master?.weights, ui);
    const masterBias = String(master?.bias || "").trim();
    const hasMasterBias = masterBias && !/^[-–—]+$/.test(masterBias);
    const hasVisibleScores = Object.values(visibleScores).some((score) => score !== null);

    if (!hasVisibleScores) return summarizeContextScores([], ui);

    return {
      ...summary,
      bias: hasMasterBias ? formatBiasLabel(masterBias, ui) : summary.bias,
    };
  }, [master, sections, ui]);

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
        assetName={activeAssetName}
        assetLogoUrl={activeAssetLogo}
        price={formatPrice(assetLive?.price, locale)}
        change24h={assetLive?.change_24h}
        updatedAt={formatTimestamp(assetLive?.as_of || workspace?.generated_at, locale)}
        statusLabel={isFallbackWorkspace ? ui.fallbackData : assetLive?.stale ? ui.staleData : null}
        combinedSummary={combinedSummary}
        onSelectAsset={() => openSearch()}
        ui={ui}
      />

      <AssetList
        rows={visibleWatchlistRows}
        activeSymbol={activeSymbol}
        onSelect={handleAssetSelect}
        activeGroup={activeAssetGroup}
        onGroupChange={setActiveAssetGroup}
        onAddAsset={() => openSearch()}
        ui={ui}
      />

      <AnalysisChartSection
        interval={analysisChartInterval}
        symbol={activeSymbol}
        tradingViewSymbol={activeTradingViewSymbol}
        isOpen={showChart}
        onIntervalChange={handleAnalysisChartIntervalChange}
        onToggle={() => setShowChart((current) => !current)}
        ui={ui}
      />

      <section className="rounded-[24px] border border-slate-200/80 bg-white p-3.5 shadow-[0_18px_40px_-36px_rgba(15,23,42,0.26)]">
        <div className="mb-2.5 flex items-center">
          <div className="text-[10px] font-black uppercase tracking-[0.24em] text-blue-600">
            {ui.marketRegime}
          </div>
        </div>
        <GlobalMarketDecisionCard
          symbol={activeSymbol}
          snapshot={{
            data: workspace?.regime ?? null,
            loading: workspaceLoading && !workspace,
          }}
          fallbackMessage={isFallbackWorkspace ? ui.fallbackReady : null}
          compact
        />
      </section>

      <ScoreOverview
        market={{ score: sections.find((section) => section.id === "market")?.score ?? null }}
        macro={{ score: sections.find((section) => section.id === "macro")?.score ?? null }}
        technical={{ score: sections.find((section) => section.id === "technical")?.score ?? null }}
        combined={
          isFallbackWorkspace && combinedSummary.score === null
            ? { ...combinedSummary, bias: ui.fallbackData, tone: scoreTone(50, ui) }
            : combinedSummary
        }
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
            emptyAction={section.emptyAction}
            symbol={activeSymbol}
            period={
              section.id === "market"
                ? marketTimeframe
                : section.id === "macro"
                ? macroTimeframe
                : technicalTimeframe
            }
            locale={locale}
            ui={ui}
            toolbar={
              section.id === "market" ? (
                <TimeframeTabs
                  value={marketTimeframe}
                  onChange={setMarketTimeframe}
                  loading={marketLoading}
                  label={ui.marketPeriod}
                  ui={ui}
                />
              ) : section.id === "macro" ? (
                <TimeframeTabs
                  value={macroTimeframe}
                  onChange={setMacroTimeframe}
                  loading={macroLoading}
                  label={ui.macroPeriod}
                  ui={ui}
                />
              ) : section.id === "technical" ? (
                <TimeframeTabs
                  value={technicalTimeframe}
                  onChange={setTechnicalTimeframe}
                  loading={technicalLoading}
                  label={ui.technicalPeriod}
                  ui={ui}
                />
              ) : null
            }
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
                <button
                  type="button"
                  onClick={() => openSearch({ mode: "indicator", category: "macro" })}
                  className="inline-flex items-center gap-2 rounded-full border border-slate-200 bg-white px-3 py-1.5 text-[10px] font-black uppercase tracking-[0.16em] text-slate-700 transition hover:border-blue-200 hover:text-blue-600"
                >
                  <Plus size={12} />
                  {ui.addIndicator}
                </button>
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
              (row) => (
                <button
                  type="button"
                  onClick={(event) => {
                    event.stopPropagation();
                    void hideAnalysisIndicator(section.id, row);
                  }}
                  className="inline-flex items-center gap-2 rounded-2xl border border-slate-200 bg-white px-3 py-2 text-[11px] font-black uppercase tracking-[0.18em] text-slate-600 transition hover:border-red-200 hover:text-red-600"
                >
                  <Target size={12} />
                  {locale?.startsWith("en") ? "Hide" : locale?.startsWith("de") ? "Ausblenden" : "Verbergen"}
                </button>
              )
            }
          />
        ))}
      </section>

      <PlanBridge
        candidate={hasScoreData ? planBridgeCandidate : null}
        onOpenPlan={() => router.push(`/setup?symbol=${encodeURIComponent(activeSymbol)}`)}
        ui={ui}
      />

      <ForwardReturnsSection symbol={activeSymbol} ui={ui} />

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
