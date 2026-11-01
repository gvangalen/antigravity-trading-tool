"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
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
  TrendingUp,
  X,
} from "lucide-react";

import { useAsset } from "@/app/providers/AssetProvider";
import { useAuth } from "@/components/auth/AuthProvider";
import { useTranslation } from "@/app/providers/I18nProvider";
import { useModal } from "@/components/modal/ModalProvider";
import { useAssetWorkspaceData } from "@/hooks/useAssetWorkspaceData";
import { useWatchlist } from "@/hooks/useWatchlist";
import IndicatorConfigModal from "@/components/scoring/IndicatorConfigModal";
import { deletePairIndicatorConfig, savePairBenchmarkWeights, getBenchmarkCopySources, previewBenchmarkCopy, confirmBenchmarkCopy } from "@/lib/api/indicatorConfig";
import MarketForwardReturnTabs from "@/components/market/MarketForwardReturnTabs";
import {
  fetchForwardReturnsMonth,
  fetchForwardReturnsQuarter,
  fetchForwardReturnsWeek,
  fetchForwardReturnsYear,
  marketIndicatorAdd,
} from "@/lib/api/market";
import { macroDataAdd } from "@/lib/api/macro";
import { fetchSetupMarketMatches } from "@/lib/api/setups";
import { technicalDataAdd } from "@/lib/api/technical";
import { mapTechnicalToStudies } from "@/config/indicator_mapping";
import { removeFromWatchlist } from "@/lib/api/watchlist";
import { fetchTradingMarkets } from "@/lib/api/assets";
import { updateIntelligenceWeights } from "@/lib/api/scores";
import { getAssistantPreferences, updateAssistantPreferences } from "@/lib/api/ai";
import TradingViewSmartChart from "@/components/charts/TradingViewSmartChart";
import {
  ANALYSIS_CHART_INTERVAL_KEY,
  DEFAULT_TRADINGVIEW_INTERVAL,
  normalizeTradingViewInterval,
} from "../../../../../shared/tradingViewConfig";
import { matchesWorkspaceAsset } from "@/lib/workspace/workspaceAssetScope.mjs";
import { FINN_INDICATOR_MODAL_COMPLETED_EVENT } from "@/lib/finnCommandSearch";
import { formatBenchmarkScore, indicatorSourceFreshness, validatedDayEvidence } from "@/lib/workspace/canonicalScorePresentation.mjs";
import { quotePresentationStatus } from "@/lib/workspace/quotePresentationStatus.mjs";
import { marketConditionForScore } from "@/lib/setup/scoreConditions.mjs";
import { availableTradingQuotes, benchmarkScaleBands, benchmarkSetupSessionKey, benchmarkSetupView, resolveTradingQuote, selectedBenchmarkSetupMatch, tradingQuoteSessionKey, withSelectedBenchmarkSetup, withSelectedTradingQuote } from "@/lib/setup/benchmarkScale.mjs";

const SEARCH_OPEN_EVENT = "finn-command-search:open";

const SECTION_META = {
  market: {
    label: "Markt",
    eyebrow: "Market Evidence",
    icon: TrendingUp,
    empty: "No market indicators loaded yet.",
  },
  macro: {
    label: "Macro",
    eyebrow: "Macro Evidence",
    icon: Globe,
    empty: "No macro indicators loaded yet.",
  },
  technical: {
    label: "Technisch",
    eyebrow: "Technical Evidence",
    icon: LineChart,
    empty: "No technical indicators loaded yet.",
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
      benchmarkTitle: "Market conditions",
      benchmarkScore: "Your benchmark score",
      selectedPeriodScore: "Selected period score",
      benchmarkExplanation: "A weighted average of your Market, Macro and Technical indicators. Your setup is compared with it; the strategy decides whether a trade follows.",
      benchmarkDetails: "See indicators and weights",
      marketSituation: "Market situation",
      periodCompositionTitle: "Scores for the selected periods",
      benchmarkAssetTitle: (symbol) => `Your ${symbol} benchmark`,
      benchmarkBasis: "Your indicators. Your measure.",
      benchmarkNow: "Now",
      benchmarkRoundedRule: "Setup zones compare the score rounded to a whole point.",
      benchmarkSetupLabel: "Compare with setup",
      benchmarkSetupZone: "Saved setup condition",
      benchmarkNoSetup: "No saved setup for this asset.",
      benchmarkNoCondition: "This setup has no benchmark condition. Review its other rules in My Plan.",
      benchmarkMissing: "No complete current benchmark. The missing component scores are shown below.",
      benchmarkUpdating: "The setup comparison is updating. No current match can be confirmed yet.",
      benchmarkReadError: "The saved setups could not be loaded. No current match can be confirmed.",
      benchmarkMatches: "Benchmark condition reached. Check the remaining plan rules separately.",
      benchmarkOutside: "Benchmark condition not reached. The current score is outside the saved range.",
      benchmarkCustom: (min, max) => min !== null && max !== null ? `${min}–${max}` : min !== null ? `From ${min}` : `Up to ${max}`,
      confidence: "Confidence",
      bias: "Bias",
      watchlist: "Watchlist",
      addAsset: "Add asset",
      latest: "Last",
      chartTitle: "TradingView chart",
      chartClose: "Close chart",
      chartOpen: "Open chart",
      chartIndicators: "Selected technical indicators",
      chartIndicatorNote: "TradingView uses the selected pair and chart interval for visual indicators. Score 2.0 uses its own source readings and rules.",
      chartLoading: "Loading the selected market's chart…",
      chartStudyFallback: "TradingView could not load the indicators. The price chart is still available.",
      contextScores: "Context scores",
      scoreSourceDate: "Oldest indicator source",
      scoreSourceUnknown: "Source date incomplete",
      scoreSourceLimit: "Saved indicator scores are not a live trading signal.",
      marketRegime: "Market regime",
      addIndicator: "Add indicator",
      editIndicator: "Edit indicator",
      removeIndicator: "Remove from this market",
      removeIndicatorConfirm: "Remove indicator",
      removeIndicatorContext: (name, pair) => `Remove ${name} from ${pair}?`,
      removeIndicatorImpact: "This market's benchmark will be recalculated. Other trading pairs stay unchanged.",
      removeIndicatorSuccess: (name, pair) => `${name} removed from ${pair}.`,
      positive: "Positive",
      negative: "Negative",
      neutral: "Neutral",
      indicatorStates: { low: "Little support", mixed: "Mixed", high: "Strong support" },
      unavailable: "Insufficient data",
      notConfigured: "No indicators added",
      pendingSource: "This indicator is configured but has no source reading yet. The next source refresh will try again; until then there is no score.",
      historyPending: (observed, required) => `This indicator has ${observed} of ${required} dated source days. We will retry the historical source; there is no score until enough real readings are available.`,
      indicatorSourceStale: "The latest source reading is too old for a current score. The source will be refreshed again.",
      scorePending: "A current source reading exists, but no indicator score is available. Check the score rule or wait for the next calculation.",
      scoreRebuilding: "Your indicator choices changed. The score is being recalculated; previous readings have not been erased.",
      scoreIncomplete: "One or more selected indicators do not have a usable score yet. The group score will return when their evidence is complete.",
      missingScoreRule: "A source reading is available, but no scoring rule is configured. This indicator has no score yet.",
      scoringRule: "Scoring rule",
      scoreCalculationTitle: "How was this score calculated?",
      scoreTitle: "Score",
      scorePoints: "points",
      scoreWeight: "Weight in group score",
      calculation: "Calculation",
      usedData: "Data used",
      scaledReading: "Reading on a 0–100 scale",
      groupContribution: "Contribution to group score",
      coverageValue: (observed, required, window) => `${observed} source days / at least ${required} in the last ${window} days`,
      systemScoringRule: "System rule",
      personalScoringRule: "Your curve",
      priceRangeMethod: (position) => `Measured price position in its recent 30-day range: ${position}/100. This is not an entry signal.`,
      dxyRangeMethod: (position) => `Measured DXY position in its recent 90-day range: ${position}/100. Higher dollar strength lowers this broad risk-context score; this is not an asset signal.`,
      volumeMethod: (position) => `Trading volume relative to its recent median: ${position}/100 (50 is the median). Volume alone says nothing about price direction.`,
      change24hMethod: (position) => `The 24-hour price change maps to ${position}/100 on a -20% to +20% scale. This is short-term direction, not an entry signal.`,
      normalizedInput: "Normalized reading",
      market: "Market",
      macro: "Macro",
      technical: "Technical",
      combined: "Combined",
      setup: "Setup",
      tuneEngine: "Adjust weights",
      closeTuning: "Close tuning",
      weight: "Weight",
      weightInfluence: "Influence on your benchmark score",
      balancedWeights: "The weights add up to 100%.",
      unbalancedWeights: "The weights must add up to 100%.",
      applyWeights: "Apply weights",
      savingWeights: "Saving...",
      copyBenchmark: "Copy benchmark from another trading pair",
      copySource: "Choose source pair",
      copyClose: "Close",
      copyEmpty: "No other configured benchmark yet.",
      copyIndicators: "indicators",
      copyReplace: "Existing target settings will be replaced; readings and scores will be recalculated.",
      copyReplaced: "To replace",
      copyConfirm: "Confirm copy",
      copyUnsupported: "These indicators are unavailable for the target pair",
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
      latestSignal: "Source observed",
      missingSourceMoment: "Not recorded",
      dataSource: "Source",
      periodLabel: "Period",
      freshness: "Freshness",
      currentData: "Current",
      fallbackData: "Fallback",
      staleData: "Stale",
      closedMarketQuote: "Market closed · last available quote",
      fallbackReady: "Fallback data is available. Detailed context will return automatically once the full workspace feed responds again.",
      scoreContribution: "Score contribution",
      sampleSize: "Readings in period",
      scoreHistory: "Dated source days for score",
      scoreHistoryValue: (observed, required, window) => `${observed}/${required} in the last ${window} days`,
      finnContextUnavailable: "Extra AI context is currently unavailable. The current data and rule-based explanation above remain available.",
      live: "Live",
      edit: "Edit",
      remove: "Remove",
      watchlistActions: "Actions",
      watchlistRemoveLabel: "Remove asset",
      watchlistRemoveTitle: "Remove asset?",
      watchlistRemoveContext: (symbol) => `${symbol} will be removed from your active watchlist.`,
      watchlistRemoveImpact: "The asset stays available, but disappears from your current tracking and quick context switches.",
      watchlistRemoveSafety: "This does not trigger orders or data changes. Only your personal watchlist changes.",
      watchlistRemoveConsequence: "After confirming, your watchlist refreshes and Finn focuses on your remaining assets.",
      watchlistRemoveConfirm: "Remove asset",
      watchlistRemoveBusy: "Removing asset...",
      watchlistRemoveSuccess: (symbol) => `${symbol} removed from watchlist`,
      modalCancelLabel: "Cancel",
      modalContextLabel: "Context",
      modalImpactLabel: "Impact",
      modalSafetyLabel: "Safety",
      modalConsequenceLabel: "After this",
      modalCloseLabel: "Close",
      marketEmpty: "You have not added any market indicators yet. Add one to build your market score.",
      macroEmpty: "You have not added any macro indicators yet. Add one to build your macro score.",
      technicalEmpty: "You have not added any technical indicators yet. Add one to build your technical score.",
      loadingMarket: "Loading market data...",
      loadingMacro: "Loading macro data...",
      loadingTechnical: "Loading technical data...",
      loadingScores: "Loading scores...",
      indicatorAssessment: (label, direction, signal) => `${label} is ${direction.toLowerCase()} and currently gives a ${signal.toLowerCase()} signal.`,
      rsiAssessment: {
        high: "RSI supports momentum and confirms a stronger direction.",
        mid: "RSI is neutral; momentum is currently balanced.",
        low: "RSI points to weak momentum and does not yet confirm follow-through.",
      },
      positiveMoveWeakScore: (value, score) => `Price is up ${value}, but the configured scoring thresholds still place this move in the weak zone (${score}/100).`,
      aboveMa200: "Above MA200",
      belowMa200: "Below MA200",
      aboveMa50: "Above MA50",
      belowMa50: "Below MA50",
      indicatorLabels: {
        sp500: "S&P 500",
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
        scoreWithoutRows: (category, score) => `${category}: ${score}/100. The indicator details are not available in this view.`,
        measured: (category, score, names, extra) => `${category}: ${score}/100 from ${names}${extra ? ` and ${extra} other indicator(s)` : ""}.`,
      },
    };
  }
  if (normalized.startsWith("de")) {
    return {
      activeAnalysis: "Aktive analyse",
      updated: "Aktualisiert",
      combinedScore: "Kombinierter score",
      benchmarkTitle: "Marktbedingungen",
      benchmarkScore: "Dein Benchmark-Score",
      selectedPeriodScore: "Score des gewählten Zeitraums",
      benchmarkExplanation: "Gewichteter Durchschnitt deiner Markt-, Makro- und technischen Indikatoren. Dein Setup wird damit verglichen; die Strategie entscheidet über einen Trade.",
      benchmarkDetails: "Indikatoren und Gewichtung ansehen",
      marketSituation: "Marktlage",
      periodCompositionTitle: "Scores der gewählten Zeiträume",
      benchmarkAssetTitle: (symbol) => `Dein ${symbol}-Benchmark`,
      benchmarkBasis: "Deine Indikatoren. Dein Maßstab.",
      benchmarkNow: "Jetzt",
      benchmarkRoundedRule: "Setup-Zonen vergleichen den auf ganze Punkte gerundeten Score.",
      benchmarkSetupLabel: "Mit Setup vergleichen",
      benchmarkSetupZone: "Gespeicherte Setup-Bedingung",
      benchmarkNoSetup: "Für dieses Asset ist kein Setup gespeichert.",
      benchmarkNoCondition: "Dieses Setup hat keine Benchmark-Bedingung. Die übrigen Regeln stehen in Mein Plan.",
      benchmarkMissing: "Kein vollständiger aktueller Benchmark. Die fehlenden Teilwerte stehen unten.",
      benchmarkUpdating: "Der Setup-Vergleich wird aktualisiert. Eine aktuelle Übereinstimmung ist noch nicht bestätigt.",
      benchmarkReadError: "Die gespeicherten Setups konnten nicht geladen werden. Eine aktuelle Übereinstimmung ist nicht bestätigt.",
      benchmarkMatches: "Benchmark-Bedingung erreicht. Prüfe die übrigen Planregeln separat.",
      benchmarkOutside: "Benchmark-Bedingung nicht erreicht. Der aktuelle Wert liegt außerhalb des gespeicherten Bereichs.",
      benchmarkCustom: (min, max) => min !== null && max !== null ? `${min}–${max}` : min !== null ? `Ab ${min}` : `Bis ${max}`,
      confidence: "Vertrauen",
      bias: "Bias",
      watchlist: "Watchlist",
      addAsset: "Asset hinzufügen",
      latest: "Letzte",
      chartTitle: "TradingView-chart",
      chartClose: "Chart schließen",
      chartOpen: "Chart öffnen",
      chartIndicators: "Ausgewählte technische Indikatoren",
      chartIndicatorNote: "Für visuelle Indikatoren verwendet TradingView das gewählte Handelspaar und Chartintervall. Score 2.0 verwendet eigene Messwerte und Regeln.",
      chartLoading: "Chart für den gewählten Markt wird geladen…",
      chartStudyFallback: "TradingView konnte die Indikatoren nicht laden. Der Kurschart bleibt verfügbar.",
      contextScores: "Kontext-scores",
      scoreSourceDate: "Älteste Indikatorquelle",
      scoreSourceUnknown: "Quelldatum unvollständig",
      scoreSourceLimit: "Gespeicherte Indikatorwerte sind kein aktuelles Handelssignal.",
      marketRegime: "Marktregime",
      addIndicator: "Indikator hinzufügen",
      editIndicator: "Indikator bearbeiten",
      removeIndicator: "Aus diesem Markt entfernen",
      removeIndicatorConfirm: "Indikator entfernen",
      removeIndicatorContext: (name, pair) => `${name} aus ${pair} entfernen?`,
      removeIndicatorImpact: "Der Benchmark dieses Marktes wird neu berechnet. Andere Handelspaare bleiben unverändert.",
      removeIndicatorSuccess: (name, pair) => `${name} aus ${pair} entfernt.`,
      positive: "Positiv",
      negative: "Negativ",
      neutral: "Neutral",
      indicatorStates: { low: "Wenig Unterstützung", mixed: "Gemischt", high: "Starke Unterstützung" },
      unavailable: "Unzureichende Daten",
      notConfigured: "Keine Indikatoren hinzugefügt",
      pendingSource: "Dieser Indikator ist eingerichtet, hat aber noch keinen Messwert. Bei der nächsten Datenaktualisierung wird die Quelle erneut abgefragt; bis dahin gibt es keinen Score.",
      historyPending: (observed, required) => `Für diesen Indikator liegen ${observed} von ${required} datierten Quelltagen vor. Wir fragen die historische Quelle erneut ab; bis genügend echte Messwerte vorliegen, gibt es keinen Score.`,
      indicatorSourceStale: "Der letzte Quellwert ist für einen aktuellen Score zu alt. Die Quelle wird erneut abgefragt.",
      scorePending: "Ein aktueller Quellwert liegt vor, aber kein Indikator-Score. Prüfe die Scoreregel oder warte auf die nächste Berechnung.",
      scoreRebuilding: "Deine Indikatorauswahl hat sich geändert. Der Score wird neu berechnet; frühere Messwerte wurden nicht gelöscht.",
      scoreIncomplete: "Mindestens ein gewählter Indikator hat noch keinen nutzbaren Score. Der Gruppenscore erscheint wieder, sobald die Daten vollständig sind.",
      missingScoreRule: "Ein Quellwert ist vorhanden, aber keine Scoreregel eingerichtet. Dieser Indikator hat noch keinen Score.",
      scoringRule: "Scoreregel",
      scoreCalculationTitle: "Wie wurde dieser Score berechnet?",
      scoreTitle: "Score",
      scorePoints: "Punkte",
      scoreWeight: "Gewicht im Gruppenscore",
      calculation: "Berechnung",
      usedData: "Verwendete Daten",
      scaledReading: "Messwert auf einer Skala von 0–100",
      groupContribution: "Beitrag zum Gruppenscore",
      coverageValue: (observed, required, window) => `${observed} Quelltage / mindestens ${required} in den letzten ${window} Tagen`,
      systemScoringRule: "Systemregel",
      personalScoringRule: "Deine Kurve",
      priceRangeMethod: (position) => `Gemessene Preisposition im jüngsten 30-Tage-Bereich: ${position}/100. Das ist kein Einstiegssignal.`,
      dxyRangeMethod: (position) => `Gemessene DXY-Position im jüngsten 90-Tage-Bereich: ${position}/100. Ein stärkerer Dollar senkt diesen allgemeinen Risikokontext-Score; das ist kein Assetsignal.`,
      volumeMethod: (position) => `Handelsvolumen relativ zum jüngsten Median: ${position}/100 (50 entspricht dem Median). Volumen allein zeigt keine Preisrichtung.`,
      change24hMethod: (position) => `Die 24-Stunden-Preisänderung ergibt ${position}/100 auf einer Skala von -20 % bis +20 %. Das ist eine kurzfristige Richtung, kein Einstiegssignal.`,
      normalizedInput: "Normierter Messwert",
      market: "Markt",
      macro: "Makro",
      technical: "Technisch",
      combined: "Kombiniert",
      setup: "Setup",
      tuneEngine: "Gewichtung anpassen",
      closeTuning: "Abstimmung schließen",
      weight: "Gewichtung",
      weightInfluence: "Einfluss auf deinen Benchmark-Score",
      balancedWeights: "Die Gewichtungen ergeben zusammen 100 %.",
      unbalancedWeights: "Die Gewichtungen müssen zusammen 100 % ergeben.",
      applyWeights: "Gewichtungen anwenden",
      savingWeights: "Speichern...",
      copyBenchmark: "Benchmark von anderem Handelspaar kopieren",
      copySource: "Quellpaar wählen",
      copyClose: "Schließen",
      copyEmpty: "Noch keine andere konfigurierte Benchmark vorhanden.",
      copyIndicators: "Indikatoren",
      copyReplace: "Bestehende Zielkonfigurationen werden ersetzt; Messwerte und Scores werden neu berechnet.",
      copyReplaced: "Zu ersetzen",
      copyConfirm: "Kopie bestätigen",
      copyUnsupported: "Diese Indikatoren sind für das Zielpaar nicht verfügbar",
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
      latestSignal: "Quellzeitpunkt",
      missingSourceMoment: "Nicht erfasst",
      dataSource: "Quelle",
      periodLabel: "Zeitraum",
      freshness: "Aktualität",
      currentData: "Aktuell",
      fallbackData: "Fallback",
      staleData: "Veraltet",
      closedMarketQuote: "Börse geschlossen · letzter verfügbarer Kurs",
      fallbackReady: "Fallback-Daten sind verfügbar. Die Detailkontexte erscheinen automatisch wieder, sobald der vollständige Workspace-Feed erneut antwortet.",
      scoreContribution: "Score-Beitrag",
      sampleSize: "Messungen im Zeitraum",
      scoreHistory: "Datierte Quelltage für den Score",
      scoreHistoryValue: (observed, required, window) => `${observed}/${required} in den letzten ${window} Tagen`,
      finnContextUnavailable: "Zusätzlicher AI-Kontext ist derzeit nicht verfügbar. Die aktuellen Daten und die regelbasierte Erklärung oben bleiben verfügbar.",
      live: "Live",
      edit: "Bearbeiten",
      remove: "Entfernen",
      watchlistActions: "Aktionen",
      watchlistRemoveLabel: "Asset entfernen",
      watchlistRemoveTitle: "Asset entfernen?",
      watchlistRemoveContext: (symbol) => `${symbol} wird aus deiner aktiven Watchlist entfernt.`,
      watchlistRemoveImpact: "Das Asset bleibt verfügbar, verschwindet aber aus deinem aktuellen Tracking und schnellen Kontextwechseln.",
      watchlistRemoveSafety: "Dadurch werden keine Orders oder Daten geändert. Nur deine persönliche Watchlist wird angepasst.",
      watchlistRemoveConsequence: "Nach dem Bestätigen wird die Watchlist neu geladen und FINN fokussiert die verbleibenden Assets.",
      watchlistRemoveConfirm: "Asset entfernen",
      watchlistRemoveBusy: "Asset wird entfernt...",
      watchlistRemoveSuccess: (symbol) => `${symbol} aus Watchlist entfernt`,
      modalCancelLabel: "Abbrechen",
      modalContextLabel: "Kontext",
      modalImpactLabel: "Auswirkung",
      modalSafetyLabel: "Sicherheit",
      modalConsequenceLabel: "Danach",
      modalCloseLabel: "Schließen",
      marketEmpty: "Du hast noch keine Marktindikatoren hinzugefügt. Füge einen hinzu, um deinen Markt-Score aufzubauen.",
      macroEmpty: "Du hast noch keine Makroindikatoren hinzugefügt. Füge einen hinzu, um deinen Makro-Score aufzubauen.",
      technicalEmpty: "Du hast noch keine technischen Indikatoren hinzugefügt. Füge einen hinzu, um deinen technischen Score aufzubauen.",
      loadingMarket: "Marktdaten werden geladen...",
      loadingMacro: "Makrodaten werden geladen...",
      loadingTechnical: "Technische Daten werden geladen...",
      loadingScores: "Scores werden geladen...",
      indicatorAssessment: (label, direction, signal) => `${label} ist ${direction.toLowerCase()} und liefert derzeit ein ${signal.toLowerCase()} Signal.`,
      rsiAssessment: {
        high: "RSI unterstützt das Momentum und bestätigt eine stärkere Richtung.",
        mid: "RSI ist neutral; das Momentum ist derzeit ausgeglichen.",
        low: "RSI weist auf schwaches Momentum hin und bestätigt noch keine Fortsetzung.",
      },
      positiveMoveWeakScore: (value, score) => `Der Kurs steigt um ${value}, aber die konfigurierten Score-Grenzen ordnen diese Bewegung noch der schwachen Zone zu (${score}/100).`,
      aboveMa200: "Über MA200",
      belowMa200: "Unter MA200",
      aboveMa50: "Über MA50",
      belowMa50: "Unter MA50",
      indicatorLabels: {
        sp500: "S&P 500",
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
        scoreWithoutRows: (category, score) => `${category}: ${score}/100. Die Indikatordetails sind in dieser Ansicht nicht verfügbar.`,
        measured: (category, score, names, extra) => `${category}: ${score}/100 aus ${names}${extra ? ` und ${extra} weiteren Indikator(en)` : ""}.`,
      },
    };
  }
  return {
    activeAnalysis: "Actieve analyse",
    updated: "Bijgewerkt",
    combinedScore: "Gecombineerde score",
    benchmarkTitle: "Marktomstandigheden",
    benchmarkScore: "Jouw benchmarkscore",
    selectedPeriodScore: "Score gekozen periode",
    benchmarkExplanation: "Gewogen gemiddelde van jouw Markt-, Macro- en Technisch-indicatoren. Je setup wordt hiermee vergeleken; de strategie bepaalt of er een trade volgt.",
    benchmarkDetails: "Bekijk indicatoren en weging",
    marketSituation: "Marktsituatie",
    periodCompositionTitle: "Scores voor de gekozen perioden",
    benchmarkAssetTitle: (symbol) => `Jouw ${symbol}-benchmark`,
    benchmarkBasis: "Jouw indicatoren. Jouw meetlat.",
    benchmarkNow: "Nu",
    benchmarkRoundedRule: "Setupzones vergelijken de op hele punten afgeronde score.",
    benchmarkSetupLabel: "Vergelijk met setup",
    benchmarkSetupZone: "Opgeslagen setupvoorwaarde",
    benchmarkNoSetup: "Voor deze asset is geen setup opgeslagen.",
    benchmarkNoCondition: "Deze setup heeft geen benchmarkvoorwaarde. Bekijk de overige regels in Mijn Plan.",
    benchmarkMissing: "Geen complete actuele benchmark. De ontbrekende deelscores staan hieronder.",
    benchmarkUpdating: "De setupvergelijking wordt bijgewerkt. Een actuele match is nog niet bevestigd.",
    benchmarkReadError: "De opgeslagen setups konden niet worden geladen. Een actuele match is niet bevestigd.",
    benchmarkMatches: "Benchmarkvoorwaarde bereikt. Controleer de andere planregels afzonderlijk.",
    benchmarkOutside: "Benchmarkvoorwaarde niet bereikt. De huidige score valt buiten het opgeslagen bereik.",
    benchmarkCustom: (min, max) => min !== null && max !== null ? `${min}–${max}` : min !== null ? `Vanaf ${min}` : `Tot ${max}`,
    confidence: "Vertrouwen",
    bias: "Bias",
    watchlist: "Watchlist",
    addAsset: "Asset toevoegen",
    latest: "Laatste",
    chartTitle: "TradingView-chart",
    chartClose: "Chart sluiten",
    chartOpen: "Chart openen",
    chartIndicators: "Geselecteerde technische indicatoren",
    chartIndicatorNote: "Voor visuele indicatoren gebruikt TradingView het gekozen handelspaar en grafiektijdsframe. Score 2.0 gebruikt eigen metingen en regels.",
    chartLoading: "Grafiek voor de gekozen markt wordt geladen…",
    chartStudyFallback: "TradingView kon de indicatoren niet laden. De koersgrafiek blijft beschikbaar.",
    contextScores: "Contextscores",
    scoreSourceDate: "Oudste indicatorbron",
    scoreSourceUnknown: "Brondatum onvolledig",
    scoreSourceLimit: "Opgeslagen indicatorscores zijn geen actueel handelssignaal.",
    marketRegime: "Marktregime",
    addIndicator: "Indicator toevoegen",
    editIndicator: "Indicator bewerken",
    removeIndicator: "Verwijderen uit deze markt",
    removeIndicatorConfirm: "Indicator verwijderen",
    removeIndicatorContext: (name, pair) => `${name} verwijderen uit ${pair}?`,
    removeIndicatorImpact: "De benchmark van deze markt wordt opnieuw berekend. Andere handelsparen blijven ongewijzigd.",
    removeIndicatorSuccess: (name, pair) => `${name} verwijderd uit ${pair}.`,
    positive: "Positief",
    negative: "Negatief",
    neutral: "Neutraal",
    indicatorStates: { low: "Weinig steun", mixed: "Gemengd", high: "Veel steun" },
    unavailable: "Onvoldoende data",
    notConfigured: "Geen indicatoren toegevoegd",
    pendingSource: "Deze indicator is ingesteld, maar heeft nog geen bronmeting. Bij de volgende gegevensverversing wordt de bron opnieuw gelezen; tot die tijd is er geen score.",
    historyPending: (observed, required) => `Deze indicator heeft ${observed} van de ${required} gedateerde brondagen. We proberen de historische bron opnieuw; tot er genoeg echte metingen zijn, is er geen score.`,
    indicatorSourceStale: "De laatste bronmeting is te oud voor een actuele score. De bron wordt opnieuw ververst.",
    scorePending: "Er is een actuele bronmeting, maar nog geen indicatorscore. Controleer de scoreregel of wacht op de volgende berekening.",
    scoreRebuilding: "Je indicatoren zijn gewijzigd. De score wordt opnieuw berekend; eerdere metingen zijn niet gewist.",
    scoreIncomplete: "Een of meer gekozen indicatoren hebben nog geen bruikbare score. De groepsscore komt terug zodra hun gegevens compleet zijn.",
    missingScoreRule: "Er is een bronmeting, maar geen scoreregel ingesteld. Deze indicator heeft daarom nog geen score.",
    scoringRule: "Scoreregel",
    scoreCalculationTitle: "Hoe is deze score berekend?",
    scoreTitle: "Score",
    scorePoints: "punten",
    scoreWeight: "Gewicht in groepsscore",
    calculation: "Berekening",
    usedData: "Gebruikte gegevens",
    scaledReading: "Meting op schaal 0–100",
    groupContribution: "Bijdrage aan groepsscore",
    coverageValue: (observed, required, window) => `${observed} brondagen / minimaal ${required} in de laatste ${window} dagen`,
    systemScoringRule: "Systeemregel",
    personalScoringRule: "Jouw curve",
    priceRangeMethod: (position) => `Gemeten prijspositie in het recente 30-daagse bereik: ${position}/100. Dit is geen instapsignaal.`,
    dxyRangeMethod: (position) => `Gemeten DXY-positie in het recente 90-daagse bereik: ${position}/100. Een sterkere dollar verlaagt deze algemene risicocontextscore; dit is geen assetsignaal.`,
    volumeMethod: (position) => `Handelsvolume ten opzichte van de recente mediaan: ${position}/100 (50 is de mediaan). Volume alleen zegt niets over de koersrichting.`,
    change24hMethod: (position) => `De koersverandering in 24 uur komt uit op ${position}/100 op een schaal van -20% tot +20%. Dit is kortetermijnrichting, geen instapsignaal.`,
    normalizedInput: "Genormaliseerde meting",
    market: "Markt",
    macro: "Macro",
    technical: "Technisch",
    combined: "Gecombineerd",
    setup: "Setup",
    tuneEngine: "Wegingen aanpassen",
    closeTuning: "Afstemmen sluiten",
    weight: "Weging",
    weightInfluence: "Invloed op jouw benchmarkscore",
    balancedWeights: "De wegingen komen samen uit op 100%.",
    unbalancedWeights: "De wegingen moeten samen op 100% uitkomen.",
    applyWeights: "Wegingen toepassen",
    savingWeights: "Opslaan...",
    copyBenchmark: "Kopieer benchmark van ander handelspaar",
    copySource: "Kies bronpaar",
    copyClose: "Sluiten",
    copyEmpty: "Er is nog geen andere ingestelde benchmark.",
    copyIndicators: "indicatoren",
    copyReplace: "Bestaande instellingen van het doelpaar worden vervangen; metingen en scores worden opnieuw berekend.",
    copyReplaced: "Te vervangen",
    copyConfirm: "Kopiëren bevestigen",
    copyUnsupported: "Deze indicatoren zijn niet beschikbaar voor het doelpaar",
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
    latestSignal: "Bronmoment",
    missingSourceMoment: "Niet vastgelegd",
    dataSource: "Bron",
    periodLabel: "Periode",
    freshness: "Actualiteit",
    currentData: "Actueel",
    fallbackData: "Fallback",
    staleData: "Verouderd",
    closedMarketQuote: "Beurs gesloten · laatst beschikbare koers",
    fallbackReady: "Fallback-data is beschikbaar. De detailcontext komt automatisch terug zodra de volledige workspace-feed weer antwoord geeft.",
    scoreContribution: "Scorebijdrage",
    sampleSize: "Metingen in periode",
    scoreHistory: "Gedateerde brondagen voor score",
    scoreHistoryValue: (observed, required, window) => `${observed}/${required} in de laatste ${window} dagen`,
    finnContextUnavailable: "Extra AI-context is nu niet beschikbaar. De actuele data en regeluitleg hierboven blijven wel beschikbaar.",
    live: "Live",
    edit: "Bewerken",
    remove: "Verwijderen",
    watchlistActions: "Acties",
    watchlistRemoveLabel: "Asset verwijderen",
    watchlistRemoveTitle: "Asset verwijderen?",
    watchlistRemoveContext: (symbol) => `${symbol} verdwijnt uit je actieve watchlist.`,
    watchlistRemoveImpact: "De asset blijft beschikbaar, maar verdwijnt uit je huidige tracking en snelle contextwissels.",
    watchlistRemoveSafety: "Dit start geen orders of datawijzigingen. Alleen je persoonlijke watchlist verandert.",
    watchlistRemoveConsequence: "Na bevestigen vernieuwt je watchlist en focust FINN op je overgebleven assets.",
    watchlistRemoveConfirm: "Asset verwijderen",
    watchlistRemoveBusy: "Asset verwijderen...",
    watchlistRemoveSuccess: (symbol) => `${symbol} verwijderd van watchlist`,
    modalCancelLabel: "Annuleren",
    modalContextLabel: "Context",
    modalImpactLabel: "Impact",
    modalSafetyLabel: "Veiligheid",
    modalConsequenceLabel: "Daarna",
    modalCloseLabel: "Sluiten",
    marketEmpty: "Je hebt nog geen marktindicatoren toegevoegd. Voeg er een toe om je marktscore op te bouwen.",
    macroEmpty: "Je hebt nog geen macro-indicatoren toegevoegd. Voeg er een toe om je macroscore op te bouwen.",
    technicalEmpty: "Je hebt nog geen technische indicatoren toegevoegd. Voeg er een toe om je technische score op te bouwen.",
    loadingMarket: "Marktdata laden...",
    loadingMacro: "Macrodata laden...",
    loadingTechnical: "Technische data laden...",
    loadingScores: "Scores laden...",
    indicatorAssessment: (label, direction, signal) => `${label} ${direction.toLowerCase()} en geeft nu een ${signal.toLowerCase()} signaal.`,
    rsiAssessment: {
      high: "RSI ondersteunt het momentum en bevestigt een sterkere richting.",
      mid: "RSI is neutraal; het momentum is momenteel in balans.",
      low: "RSI wijst op zwak momentum en bevestigt nog geen vervolgbeweging.",
    },
    positiveMoveWeakScore: (value, score) => `De koers stijgt ${value}, maar de ingestelde scoregrenzen plaatsen deze beweging nog in de zwakke zone (${score}/100).`,
    aboveMa200: "Boven MA200",
    belowMa200: "Onder MA200",
    aboveMa50: "Boven MA50",
    belowMa50: "Onder MA50",
    indicatorLabels: {
      sp500: "S&P 500",
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
      scoreWithoutRows: (category, score) => `${category}: ${score}/100. De indicatordetails zijn in dit overzicht niet beschikbaar.`,
      measured: (category, score, names, extra) => `${category}: ${score}/100 uit ${names}${extra ? ` en ${extra} andere indicator(en)` : ""}.`,
    },
  };
}

const DEFAULT_INTELLIGENCE_WEIGHTS = {
  market: 1 / 3,
  macro: 1 / 3,
  technical: 1 / 3,
};

const ANALYSIS_TIMEFRAMES = ["day", "week", "month", "quarter"];
const ASSISTANT_PREFERENCES_CACHE_TTL_MS = 300_000;
let assistantPreferencesCache = {
  data: null,
  updatedAt: 0,
  inflight: null,
};

function getFreshAssistantPreferences() {
  if (!assistantPreferencesCache.updatedAt) return undefined;
  if (Date.now() - assistantPreferencesCache.updatedAt > ASSISTANT_PREFERENCES_CACHE_TTL_MS) {
    return undefined;
  }
  return assistantPreferencesCache.data;
}

async function loadAssistantPreferencesShared(forceFresh = false) {
  const cached = getFreshAssistantPreferences();
  if (!forceFresh && cached !== undefined) {
    return cached;
  }

  if (!forceFresh && assistantPreferencesCache.inflight) {
    return assistantPreferencesCache.inflight;
  }

  const inflight = getAssistantPreferences()
    .then((result) => {
      assistantPreferencesCache = {
        data: result ?? null,
        updatedAt: Date.now(),
        inflight: null,
      };
      return result ?? null;
    })
    .catch((error) => {
      assistantPreferencesCache = {
        data: assistantPreferencesCache.data,
        updatedAt: assistantPreferencesCache.updatedAt,
        inflight: null,
      };
      throw error;
    });

  assistantPreferencesCache = {
    data: assistantPreferencesCache.data,
    updatedAt: assistantPreferencesCache.updatedAt,
    inflight,
  };

  return inflight;
}

function mergeAssistantPreferences(patch) {
  const current = assistantPreferencesCache.data || {};
  const currentPreferences = current?.preferences || {};
  assistantPreferencesCache = {
    data: {
      ...current,
      preferences: {
        ...currentPreferences,
        ...patch,
      },
    },
    updatedAt: Date.now(),
    inflight: null,
  };
}

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

function averageVisibleSectionScore(rows) {
  const scores = (Array.isArray(rows) ? rows : [])
    .map((row) => normalizeScore(row?.score))
    .filter((score) => score !== null);

  if (!scores.length) return null;
  return Math.round(scores.reduce((sum, score) => sum + score, 0) / scores.length);
}

function oldestScoredSource(rows) {
  const scored = (Array.isArray(rows) ? rows : []).filter((row) => normalizeScore(row?.score) !== null);
  if (!scored.length) return null;
  const dates = scored.map((row) => new Date(row?.timestamp).getTime());
  if (dates.some((value) => !Number.isFinite(value) || value <= 0)) return null;
  return new Date(Math.min(...dates)).toISOString();
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
  if (value === null || value === undefined || value === "") return "—";
  const numericValue = Number(value);
  if (!Number.isFinite(numericValue)) return "—";
  return new Intl.NumberFormat(locale || "en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: numericValue >= 1000 ? 0 : 2,
  }).format(numericValue);
}

function formatQuotePrice(value, locale, quoteCurrency) {
  if (value === null || value === undefined || value === "") return "—";
  const numericValue = Number(value);
  const currency = String(quoteCurrency || "").toUpperCase();
  if (!Number.isFinite(numericValue) || !currency) return "—";
  if (["USD", "EUR", "GBP"].includes(currency)) {
    return new Intl.NumberFormat(locale || "en-US", {
      style: "currency", currency,
      maximumFractionDigits: numericValue >= 1000 ? 0 : 2,
    }).format(numericValue);
  }
  return `${new Intl.NumberFormat(locale || "en-US", {
    maximumFractionDigits: numericValue >= 1000 ? 0 : 2,
  }).format(numericValue)} ${currency}`;
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
    year: "numeric",
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

function localizeSemanticToken(value, ui = getUiCopy("en")) {
  const normalized = String(value || "").trim().toLowerCase();
  if (!normalized) return "";

  if (normalized === "insufficient data" || normalized === "onvoldoende data" || normalized === "unzureichende daten") {
    return ui.unavailable;
  }
  if (normalized.includes("above ma200") || normalized.includes("boven ma200") || normalized.includes("über ma200")) {
    return ui.aboveMa200;
  }
  if (normalized.includes("below ma200") || normalized.includes("onder ma200") || normalized.includes("unter ma200")) {
    return ui.belowMa200;
  }
  if (normalized.includes("above ma50") || normalized.includes("boven ma50") || normalized.includes("über ma50")) {
    return ui.aboveMa50;
  }
  if (normalized.includes("below ma50") || normalized.includes("onder ma50") || normalized.includes("unter ma50")) {
    return ui.belowMa50;
  }
  if (normalized.includes("improv") || normalized.includes("verbet") || normalized.includes("verbess")) {
    return ui.improving;
  }
  if (normalized.includes("weaken") || normalized.includes("verslecht") || normalized.includes("schwä")) {
    return ui.worsening;
  }
  if (normalized.includes("stable") || normalized.includes("stabiel") || normalized.includes("stabil")) {
    return ui.stable;
  }
  if (normalized === "neutral" || normalized === "neutraal") {
    return ui.neutral;
  }
  if (normalized === "positive" || normalized === "positief" || normalized === "positiv") {
    return ui.positive;
  }
  if (normalized === "negative" || normalized === "negatief" || normalized === "negativ") {
    return ui.negative;
  }
  if (normalized.includes("buy")) return ui.active;
  if (normalized.includes("sell")) return ui.weakened;
  return String(value || "").trim();
}

function localizeIndicatorDetail(value, ui = getUiCopy("en")) {
  const normalized = String(value || "").trim();
  if (!normalized) return "";

  const directMap = new Map([
    ["Onvoldoende data", ui.unavailable],
    ["Insufficient data", ui.unavailable],
    ["Unzureichende Daten", ui.unavailable],
    ["Geen interpretatie beschikbaar", ui.unavailable],
    ["No interpretation available", ui.unavailable],
    ["Keine Interpretation verfügbar", ui.unavailable],
    ["Geen scoreregel match", ui.unavailable],
    ["No matching scoring rule", ui.unavailable],
    ["Keine passende Scoring-Regel", ui.unavailable],
    ["Interpretatiefout", ui.unavailable],
    ["Interpretation error", ui.unavailable],
    ["Interpretationsfehler", ui.unavailable],
    ["Geen actie", ui.unavailable],
    ["No action", ui.unavailable],
    ["Keine Aktion", ui.unavailable],
    ["Empty", ui.unavailable],
    ["Leeg", ui.unavailable],
    ["Leer", ui.unavailable],
    ["Controleer logs", ui.finnContextUnavailable],
    ["Check logs", ui.finnContextUnavailable],
    ["Logs prüfen", ui.finnContextUnavailable],
    ["Geen interpretatie beschikbaar", ui.unavailable],
  ]);

  if (directMap.has(normalized)) {
    return directMap.get(normalized);
  }

  return normalized
    .replace("Geen interpretatie beschikbaar", ui.unavailable)
    .replace("Onvoldoende data", ui.unavailable)
    .replace("Empty", ui.unavailable);
}

function isGenericIndicatorExplanation(value) {
  const normalized = String(value || "").trim().toLowerCase();
  if (!normalized) return true;

  return [
    /^empty$/,
    /^leeg$/,
    /^leer$/,
    /geen interpretatie beschikbaar|no interpretation available|keine interpretation verfügbar/,
    /geen scoreregel match|no matching scoring rule|keine passende scoring-regel/,
    /interpretatiefout|interpretation error|interpretationsfehler/,
    /geen actie|no action|keine aktion/,
    /geen duidelijke edge|no clear edge|keine klare edge/,
    /zeer lage range|very low range|sehr niedriger bereich/,
    /lage range|low range|niedriger bereich/,
    /neutrale zone|neutral zone|neutrale zone/,
    /extreem|extreme range|extremer bereich/,
    /zeer zwakke marktcondities|very weak market conditions|sehr schwache marktbedingungen/,
    /lage kwaliteit liquiditeit\/momentum|low-quality liquidity\/momentum|niedrige liquiditäts\/momentum-qualität/,
    /zwakke condities|weak conditions|schwache bedingungen/,
    /sentiment\/conditie extreem zwak|sentiment\/condition extremely weak|sentiment\/zustand extrem schwach/,
    /sterk\/oververhit afhankelijk van indicator|strong or overheated depending on the indicator|stark\/überhitzt je nach indikator/,
    /^onvoldoende data$|^insufficient data$|^unzureichende daten$/,
    /^empty$/i,
  ].some((pattern) => pattern.test(normalized));
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

function formatIndicatorValue(name, value, locale, ui = getUiCopy(locale), quoteCurrency = null) {
  if (!hasUsableIndicatorValue(name, value)) return ui.unavailable;

  const label = String(name || "").toLowerCase();
  const raw = typeof value === "string" ? value.trim() : value;
  const rawString = typeof raw === "string" ? raw : "";
  const numericValue = parseIndicatorNumber(raw);

  if (typeof raw === "string" && /buy|sell|above|below|bull|bear|neutral|hoog|laag|stijg|daal|trend/i.test(rawString)) {
    return localizeSemanticToken(raw, ui);
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
    return quoteCurrency
      ? formatQuotePrice(numericValue, locale, quoteCurrency)
      : formatPrice(numericValue, locale);
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

  return localizeSemanticToken(rawString, ui) || ui.unavailable;
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

function explainIndicatorAssessment({
  name,
  label,
  score,
  numericValue,
  direction,
  ui,
}) {
  const normalizedName = String(name || "").trim().toLowerCase();
  const safeLabel = label || prettifyName(name, ui);
  const tone = score === null ? "missing" : score >= 70 ? "high" : score <= 35 ? "low" : "mid";

  if (normalizedName === "rsi" && ui.rsiAssessment?.[tone]) {
    return ui.rsiAssessment[tone];
  }

  const genericByTone = {
    high: `${safeLabel} supports the current setup and confirms the stronger side of the signal.`,
    mid: `${safeLabel} is mixed right now and does not create a strong edge on its own.`,
    low: `${safeLabel} weakens the current setup and still points to limited confirmation.`,
    missing: ui.unavailable,
  };

  const movingAverageLabel =
    normalizedName === "ma_200"
      ? numericValue >= 1
        ? ui.aboveMa200
        : ui.belowMa200
      : normalizedName === "ma_50"
        ? numericValue >= 1
          ? ui.aboveMa50
          : ui.belowMa50
        : null;

  const explanations = {
    change_24h: {
      high: `${safeLabel} shows strong short-term price expansion and supports current momentum.`,
      mid: `${safeLabel} is moving, but the short-term move still lacks decisive follow-through.`,
      low: `${safeLabel} stays weak and keeps short-term momentum under pressure.`,
    },
    volume: {
      high: `${safeLabel} confirms participation and improves confidence in the current move.`,
      mid: `${safeLabel} is present, but participation is not strong enough to confirm the move clearly.`,
      low: `${safeLabel} remains thin and does not confirm price action with enough participation.`,
    },
    market_volume: {
      high: `${safeLabel} confirms participation and improves confidence in the current move.`,
      mid: `${safeLabel} is present, but participation is not strong enough to confirm the move clearly.`,
      low: `${safeLabel} remains thin and does not confirm price action with enough participation.`,
    },
    btc_dominance: {
      high: `${safeLabel} strongly supports the current market regime for this asset setup.`,
      mid: `${safeLabel} is balanced and leaves the macro regime mixed.`,
      low: `${safeLabel} currently works against the preferred market regime for this setup.`,
    },
    fear_greed_index: {
      high: `${safeLabel} sits in a supportive zone for the current setup according to your scoring rules.`,
      mid: `${safeLabel} is neutral and does not create a strong sentiment edge yet.`,
      low: `${safeLabel} signals fragile sentiment and keeps risk appetite under pressure.`,
    },
    inflation_rate: {
      high: `${safeLabel} is currently supportive for risk assets under your macro thresholds.`,
      mid: `${safeLabel} is mixed and does not yet give a clear macro tailwind.`,
      low: `${safeLabel} remains a macro headwind and keeps risk conditions tighter.`,
    },
    oil_price: {
      high: `${safeLabel} is in a zone that supports your current macro interpretation.`,
      mid: `${safeLabel} is mixed and does not materially shift the macro backdrop yet.`,
      low: `${safeLabel} adds macro stress and weighs on the broader risk picture.`,
    },
    us10y: {
      high: `${safeLabel} is currently supportive for your macro regime assessment.`,
      mid: `${safeLabel} is stable, but rates are not giving a strong directional edge yet.`,
      low: `${safeLabel} remains a rates headwind and limits macro support.`,
    },
    us2y: {
      high: `${safeLabel} is currently supportive for your macro regime assessment.`,
      mid: `${safeLabel} is stable, but rates are not giving a strong directional edge yet.`,
      low: `${safeLabel} remains a rates headwind and limits macro support.`,
    },
    vix: {
      high: `${safeLabel} points to calmer volatility conditions and supports the current setup.`,
      mid: `${safeLabel} is neutral and keeps volatility context mixed.`,
      low: `${safeLabel} signals elevated stress and weakens the current risk setup.`,
    },
    ma_200: {
      high: `${safeLabel} is ${movingAverageLabel?.toLowerCase() || direction.toLowerCase()} and confirms the broader trend structure.`,
      mid: `${safeLabel} is close to balance and gives only limited trend confirmation.`,
      low: `${safeLabel} is ${movingAverageLabel?.toLowerCase() || direction.toLowerCase()} and weakens the broader trend structure.`,
    },
    ma_50: {
      high: `${safeLabel} is ${movingAverageLabel?.toLowerCase() || direction.toLowerCase()} and supports the active trend.`,
      mid: `${safeLabel} is balanced and does not yet confirm a strong active trend.`,
      low: `${safeLabel} is ${movingAverageLabel?.toLowerCase() || direction.toLowerCase()} and keeps the active trend weak.`,
    },
    rsi: {
      high: `${safeLabel} supports momentum and confirms stronger directional control.`,
      mid: `${safeLabel} is neutral and momentum remains balanced.`,
      low: `${safeLabel} keeps momentum weak and does not confirm follow-through.`,
    },
    adx: {
      high: `${safeLabel} confirms a stronger trend environment and better directional persistence.`,
      mid: `${safeLabel} suggests a tradable move, but trend strength is still moderate.`,
      low: `${safeLabel} indicates weak trend strength and limited persistence.`,
    },
    atr_pct: {
      high: `${safeLabel} shows expanding range conditions that support an active move.`,
      mid: `${safeLabel} is manageable, but volatility expansion is not decisive yet.`,
      low: `${safeLabel} remains compressed and limits range expansion.`,
    },
    ema_20_gap_pct: {
      high: `${safeLabel} supports short-term trend alignment and clean follow-through.`,
      mid: `${safeLabel} is mixed and does not yet show a clear short-term edge.`,
      low: `${safeLabel} weakens short-term trend alignment and follow-through.`,
    },
    ema_50_gap_pct: {
      high: `${safeLabel} supports medium-term trend alignment and healthy structure.`,
      mid: `${safeLabel} is mixed and medium-term trend alignment remains incomplete.`,
      low: `${safeLabel} weakens medium-term trend alignment and structure.`,
    },
    macd_hist_pct: {
      high: `${safeLabel} confirms improving momentum and supports continuation.`,
      mid: `${safeLabel} is mixed and momentum confirmation remains limited.`,
      low: `${safeLabel} weakens momentum and does not confirm continuation.`,
    },
  };

  const specific =
    explanations[normalizedName]?.[tone] ||
    (normalizedName.includes("change") ? explanations.change_24h?.[tone] : null) ||
    (normalizedName.includes("volume") ? explanations.volume?.[tone] : null) ||
    (normalizedName.includes("fear") ? explanations.fear_greed_index?.[tone] : null) ||
    (normalizedName.includes("dominance") ? explanations.btc_dominance?.[tone] : null) ||
    (normalizedName.includes("inflation") ? explanations.inflation_rate?.[tone] : null) ||
    (normalizedName.includes("oil") ? explanations.oil_price?.[tone] : null) ||
    (normalizedName.includes("vix") ? explanations.vix?.[tone] : null) ||
    (normalizedName.includes("rsi") ? explanations.rsi?.[tone] : null) ||
    (normalizedName.includes("adx") ? explanations.adx?.[tone] : null) ||
    (normalizedName.includes("atr") ? explanations.atr_pct?.[tone] : null) ||
    (normalizedName.includes("ema") ? explanations.ema_20_gap_pct?.[tone] : null) ||
    (normalizedName.includes("macd") ? explanations.macd_hist_pct?.[tone] : null);

  return specific || genericByTone[tone] || ui.indicatorAssessment(safeLabel, direction, scoreTone(score, ui).label);
}

function buildRows(items, locale, ui, currentEvidence = null, categoryScore = null, quoteCurrency = null) {
  const source = Array.isArray(items) ? items : [];
  const evidenceWeight = currentEvidence && normalizeScore(categoryScore) !== null
    ? Object.values(currentEvidence).reduce((sum, entry) =>
        sum + (["custom", "system_template"].includes(entry?.rule_origin) &&
          normalizeScore(entry?.score) !== null ? Number(entry?.weight || 1) : 0), 0)
    : 0;

  return source.map((item, index) => {
    const name = item?.name || item?.indicator || `indicator_${index}`;
    const label = prettifyName(name, ui);
    const rawValue = item?.value ?? item?.waarde;
    const hasValue = hasUsableIndicatorValue(name, rawValue);
    const evidence = currentEvidence === null ? item : validatedDayEvidence(categoryScore, currentEvidence, name);
    // The server verifies that the daily evidence still matches this exact
    // reading. Do not resurrect a saved score when that check rejected it.
    const score = hasValue && (currentEvidence === null || evidence)
      ? normalizeScore(item?.score)
      : null;
    const verifiedContribution = score !== null && evidenceWeight > 0 && evidence
      ? {
          status: "available",
          basis: "verified_indicator_weight",
          weight: Number(evidence.weight || 1) / evidenceWeight,
          weighted_points: score * Number(evidence.weight || 1) / evidenceWeight,
        }
      : null;
    const ruleOrigin = score === null ? null : evidence?.rule_origin || item?.rule_origin || null;
    const tone = scoreTone(score, ui);
    const direction = score !== null ? toDirectionLabel(item, score, ui) : ui.unavailable;
    const value = formatIndicatorValue(name, rawValue, locale, ui, quoteCurrency);
    const numericValue = parseIndicatorNumber(rawValue);
    const scoreConflict =
      hasValue &&
      String(name).toLowerCase().includes("change") &&
      Number.isFinite(numericValue) &&
      numericValue > 0 &&
      score !== null &&
      score <= 35;
    const rawDetail = String(item?.interpretation || item?.uitleg || item?.action || "").trim();
    const localizedDetail = trimSentence(localizeIndicatorDetail(rawDetail, ui), "");
    const shouldUseBackendDetail = score !== null &&
      localizedDetail &&
      localizedDetail !== ui.unavailable &&
      !isGenericIndicatorExplanation(rawDetail) &&
      !isGenericIndicatorExplanation(localizedDetail) &&
      (String(name || "").trim().toLowerCase() === "sp500" ||
        !ui.indicatorLabels?.[String(name || "").trim().toLowerCase()]);
    const unavailableReason = item?.score_unavailable_reason;
    const historyCoverage = item?.score_history_coverage;
    const generatedDetail = score !== null
      ? explainIndicatorAssessment({
          name,
          label,
          score,
          numericValue,
          direction,
          ui,
        })
      : unavailableReason === "insufficient_dated_history" && historyCoverage
        ? ui.historyPending(historyCoverage.observed_days, historyCoverage.required_days)
        : unavailableReason === "stale_source"
          ? ui.indicatorSourceStale
          : unavailableReason === "missing_rule"
            ? ui.missingScoreRule
          : unavailableReason === "score_pending"
            ? ui.scorePending
      : !hasValue && item?.data_status === "pending_refresh"
        ? ui.pendingSource
        : ui.unavailable;
    const normalizedPosition = Number(evidence?.normalized_value);
    const methodDetail = ruleOrigin === "system_template" && Number.isFinite(normalizedPosition)
      ? String(name).toLowerCase() === "price"
        ? ui.priceRangeMethod(Math.round(normalizedPosition))
        : String(name).toLowerCase() === "dxy"
          ? ui.dxyRangeMethod(Math.round(normalizedPosition))
          : String(name).toLowerCase() === "volume"
            ? ui.volumeMethod(Math.round(normalizedPosition))
            : String(name).toLowerCase() === "change_24h"
              ? ui.change24hMethod(Math.round(normalizedPosition))
          : null
      : null;
    const detail = scoreConflict
      ? ui.positiveMoveWeakScore(value, Math.round(score))
      : methodDetail
        ? methodDetail
      : shouldUseBackendDetail
        ? String(name).trim().toLowerCase() === "sp500"
          ? locale?.startsWith("nl")
            ? localizedDetail
                .replace(/^S&P 500 ligt boven het midden van het eigen recente 90-daagse bereik[.;].*$/i, "De S&P 500 staat boven het midden van zijn koersbereik over de afgelopen 90 dagen.")
                .replace(/;\s*dit is macrocontext[^.]*\.?$/i, ".")
            : localizedDetail
          : localizedDetail
        : generatedDetail;

    return {
      id: `${name}-${index}`,
      name,
      label,
      value,
      direction,
      score,
      signalTone: tone,
      scoreLabel: score === null ? ui.unavailable : `${Math.round(score)}/100`,
      detail,
      timestamp: evidence?.source_observed_at || item?.source_observed_at || null,
      ruleOrigin,
      normalizedPosition: score === null || !Number.isFinite(normalizedPosition) ? null : Math.round(normalizedPosition),
      raw: verifiedContribution ? { ...item, score_contribution: verifiedContribution } : item,
    };
  });
}

function buildSectionInsight(sectionId, sectionScore, ui, sourceStatus = null, rows = [], notConfigured = false) {
  const score = normalizeScore(sectionScore);
  const copy = ui.sectionInsights;

  if (score === null) {
    if (notConfigured) return ui[`${sectionId}Empty`];
    if (sourceStatus === "score_rebuild_pending") return ui.scoreRebuilding;
    if (rows.some((row) => row?.raw?.configured || row?.raw?.value != null)) return ui.scoreIncomplete;
    return copy.missing;
  }

  const scored = rows.filter((row) => normalizeScore(row?.score) !== null && row?.label);
  if (!scored.length) return copy.scoreWithoutRows(ui[sectionId], Math.round(score));
  return copy.measured(
    ui[sectionId], Math.round(score),
    scored.slice(0, 3).map((row) => row.label).join(", "),
    Math.max(0, scored.length - 3),
  );
}

function ScoreOverview({ assetSymbol, market, macro, technical, combined, sections, weights, loading, onSaveWeights, onOpenPlan, onSelectSetup, selectedSetupId, setupMatches, setupMatchError, ui, locale, conditionOptions, isDailyBenchmark }) {
  const [isEditing, setIsEditing] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [localWeights, setLocalWeights] = useState(() => normalizeWeights(weights));

  useEffect(() => {
    if (!isEditing) {
      setLocalWeights((current) => {
        const next = normalizeWeights(weights);
        return Object.keys(next).every((key) => current[key] === next[key]) ? current : next;
      });
    }
  }, [isEditing, weights]);

  const currentScore = normalizeScore(combined?.score);
  const eligibleMatches = isDailyBenchmark && Array.isArray(setupMatches) ? setupMatches.filter((match) =>
    String(match?.symbol || "").toUpperCase() === assetSymbol
  ) : [];
  const selectedMatch = selectedBenchmarkSetupMatch(eligibleMatches, selectedSetupId);
  const view = benchmarkSetupView(currentScore, selectedMatch);
  const scaleBands = benchmarkScaleBands();
  const setupZoneLabel = view.preset
    ? conditionOptions?.[view.preset.id]?.title || ui.benchmarkCustom(view.minimum, view.maximum)
    : view.zone ? ui.benchmarkCustom(view.minimum, view.maximum) : null;
  const statusText = setupMatchError ? ui.benchmarkReadError : setupMatches === null ? ui.benchmarkUpdating : ({
    no_setup: ui.benchmarkNoSetup,
    no_condition: ui.benchmarkNoCondition,
    insufficient_data: ui.benchmarkMissing,
    updating: ui.benchmarkUpdating,
    matches: ui.benchmarkMatches,
    outside_conditions: ui.benchmarkOutside,
  }[view.status]);
  const scoreSections = sections.filter((section) => section.score !== null);
  const sectionSource = (id) => oldestScoredSource(sections.find((section) => section.id === id)?.rows);
  const combinedSource = scoreSections.length && scoreSections.every((section) => sectionSource(section.id))
    ? new Date(Math.min(...scoreSections.map((section) => new Date(sectionSource(section.id)).getTime()))).toISOString()
    : null;

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
  const currentWeights = normalizeWeights(weights);

  return (
    <section id="benchmark-uitleg" className="scroll-mt-6 rounded-[24px] border border-slate-200/80 bg-white shadow-[0_18px_40px_-36px_rgba(15,23,42,0.26)]">
      <div className="flex items-center justify-between gap-3 border-b border-slate-100 px-4 py-3">
        <div>
          <h2 className="text-[19px] font-black tracking-tight text-slate-950">
            {isDailyBenchmark ? ui.benchmarkAssetTitle(assetSymbol) : ui.periodCompositionTitle}
          </h2>
          <p className="mt-0.5 text-xs text-slate-500">{ui.benchmarkBasis}</p>
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
      <div className="px-4 py-4">
        <div className="flex flex-wrap items-end gap-x-4 gap-y-1">
          <strong className="text-[42px] font-black leading-none tracking-tight text-slate-950">
            {loading && currentScore === null ? "…" : formatBenchmarkScore(currentScore, locale)}
          </strong>
          <div className="pb-0.5">
            <div className="text-[16px] font-bold text-slate-950">
              {view.currentBand ? conditionOptions?.[view.currentBand.id]?.title || ui.benchmarkCustom(view.currentBand.min, view.currentBand.max) : ui.unavailable}
            </div>
            <div className="text-[11px] text-slate-500">
              {currentScore !== null ? (combinedSource ? `${ui.scoreSourceDate}: ${formatTimestamp(combinedSource, locale)}` : ui.scoreSourceUnknown) : ui.benchmarkMissing}
            </div>
          </div>
        </div>

        <div className="mt-5 min-w-0 pb-1">
          <div className="w-full min-w-0">
            <div className="relative h-12" role="img" aria-label={`${ui.benchmarkScore}: ${currentScore === null ? ui.unavailable : `${formatBenchmarkScore(currentScore, locale)} · ${conditionOptions?.[view.currentBand?.id]?.title || ui.benchmarkCustom(view.currentBand.min, view.currentBand.max)}`}`}>
              {currentScore !== null ? (
                <div className={`absolute top-0 z-20 rounded-full bg-slate-900 px-2 py-1 text-[10px] font-bold text-white ${currentScore <= 10 ? "" : currentScore >= 90 ? "-translate-x-full" : "-translate-x-1/2"}`} style={{ left: `${currentScore}%` }}>
                  {ui.benchmarkNow} · {formatBenchmarkScore(currentScore, locale)}
                </div>
              ) : null}
              <div className="absolute inset-x-0 bottom-0 flex h-7 gap-0.5 overflow-hidden rounded-lg">
                {scaleBands.map((band, index) => (
                  <div key={band.id} style={{ width: `${band.width}%` }} className={[
                    "bg-rose-200", "bg-orange-200", "bg-amber-100", "bg-teal-100", "bg-emerald-200",
                  ][index]} />
                ))}
              </div>
              {view.zone ? (
                <div className="absolute bottom-0 z-10 h-7 rounded-lg border-[3px] border-blue-600" style={{ left: `${view.zone.start}%`, width: `${Math.max(1, view.zone.end - view.zone.start)}%` }} />
              ) : null}
              {currentScore !== null ? (
                <div className="absolute bottom-0 z-30 h-7 w-0.5 -translate-x-1/2 bg-slate-950" style={{ left: `${currentScore}%` }} />
              ) : null}
            </div>
            <div className="mt-2 flex gap-0.5 text-center text-[8px] font-semibold leading-tight text-slate-600 sm:text-[10px]">
              {scaleBands.map((band) => (
                <div key={band.id} style={{ width: `${band.width}%` }} className="min-w-0 break-words px-0.5">
                  <span className="block font-bold text-slate-400">{band.min}–{band.max}</span>
                  {conditionOptions?.[band.id]?.title || ui.benchmarkCustom(band.min, band.max)}
                </div>
              ))}
            </div>
          </div>
        </div>
        {isDailyBenchmark && currentScore !== null ? <p className="mt-1 text-[10px] text-slate-500">{ui.benchmarkRoundedRule}</p> : null}

        {isDailyBenchmark ? (
          <div className="mt-4 rounded-xl border border-blue-100 bg-blue-50/60 px-3.5 py-3">
            {eligibleMatches.length > 1 ? (
              <label className="mb-2 flex flex-wrap items-center gap-2 text-xs font-semibold text-slate-700">
                {ui.benchmarkSetupLabel}
                <select value={String(selectedMatch?.setup_id || "")} onChange={(event) => onSelectSetup(event.target.value)} className="max-w-full rounded-lg border border-slate-200 bg-white px-2 py-1.5 text-xs text-slate-900">
                  {eligibleMatches.map((match) => <option key={match.setup_id} value={match.setup_id}>{match.name}</option>)}
                </select>
              </label>
            ) : selectedMatch ? (
              <button type="button" onClick={onOpenPlan} className="text-left text-xs font-bold text-blue-700 hover:underline">{selectedMatch.name}</button>
            ) : null}
            {setupZoneLabel ? <p className="text-xs font-semibold text-slate-900">{ui.benchmarkSetupZone}: {setupZoneLabel}</p> : null}
            <p className="mt-1 text-xs leading-relaxed text-slate-600">{statusText}</p>
          </div>
        ) : null}

        <div className="mt-4 grid gap-2 border-t border-slate-100 pt-3 sm:grid-cols-3">
          {weightItems.map((item) => (
            <div key={item.id} className="text-xs text-slate-600">
              <span className="font-semibold">{item.label}</span>{" "}
              <strong className="text-slate-950">{formatScore(item.score)}</strong>{" · "}
              {Math.round((currentWeights[item.id] || 0) * 100)}%
            </div>
          ))}
        </div>
        <p className="mt-2 text-[11px] text-slate-500">{ui.scoreSourceLimit}</p>
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

function AnalysisChartSection({ interval, onIntervalChange, tradingViewSymbol, studies, isOpen, onToggle, ui }) {
  // The TradingView embed accepts multiple studies when every entry uses the
  // same object shape. Mixing string IDs with configured studies silently
  // drops later entries (for example RSI after MA 200).
  const indicators = studies.map(({ id, inputs }) => inputs ? { id, inputs } : { id });
  const chartHeight = Math.min(760, 420 + indicators.length * 75);

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
          {tradingViewSymbol ? (
            <TradingViewSmartChart
              key={tradingViewSymbol}
              symbol={tradingViewSymbol}
              interval={interval}
              indicators={indicators}
              studyFallbackLabel={ui.chartStudyFallback}
              focusedBotId={null}
              setFocusedBotId={() => {}}
              height={chartHeight}
              onIntervalChange={onIntervalChange}
            />
          ) : <p className="py-12 text-center text-sm text-slate-500">{ui.chartLoading}</p>}
          {tradingViewSymbol && studies.length ? (
            <p className="mt-2 px-1 text-xs text-slate-500">
              {ui.chartIndicators}: {studies.map((study) => study.label).join(", ")}. {ui.chartIndicatorNote}
            </p>
          ) : null}
        </div>
      ) : null}
    </section>
  );
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
  conditionOptions,
  isDailyBenchmark,
  locale,
  onSelectAsset,
  ui,
}) {
  const changeValue = Number(change24h);
  const changeClass = Number.isFinite(changeValue)
    ? changeValue >= 0
      ? "text-emerald-600"
      : "text-red-600"
    : "text-slate-400";
  const condition = marketConditionForScore(combinedSummary.score);
  const situation = condition ? conditionOptions?.[condition.id]?.title : ui.unavailable;

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

      <div className="mt-2.5 grid gap-3 lg:grid-cols-[minmax(0,1fr)_minmax(350px,0.9fr)] lg:items-center">
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

        <div className="rounded-2xl border border-blue-100 bg-blue-50/60 px-4 py-3">
          <div className="text-[10px] font-black uppercase tracking-[0.16em] text-blue-600">{ui.benchmarkTitle}</div>
          <div className="mt-1 flex flex-wrap items-baseline gap-x-3 gap-y-1">
            <strong className="text-lg font-black text-slate-950">{situation}</strong>
            <span className="text-xs font-bold text-slate-600">
              {isDailyBenchmark ? ui.benchmarkScore : ui.selectedPeriodScore}: {combinedSummary.score === null ? "—" : `${formatBenchmarkScore(combinedSummary.score, locale)}/100`}
            </span>
          </div>
          <p className="mt-1 text-[11px] leading-relaxed text-slate-600">{ui.benchmarkExplanation}</p>
          <a href="#benchmark-uitleg" className="mt-1.5 inline-flex items-center gap-1 text-[11px] font-bold text-blue-700 hover:underline">
            {ui.benchmarkDetails} <ArrowRight size={12} aria-hidden="true" />
          </a>
        </div>
      </div>
    </section>
  );
}

function AssetList({
  rows,
  activeSymbol,
  activeGroup,
  onSelect,
  onRemove,
  onGroupChange,
  onAddAsset,
  conditionOptions,
  ui,
}) {
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
        <div className="grid grid-cols-[minmax(0,1.5fr)_120px_100px_minmax(150px,1fr)_48px] gap-3 border-b border-slate-100 px-4 py-2.5 text-[9px] font-black uppercase tracking-[0.2em] text-slate-400">
          <div>Asset</div>
          <div className="text-right">{ui.latest}</div>
          <div className="text-right">24u</div>
          <div className="text-right">{ui.marketSituation}</div>
          <div className="text-right">{ui.watchlistActions}</div>
        </div>
        <div>
          {rows.length ? rows.map((row) => {
            const active = row.symbol === activeSymbol;
            const condition = marketConditionForScore(row.rawScore);
            const situation = condition ? conditionOptions?.[condition.id]?.title : ui.unavailable;
            return (
              <div
                key={row.symbol}
                role="button"
                tabIndex={0}
                onClick={() => onSelect(row.symbol)}
                onKeyDown={(event) => {
                  if (event.key === "Enter" || event.key === " ") {
                    event.preventDefault();
                    onSelect(row.symbol);
                  }
                }}
                className={`grid w-full cursor-pointer grid-cols-[minmax(0,1.5fr)_120px_100px_minmax(150px,1fr)_48px] items-center gap-3 border-b border-slate-100 px-4 py-2.5 text-left transition last:border-b-0 ${
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
                    <span className="text-[15px] font-black text-slate-950">
                      {row.assetClass === "crypto" && row.quoteCurrency
                        ? `${row.symbol}/${row.quoteCurrency}` : row.symbol}
                    </span>
                  </div>
                  <div className="mt-0.5 truncate text-[13px] font-medium text-slate-500">
                    {row.displayName || ASSET_NAMES[row.symbol] || "Asset context"}
                  </div>
                </div>
                <div className="text-right text-[15px] font-black text-slate-950">{row.lastPrice}</div>
                <div className={`text-right text-[15px] font-black ${row.changeTone}`}>
                  {row.change24h}
                </div>
                <div className="text-right">
                  <div className="text-[12px] font-black text-slate-900">{situation}</div>
                  <div className="text-[10px] font-semibold text-slate-500">{ui.benchmarkScore}: {condition ? `${row.score}/100` : "—"}</div>
                </div>
                <div className="flex justify-end">
                  <button
                    type="button"
                    aria-label={`${ui.watchlistRemoveLabel}: ${row.symbol}`}
                    title={ui.watchlistRemoveLabel}
                    onClick={(event) => {
                      event.stopPropagation();
                      onRemove(row);
                    }}
                    className="inline-flex h-8 w-8 items-center justify-center rounded-full border border-slate-200 bg-white text-slate-400 transition hover:border-red-200 hover:bg-red-50 hover:text-red-600"
                  >
                    <X size={14} />
                  </button>
                </div>
              </div>
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
  onEdit,
  onRemove,
  period,
  locale,
  ui,
}) {
  const contribution = row.raw?.score_contribution;
  const weightText = row.score !== null && contribution?.status === "available"
    ? `${Math.round(Number(contribution.weight || 0) * 100)}%`
    : ui.unavailable;
  const contributionText = row.score !== null && contribution?.status === "available"
    ? `${new Intl.NumberFormat(locale, { maximumFractionDigits: 1 }).format(Number(contribution.weighted_points || 0))} ${ui.scorePoints} · ${weightText}`
    : ui.unavailable;
  const historyCoverage = row.raw?.score_history_coverage;
  const freshness = row.raw?.freshness;
  const freshnessText = {
    unavailable: ui.unavailable,
    stale: ui.staleData,
    current: ui.currentData,
  }[indicatorSourceFreshness(freshness)];

  return (
    <div className="border-t border-slate-100">
      <button
        type="button"
        onClick={onToggle}
        className="w-full px-4 py-3 text-left transition hover:bg-slate-50/80"
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
              <div className="text-[16px] font-bold leading-tight text-slate-950">{row.label}</div>
            </div>
          </div>

          <div className="lg:text-right">
            <div className="text-[10px] font-black uppercase tracking-[0.22em] text-slate-400 lg:hidden">
              {ui.value}
            </div>
            <div className="text-[16px] font-bold text-slate-950">{row.value}</div>
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
              <span className="inline-flex items-center rounded-lg border border-slate-300 px-3 py-1.5 text-[12px] font-semibold text-slate-900">
                {ui.scoreTitle} {row.scoreLabel}
              </span>
            </div>
          </div>
        </div>
        <p className="mt-3 text-[13px] leading-5 text-slate-700">{row.detail}</p>
      </button>

      {expanded ? (
        <div className="border-t border-slate-100 px-4 py-4">
          {onEdit ? (
            <div className="mb-4 flex flex-wrap gap-2">
              <button type="button" onClick={onEdit} className="rounded-lg border border-slate-200 px-3 py-1.5 text-xs font-semibold text-blue-700 hover:bg-blue-50">
                {ui.editIndicator}
              </button>
              <button type="button" onClick={onRemove} className="rounded-lg border border-slate-200 px-3 py-1.5 text-xs font-semibold text-red-700 hover:bg-red-50">
                {ui.removeIndicator}
              </button>
            </div>
          ) : null}
          <h3 className="text-[14px] font-bold text-slate-900">{ui.scoreCalculationTitle}</h3>
          <div className="mt-3 overflow-hidden rounded-xl border border-slate-200 bg-slate-50/70">
            <div className="grid md:grid-cols-2">
              <div className="p-4 md:border-r md:border-slate-200">
                <h4 className="text-[13px] font-bold text-slate-900">{ui.calculation}</h4>
                <dl className="mt-2 text-[12px]">
                  {[
                    [ui.scaledReading, row.normalizedPosition !== null ? `${row.normalizedPosition}/100` : ui.unavailable],
                    [ui.scoringRule, row.ruleOrigin === "custom" ? ui.personalScoringRule : row.ruleOrigin ? ui.systemScoringRule : ui.unavailable],
                    [ui.groupContribution, contributionText],
                  ].map(([label, value]) => (
                    <div key={label} className="flex justify-between gap-3 border-b border-slate-200 py-2 last:border-0">
                      <dt className="text-slate-500">{label}</dt>
                      <dd className="text-right font-semibold text-slate-800">{value}</dd>
                    </div>
                  ))}
                </dl>
              </div>
              <div className="border-t border-slate-200 p-4 md:border-t-0">
                <h4 className="text-[13px] font-bold text-slate-900">{ui.usedData}</h4>
                <dl className="mt-2 text-[12px]">
                  {[
                    [ui.periodLabel, ui[row.raw?.period || period] || row.raw?.period || period],
                    [ui.sampleSize, row.raw?.sample_size ?? ui.unavailable],
                    ...(historyCoverage ? [[ui.scoreHistory, ui.coverageValue(historyCoverage.observed_days, historyCoverage.required_days, historyCoverage.window_days)]] : []),
                  ].map(([label, value]) => (
                    <div key={label} className="flex justify-between gap-3 border-b border-slate-200 py-2 last:border-0">
                      <dt className="text-slate-500">{label}</dt>
                      <dd className="text-right font-semibold text-slate-800">{value}</dd>
                    </div>
                  ))}
                </dl>
              </div>
            </div>
            <div className="flex flex-wrap justify-between gap-2 border-t border-slate-200 px-4 py-2 text-[11px] text-slate-500">
              <span>{ui.dataSource}: {String(row.raw?.source || "—").replaceAll("_", " ")} · {ui.latestSignal}: {row.timestamp ? formatTimestamp(row.timestamp, locale) : ui.missingSourceMoment}</span>
              <span>{ui.freshness}: {freshnessText}</span>
            </div>
          </div>

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
  onEditIndicator,
  onRemoveIndicator,
  action,
  toolbar,
  emptyState,
  emptyAction,
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
                onEdit={onEditIndicator ? () => onEditIndicator(id, row) : null}
                onRemove={onRemoveIndicator ? () => onRemoveIndicator(id, row) : null}
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
  const { user, sessionChecked } = useAuth();
  const { selectedAsset, setSelectedAsset } = useAsset();
  const { symbols: persistedWatchlistSymbols = [], refresh: refreshPersistedWatchlist } = useWatchlist();
  const { locale, t } = useTranslation();
  const { openConfirm, showSnackbar } = useModal();
  const ui = useMemo(() => getUiCopy(locale), [locale]);
  const symbolFromUrl = searchParams.get("symbol")?.toUpperCase();
  const activeSymbol = symbolFromUrl || selectedAsset || "BTC";
  const setupSelectionKey = sessionChecked ? benchmarkSetupSessionKey(user?.id, activeSymbol) : null;
  const quoteSelectionKey = sessionChecked ? tradingQuoteSessionKey(user?.id, activeSymbol) : null;
  const urlSetupId = searchParams.get("benchmarkSetup");
  const [rememberedSetup, setRememberedSetup] = useState({ key: null, id: null });
  const [rememberedQuote, setRememberedQuote] = useState({ key: null, quote: null });
  const [tradingMarkets, setTradingMarkets] = useState({ symbol: null, markets: [] });
  useEffect(() => {
    if (!setupSelectionKey) {
      setRememberedSetup({ key: null, id: null });
      return;
    }
    const id = urlSetupId || window.sessionStorage.getItem(setupSelectionKey);
    if (urlSetupId) window.sessionStorage.setItem(setupSelectionKey, urlSetupId);
    setRememberedSetup({ key: setupSelectionKey, id });
  }, [setupSelectionKey, urlSetupId]);
  useEffect(() => {
    if (!quoteSelectionKey) {
      setRememberedQuote({ key: null, quote: null });
      return;
    }
    setRememberedQuote({ key: quoteSelectionKey, quote: window.sessionStorage.getItem(quoteSelectionKey) });
  }, [quoteSelectionKey]);
  useEffect(() => {
    if (!sessionChecked || !user?.id) return;
    let canceled = false;
    setTradingMarkets({ symbol: null, markets: [] });
    fetchTradingMarkets(activeSymbol).then((result) => {
      if (canceled) return;
      setTradingMarkets({ symbol: activeSymbol, markets: Array.isArray(result) ? result : (Array.isArray(result?.markets) ? result.markets : []) });
    }).catch(() => {
      if (!canceled) setTradingMarkets({ symbol: activeSymbol, markets: [] });
    });
    return () => { canceled = true; };
  }, [activeSymbol, sessionChecked, user?.id]);
  const [marketTimeframe, setMarketTimeframe] = useState("day");
  const [macroTimeframe, setMacroTimeframe] = useState("day");
  const [technicalTimeframe, setTechnicalTimeframe] = useState("day");
  const [activeAssetGroup, setActiveAssetGroup] = useState("crypto");
  const [expandedRowKey, setExpandedRowKey] = useState(null);
  const [technicalConfigModal, setTechnicalConfigModal] = useState(null);
  const [pairConfigModal, setPairConfigModal] = useState(null);
  const [copySources, setCopySources] = useState([]);
  const [copySourceId, setCopySourceId] = useState("");
  const [copyPreview, setCopyPreview] = useState(null);
  const [copyBusy, setCopyBusy] = useState(false);
  const [copyOpen, setCopyOpen] = useState(false);
  const [watchlistRows, setWatchlistRows] = useState([]);
  const [removedWatchlistSymbols, setRemovedWatchlistSymbols] = useState([]);
  const [showChart, setShowChart] = useState(true);
  const [analysisChartInterval, setAnalysisChartInterval] = useState(DEFAULT_TRADINGVIEW_INTERVAL);
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
  const watchlistSymbols = useMemo(
    () => {
      const normalizedSymbols = persistedWatchlistSymbols
        .map((symbol) => String(symbol || "").trim().toUpperCase())
        .filter(Boolean);

      if (!normalizedSymbols.length) return [];
      return Array.from(new Set([activeSymbol, ...normalizedSymbols]));
    },
    [activeSymbol, persistedWatchlistSymbols]
  );

  const [setupMatches, setSetupMatches] = useState(null);
  const [setupMatchError, setSetupMatchError] = useState(false);
  const [setupMatchLoading, setSetupMatchLoading] = useState(true);
  const setupMatchesSymbolRef = useRef(activeSymbol);
  const selectedSetupId = urlSetupId || (rememberedSetup.key === setupSelectionKey ? rememberedSetup.id : null);
  const savedPairMatches = useMemo(() => (setupMatches || []).filter(
    (match) => match?.market_id && match?.quote_currency &&
      String(match.symbol || "").toUpperCase() === activeSymbol
  ), [activeSymbol, setupMatches]);
  const availableQuotes = useMemo(() => availableTradingQuotes(
    savedPairMatches,
    tradingMarkets.symbol === activeSymbol ? tradingMarkets.markets : [],
  ), [activeSymbol, savedPairMatches, tradingMarkets]);
  const explicitQuote = String(searchParams.get("quote") || "").toUpperCase();
  const selectedPairMatch = savedPairMatches.find((match) =>
    String(match.setup_id) === String(selectedSetupId || ""));
  const activeQuoteCurrency = rememberedQuote.key === quoteSelectionKey
    ? resolveTradingQuote({
      explicitQuote,
      setupQuote: selectedPairMatch?.quote_currency,
      rememberedQuote: rememberedQuote.quote,
      availableQuotes,
    }) : null;
  useEffect(() => {
    if (!quoteSelectionKey || !availableQuotes.includes(explicitQuote)) return;
    window.sessionStorage.setItem(quoteSelectionKey, explicitQuote);
    setRememberedQuote({ key: quoteSelectionKey, quote: explicitQuote });
  }, [availableQuotes, explicitQuote, quoteSelectionKey]);

  const {
    workspace: loadedWorkspace,
    watchlist: watchlistData,
    loading: workspaceLoading,
    watchlistLoading,
    isFallbackWorkspace,
    reloadWorkspace,
    reloadWatchlist,
  } = useAssetWorkspaceData(activeSymbol, periods, watchlistSymbols, activeQuoteCurrency);
  // Resolve saved pair choices before showing any price or score. Otherwise
  // the initial base-asset response can briefly masquerade as a pair plan.
  const workspace = (setupMatches !== null && tradingMarkets.symbol === activeSymbol &&
    (!quoteSelectionKey || rememberedQuote.key === quoteSelectionKey) &&
    matchesWorkspaceAsset(loadedWorkspace, activeSymbol, periods, activeQuoteCurrency)) ? loadedWorkspace : null;
  useEffect(() => {
    setCopyOpen(false);
    setCopyPreview(null);
    setCopySourceId("");
  }, [workspace?.market_id]);
  const lastWorkspaceReloadAtRef = useRef(0);
  const scoreRefreshTimersRef = useRef([]);

  const categoryData = workspace?.categories || {};
  const marketDayData = categoryData.market?.rows || [];
  const macroData = categoryData.macro?.rows || [];
  const technicalData = categoryData.technical?.rows || [];
  const chartStudies = useMemo(() => mapTechnicalToStudies(technicalData), [technicalData]);
  const market = { score: marketTimeframe === "day" ? workspace?.daily?.market?.score ?? null : categoryData.market?.score?.score ?? null };
  const macro = { score: macroTimeframe === "day" ? workspace?.daily?.macro?.score ?? null : categoryData.macro?.score?.score ?? null };
  const technical = { score: technicalTimeframe === "day" ? workspace?.daily?.technical?.score ?? null : categoryData.technical?.score?.score ?? null };
  const workspaceAsset = workspace?.asset || null;
  const master = {
    weights: workspace?.master?.weights || DEFAULT_INTELLIGENCE_WEIGHTS,
    bias: workspace?.master?.master_bias || "–",
  };
  const assetLive = workspace?.quote || null;
  const quoteStatus = quotePresentationStatus({
    stale: assetLive?.stale,
    assetClass: workspaceAsset?.asset_class,
    marketRegion: workspaceAsset?.market_region,
    timeZone: workspaceAsset?.timezone,
    sourceAt: assetLive?.as_of,
  });
  const hasResolvedWorkspace = Boolean(workspace);
  const marketLoading = workspaceLoading && !hasResolvedWorkspace;
  const macroLoading = workspaceLoading && !hasResolvedWorkspace;
  const technicalLoading = workspaceLoading && !hasResolvedWorkspace;
  const scoresLoading = workspaceLoading && !hasResolvedWorkspace;

  const refreshWorkspaceOnce = useCallback(async () => {
    const now = Date.now();
    if (now - lastWorkspaceReloadAtRef.current < 1200) return;
    lastWorkspaceReloadAtRef.current = now;
    await reloadWorkspace({ forceNetwork: true });
  }, [reloadWorkspace]);

  const scheduleScoreRefresh = useCallback(() => {
    scoreRefreshTimersRef.current.forEach((timer) => window.clearTimeout(timer));
    scoreRefreshTimersRef.current = [3000, 8000, 15000].map((delay) =>
      window.setTimeout(() => { void reloadWorkspace({ forceNetwork: true }); }, delay)
    );
  }, [reloadWorkspace]);

  useEffect(() => () => {
    scoreRefreshTimersRef.current.forEach((timer) => window.clearTimeout(timer));
    scoreRefreshTimersRef.current = [];
  }, [activeSymbol]);

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
    // Keep the saved trading-pair identity while a refreshed score snapshot
    // triggers another match read. Clearing it switches the workspace back to
    // the legacy base asset and can start a EUR/USDT request loop.
    if (setupMatchesSymbolRef.current !== activeSymbol) {
      setupMatchesSymbolRef.current = activeSymbol;
      setSetupMatches(null);
    }
    setSetupMatchLoading(true);
    setSetupMatchError(false);

    async function loadSetupMatches() {
      try {
        const result = await fetchSetupMarketMatches(activeSymbol);
        if (!cancelled) {
          setSetupMatches(result.filter((match) => String(match?.symbol || "").toUpperCase() === activeSymbol));
          setSetupMatchError(false);
          setSetupMatchLoading(false);
        }
      } catch (error) {
        console.error("Failed to load setup matches for asset workspace", error);
        if (!cancelled) {
          setSetupMatchError(true);
          setSetupMatchLoading(false);
        }
      }
    }

    loadSetupMatches();
    return () => {
      cancelled = true;
    };
  }, [activeSymbol, workspace?.daily?.calculated_at]);

  const addMarket = async (name) => {
    await marketIndicatorAdd(name, activeSymbol);
    await refreshWorkspaceOnce();
    scheduleScoreRefresh();
  };
  const addMacroIndicator = async (name) => {
    await macroDataAdd(name, activeSymbol);
    await refreshWorkspaceOnce();
    scheduleScoreRefresh();
  };
  const addTechnicalIndicator = async (name) => {
    const result = await technicalDataAdd(name, activeSymbol);
    await refreshWorkspaceOnce();
    scheduleScoreRefresh();
    if (result?.status === "pending_source") {
      showSnackbar(`${name} is ingesteld. De meetwaarde wacht op de databron; er is nog geen score.`, "info");
    }
  };
  const saveWeights = async (weights) => {
    const result = workspace?.market_id
      ? await savePairBenchmarkWeights(workspace.market_id, weights)
      : await updateIntelligenceWeights(weights);
    await refreshWorkspaceOnce();
    return result;
  };

  const openCopy = async () => {
    if (!workspace?.market_id) return;
    setCopyBusy(true);
    setCopyOpen(true);
    setCopyPreview(null);
    setCopySourceId("");
    try {
      setCopySources(await getBenchmarkCopySources(workspace.market_id));
    } catch (error) {
      setCopySources([]);
      showSnackbar(String(error?.message || error), "error");
    } finally {
      setCopyBusy(false);
    }
  };

  const chooseCopySource = async (sourceId) => {
    setCopySourceId(sourceId);
    setCopyPreview(null);
    if (!sourceId || !workspace?.market_id) return;
    setCopyBusy(true);
    try {
      setCopyPreview(await previewBenchmarkCopy(Number(sourceId), workspace.market_id));
    } catch (error) {
      showSnackbar(String(error?.message || error), "error");
    } finally {
      setCopyBusy(false);
    }
  };

  const applyCopy = async () => {
    if (!copyPreview) return;
    setCopyBusy(true);
    try {
      await confirmBenchmarkCopy(copyPreview);
      setCopyOpen(false);
      setCopyPreview(null);
      await refreshWorkspaceOnce();
      scheduleScoreRefresh();
    } catch (error) {
      showSnackbar(String(error?.message || error), "error");
    } finally {
      setCopyBusy(false);
    }
  };

  useEffect(() => {
    let cancelled = false;

    async function loadAnalysisPreferences() {
      try {
        const response = await loadAssistantPreferencesShared();
        if (cancelled) return;
        setAnalysisChartInterval(
          normalizeTradingViewInterval(response?.preferences?.[ANALYSIS_CHART_INTERVAL_KEY])
        );
      } catch (error) {
        if (!cancelled) {
          console.error("Failed to load analysis preferences:", error);
        }
      }
    }

    void loadAnalysisPreferences();
    return () => {
      cancelled = true;
    };
  }, []);

  const handleAnalysisChartIntervalChange = async (nextInterval) => {
    const normalized = normalizeTradingViewInterval(nextInterval);
    setAnalysisChartInterval((current) => (current === normalized ? current : normalized));

    try {
      await updateAssistantPreferences({
        [ANALYSIS_CHART_INTERVAL_KEY]: normalized,
      });
      mergeAssistantPreferences({
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

      if (["market", "macro", "technical"].includes(detail.category)) {
        void refreshWorkspaceOnce();
        scheduleScoreRefresh();
      }
    };

    window.addEventListener(FINN_INDICATOR_MODAL_COMPLETED_EVENT, refreshCompletedIndicator);
    return () =>
      window.removeEventListener(FINN_INDICATOR_MODAL_COMPLETED_EVENT, refreshCompletedIndicator);
  }, [activeSymbol, refreshWorkspaceOnce, scheduleScoreRefresh]);

  useEffect(() => {
    let cancelled = false;

    async function loadWatchlistRows() {
        const nextRows = (watchlistData || []).map((row) => {
          const changeValue = row?.change_24h == null ? NaN : Number(row.change_24h);
          const assetClass = String(row?.asset_class || "").toLowerCase();
          return {
            symbol: row.symbol,
            displayName: row?.display_name || row?.displayName || ASSET_NAMES[row.symbol] || row.symbol,
            logoUrl: resolveAssetLogoUrl(row?.symbol, row?.logo_url || row?.logoUrl || null, assetClass),
            tradingviewSymbol: row?.tradingview_symbol || row?.tradingviewSymbol || null,
            assetClass,
            assetGroup: normalizeAssetGroup(assetClass),
            quoteCurrency: String(row?.quote_currency || "").toUpperCase(),
            lastPrice: formatQuotePrice(row?.price, locale, row?.quote_currency),
            change24h: formatPercent(changeValue, 2),
            changeTone: Number.isFinite(changeValue)
            ? changeValue >= 0 ? "text-emerald-600" : "text-red-600"
            : "text-slate-400",
          score: formatScore(row?.score),
          rawScore: row?.score,
        };
      });

      if (!cancelled) {
        setWatchlistRows(nextRows);
        setRemovedWatchlistSymbols((current) => {
          const remaining = current.filter((symbol) => nextRows.some((row) => row.symbol === symbol));
          return remaining.length === current.length ? current : remaining;
        });
      }
    }

    if (!watchlistLoading) loadWatchlistRows();
    return () => {
      cancelled = true;
    };
  }, [locale, ui, watchlistData, watchlistLoading]);

  const currentWatchlistRows = useMemo(
    () => watchlistRows.filter((row) => !removedWatchlistSymbols.includes(row.symbol)
      && (row.symbol !== activeSymbol || !activeQuoteCurrency || row.quoteCurrency === activeQuoteCurrency)),
    [activeQuoteCurrency, activeSymbol, removedWatchlistSymbols, watchlistRows]
  );
  const visibleWatchlistRows = useMemo(
    () => currentWatchlistRows.filter((row) => row.assetGroup === activeAssetGroup),
    [activeAssetGroup, currentWatchlistRows]
  );
  const activeWatchlistRow = useMemo(
    () => currentWatchlistRows.find((row) => row.symbol === activeSymbol) || null,
    [activeSymbol, currentWatchlistRows]
  );
  const handleAssetGroupChange = (nextGroup) => {
    const normalizedGroup = normalizeAssetGroup(nextGroup);
    setActiveAssetGroup(normalizedGroup);

    const activeRowGroup = normalizeAssetGroup(activeWatchlistRow?.assetGroup || activeWatchlistRow?.assetClass);
    if (activeRowGroup === normalizedGroup) return;

    const fallbackRow = currentWatchlistRows.find((row) => row.assetGroup === normalizedGroup);
    if (fallbackRow?.symbol) {
      handleAssetSelect(fallbackRow.symbol);
    }
  };
  const handleRemoveWatchlistAsset = useCallback((row) => {
    if (!row?.symbol) return;

    openConfirm({
      title: ui.watchlistRemoveTitle,
      context: ui.watchlistRemoveContext(row.symbol),
      impact: ui.watchlistRemoveImpact,
      safety: ui.watchlistRemoveSafety,
      contextLabel: ui.modalContextLabel,
      impactLabel: ui.modalImpactLabel,
      safetyLabel: ui.modalSafetyLabel,
      consequenceLabel: ui.modalConsequenceLabel,
      closeLabel: ui.modalCloseLabel,
      cancelText: ui.modalCancelLabel,
      consequence: ui.watchlistRemoveConsequence,
      tone: "danger",
      confirmText: ui.watchlistRemoveConfirm,
      busyText: ui.watchlistRemoveBusy,
      onConfirm: async () => {
        const normalizedSymbol = String(row.symbol || "").toUpperCase();
        await removeFromWatchlist(normalizedSymbol);
        setRemovedWatchlistSymbols((current) => current.includes(normalizedSymbol)
          ? current : [...current, normalizedSymbol]);
        const remainingRows = currentWatchlistRows.filter(
          (item) => String(item?.symbol || "").toUpperCase() !== normalizedSymbol
        );
        setWatchlistRows(remainingRows);

        const removedActiveAsset = normalizedSymbol === activeSymbol;
        if (removedActiveAsset) {
          const sameGroupFallback = remainingRows.find((item) => item.assetGroup === row.assetGroup);
          const nextFallback = sameGroupFallback || remainingRows[0] || null;
          if (nextFallback?.symbol) {
            setSelectedAsset(nextFallback.symbol);
            router.push(
              buildContextHref({
                pathname,
                symbol: nextFallback.symbol,
                context: initialTab,
                variant,
              }),
              { scroll: false }
            );
          }
        }

        await Promise.allSettled([reloadWatchlist(), refreshPersistedWatchlist(true)]);
        showSnackbar(ui.watchlistRemoveSuccess(normalizedSymbol));
      },
    });
  }, [
    activeSymbol,
    initialTab,
    openConfirm,
    pathname,
    currentWatchlistRows,
    reloadWatchlist,
    refreshPersistedWatchlist,
    router,
    setSelectedAsset,
    showSnackbar,
    ui,
    variant,
  ]);
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
  const activeTradingViewSymbol = workspaceAsset?.tradingview_symbol || null;

  const handleEditIndicator = (category, row) => {
    if (!workspace?.market_id || !row?.name) return;
    setPairConfigModal({ category, indicator: row.name });
  };
  const handleRemoveIndicator = (category, row) => {
    const marketId = workspace?.market_id;
    if (!marketId || !row?.name) return;
    const pair = workspace?.pair || activeSymbol;
    openConfirm({
      title: ui.removeIndicatorConfirm,
      context: ui.removeIndicatorContext(row.label, pair),
      impact: ui.removeIndicatorImpact,
      contextLabel: ui.modalContextLabel,
      impactLabel: ui.modalImpactLabel,
      closeLabel: ui.modalCloseLabel,
      cancelText: ui.modalCancelLabel,
      tone: "danger",
      confirmText: ui.removeIndicatorConfirm,
      onConfirm: async () => {
        await deletePairIndicatorConfig(marketId, category, row.name);
        await refreshWorkspaceOnce();
        scheduleScoreRefresh();
        showSnackbar(ui.removeIndicatorSuccess(row.label, pair));
      },
    });
  };

  const sections = useMemo(() => {
    const evidence = workspace?.daily?.indicator_evidence || {};
    const dayEvidence = (category, period, score) => period === "day" ? (normalizeScore(score) === null ? {} : evidence[category] || {}) : null;
    const marketRows = buildRows(marketDayData, locale, ui, dayEvidence("market", marketTimeframe, market?.score), market?.score, workspace?.quote_currency);
    const macroRows = buildRows(macroData, locale, ui, dayEvidence("macro", macroTimeframe, macro?.score), macro?.score);
    const technicalRows = buildRows(technicalData, locale, ui, dayEvidence("technical", technicalTimeframe, technical?.score), technical?.score);
    const notConfigured = (rows, loadingState, score) =>
      workspace?.symbol === activeSymbol && !loadingState && !isFallbackWorkspace && rows.length === 0 && normalizeScore(score) === null;
    const marketNotConfigured = notConfigured(marketRows, marketLoading, market?.score);
    const macroNotConfigured = notConfigured(macroRows, macroLoading, macro?.score);
    const technicalNotConfigured = notConfigured(technicalRows, technicalLoading, technical?.score);
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
        score: marketTimeframe === "day" ? normalizeScore(market?.score) : visibleScore(marketRows),
        insight: marketLoading ? ui.loadingMarket : buildSectionInsight("market", marketTimeframe === "day" ? market?.score : visibleScore(marketRows), ui, workspace?.daily?.market?.source_status, marketRows, marketNotConfigured),
        rows: marketRows,
        notConfigured: marketNotConfigured,
        emptyState: marketLoading ? ui.loadingMarket : marketNotConfigured ? ui.notConfigured : fallbackEmptyState(market?.score, marketRows, marketLoading, ui.marketEmpty),
        emptyAction: showEmptyAction(market?.score, marketRows, marketLoading) ? emptyActionButton("market") : null,
      },
      {
        id: "macro",
        title: locale?.startsWith("en") ? "Macro" : locale?.startsWith("de") ? "Makro" : SECTION_META.macro.label,
        eyebrow: locale?.startsWith("en") ? "Macro evidence" : locale?.startsWith("de") ? "Makrobelege" : "Macro-bewijs",
        icon: SECTION_META.macro.icon,
        score: macroTimeframe === "day" ? normalizeScore(macro?.score) : visibleScore(macroRows),
        insight: macroLoading ? ui.loadingMacro : buildSectionInsight("macro", macroTimeframe === "day" ? macro?.score : visibleScore(macroRows), ui, workspace?.daily?.macro?.source_status, macroRows, macroNotConfigured),
        rows: macroRows,
        notConfigured: macroNotConfigured,
        emptyState: macroLoading ? ui.loadingMacro : macroNotConfigured ? ui.notConfigured : fallbackEmptyState(macro?.score, macroRows, macroLoading, ui.macroEmpty),
        emptyAction: showEmptyAction(macro?.score, macroRows, macroLoading) ? emptyActionButton("macro") : null,
      },
      {
        id: "technical",
        title: locale?.startsWith("en") ? "Technical" : locale?.startsWith("de") ? "Technisch" : SECTION_META.technical.label,
        eyebrow: locale?.startsWith("en") ? "Technical evidence" : locale?.startsWith("de") ? "Technische belege" : "Technisch bewijs",
        icon: SECTION_META.technical.icon,
        score: technicalTimeframe === "day" ? normalizeScore(technical?.score) : visibleScore(technicalRows),
        insight: technicalLoading ? ui.loadingTechnical : buildSectionInsight("technical", technicalTimeframe === "day" ? technical?.score : visibleScore(technicalRows), ui, workspace?.daily?.technical?.source_status, technicalRows, technicalNotConfigured),
        rows: technicalRows,
        notConfigured: technicalNotConfigured,
        emptyState: technicalLoading ? ui.loadingTechnical : technicalNotConfigured ? ui.notConfigured : fallbackEmptyState(technical?.score, technicalRows, technicalLoading, ui.technicalEmpty),
        emptyAction: showEmptyAction(technical?.score, technicalRows, technicalLoading) ? emptyActionButton("technical") : null,
      },
    ];
  }, [activeSymbol, isFallbackWorkspace, locale, macro?.score, macroData, macroLoading, macroTimeframe, market?.score, marketDayData, marketLoading, marketTimeframe, technical?.score, technicalData, technicalLoading, technicalTimeframe, ui, workspace?.daily?.indicator_evidence, workspace?.quote_currency, workspace?.symbol]);

  const combinedSummary = useMemo(() => {
    if (Object.values(periods).every((period) => period === "day")) {
      const currentBenchmark = normalizeScore(workspace?.daily?.benchmark_score);
      if (currentBenchmark === null) return summarizeContextScores([], ui);
      const tone = scoreTone(currentBenchmark, ui);
      return { score: currentBenchmark, confidence: null, bias: tone.label, tone };
    }
    const visibleScores = {
      market: sections.find((section) => section.id === "market")?.score ?? null,
      macro: sections.find((section) => section.id === "macro")?.score ?? null,
      technical: sections.find((section) => section.id === "technical")?.score ?? null,
    };
    const summary = summarizeWeightedScores(visibleScores, master?.weights, ui);
    const hasVisibleScores = Object.values(visibleScores).some((score) => score !== null);

    if (!hasVisibleScores) return summarizeContextScores([], ui);
    return summary;
  }, [master, periods, sections, ui, workspace?.daily?.benchmark_score]);

  const handleAssetSelect = (symbol) => {
    const nextSymbol = String(symbol || activeSymbol).toUpperCase();
    setSelectedAsset(nextSymbol);
    const nextQuoteKey = tradingQuoteSessionKey(user?.id, nextSymbol);
    const rememberedNextQuote = nextQuoteKey && window.sessionStorage.getItem(nextQuoteKey);
    const href = buildContextHref({ pathname, symbol: nextSymbol, context: initialTab, variant });
    const nextHref = ["EUR", "USD", "USDT"].includes(rememberedNextQuote)
      ? `/asset?${withSelectedTradingQuote(href.split("?")[1], rememberedNextQuote)}` : href;
    router.push(nextHref, {
      scroll: false,
    });
  };

  const openSearch = (detail = undefined) => {
    if (typeof window === "undefined") return;
    if (detail?.mode === "indicator" && activeQuoteCurrency && !workspace?.market_id) {
      showSnackbar(locale?.startsWith("en") ? "The selected market is still loading. Please try again shortly."
        : locale?.startsWith("de") ? "Das gewählte Handelspaar wird noch geladen. Bitte versuche es gleich erneut."
        : "Het gekozen handelspaar wordt nog geladen. Probeer het zo opnieuw.", "info");
      return;
    }
    window.dispatchEvent(new CustomEvent(SEARCH_OPEN_EVENT, {
      detail: { ...(detail || {}), marketId: workspace?.market_id || null,
        quoteCurrency: workspace?.quote_currency || null },
    }));
  };

  return (
    <section className="space-y-3">
      <ActiveAssetCard
        activeSymbol={activeSymbol}
        assetName={activeAssetName}
        assetLogoUrl={activeAssetLogo}
        price={formatQuotePrice(assetLive?.price, locale, assetLive?.quote_currency)}
        change24h={assetLive?.change_24h}
        updatedAt={formatTimestamp(assetLive?.as_of || workspace?.generated_at, locale)}
        statusLabel={isFallbackWorkspace ? ui.fallbackData : quoteStatus === "closed_session" ? ui.closedMarketQuote : quoteStatus === "stale" ? ui.staleData : null}
        combinedSummary={combinedSummary}
        conditionOptions={t?.setups?.marketConditions?.options}
        isDailyBenchmark={Object.values(periods).every((period) => period === "day")}
        locale={locale}
        onSelectAsset={() => openSearch({ mode: "asset" })}
        ui={ui}
      />

      {availableQuotes.length > 0 && (
        <div className="flex flex-wrap items-center gap-2 rounded-xl border border-slate-200 bg-white px-4 py-3 text-sm">
          <span className="font-semibold text-slate-700">
            {locale?.startsWith("de") ? "Handelspaar" : locale?.startsWith("en") ? "Trading pair" : "Handelspaar"}
          </span>
          {availableQuotes.map((quote) => (
            <button key={quote} type="button"
              className={`rounded-lg border px-3 py-1.5 font-semibold ${activeQuoteCurrency === quote ? "border-blue-600 bg-blue-50 text-blue-700" : "border-slate-200 text-slate-700"}`}
              onClick={() => {
                if (setupSelectionKey) window.sessionStorage.removeItem(setupSelectionKey);
                setRememberedSetup({ key: setupSelectionKey, id: null });
                if (quoteSelectionKey) window.sessionStorage.setItem(quoteSelectionKey, quote);
                setRememberedQuote({ key: quoteSelectionKey, quote });
                const query = withSelectedTradingQuote(searchParams.toString(), quote);
                router.replace(`${pathname || "/asset"}?${query}`, { scroll: false });
              }}>
              {activeSymbol}/{quote}
            </button>
          ))}
        </div>
      )}

      <AssetList
        rows={visibleWatchlistRows}
        activeSymbol={activeSymbol}
        onSelect={handleAssetSelect}
        onRemove={handleRemoveWatchlistAsset}
        activeGroup={activeAssetGroup}
        onGroupChange={handleAssetGroupChange}
        onAddAsset={() => openSearch({ mode: "asset" })}
        conditionOptions={t?.setups?.marketConditions?.options}
        ui={ui}
      />

      <AnalysisChartSection
        interval={analysisChartInterval}
        tradingViewSymbol={activeTradingViewSymbol}
        studies={chartStudies}
        isOpen={showChart}
        onIntervalChange={handleAnalysisChartIntervalChange}
        onToggle={() => setShowChart((current) => !current)}
        ui={ui}
      />

      <ScoreOverview
        assetSymbol={activeSymbol}
        market={{ score: sections.find((section) => section.id === "market")?.score ?? null }}
        macro={{ score: sections.find((section) => section.id === "macro")?.score ?? null }}
        technical={{ score: sections.find((section) => section.id === "technical")?.score ?? null }}
        combined={
          isFallbackWorkspace && combinedSummary.score === null
            ? { ...combinedSummary, bias: ui.fallbackData, tone: scoreTone(50, ui) }
            : combinedSummary
        }
        weights={master?.weights}
        sections={sections}
        locale={locale}
        loading={scoresLoading}
        onSaveWeights={saveWeights}
        onOpenPlan={() => router.push(`/setup?symbol=${encodeURIComponent(activeSymbol)}`)}
        onSelectSetup={(setupId) => {
          if (setupSelectionKey) {
            window.sessionStorage.setItem(setupSelectionKey, String(setupId));
            setRememberedSetup({ key: setupSelectionKey, id: String(setupId) });
          }
          const query = new URLSearchParams(withSelectedBenchmarkSetup(searchParams.toString(), setupId));
          const chosenMatch = setupMatches?.find((match) => String(match.setup_id) === String(setupId));
          if (chosenMatch?.quote_currency) query.set("quote", String(chosenMatch.quote_currency).toUpperCase());
          else query.delete("quote");
          router.replace(`${pathname || "/asset"}?${query.toString()}`, { scroll: false });
        }}
        selectedSetupId={selectedSetupId}
        setupMatches={setupMatchLoading || setupMatchError ? null : activeQuoteCurrency ? setupMatches?.filter((match) =>
          match.market_id && String(match.quote_currency).toUpperCase() === activeQuoteCurrency
        ) : setupMatches}
        setupMatchError={setupMatchError}
        ui={ui}
        conditionOptions={t?.setups?.marketConditions?.options}
        isDailyBenchmark={Object.values(periods).every((period) => period === "day")}
      />

      {workspace?.market_id ? (
        <div className="rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm">
          <button type="button" onClick={openCopy} className="font-semibold text-blue-700 hover:underline">
            {ui.copyBenchmark}
          </button>
          {copyOpen ? (
            <div className="mt-3 space-y-3">
              <div className="flex items-center gap-2">
                <select value={copySourceId} onChange={(event) => chooseCopySource(event.target.value)}
                  aria-label={ui.copySource} className="rounded-lg border border-slate-300 px-3 py-2">
                  <option value="">{ui.copySource}</option>
                  {copySources.map((source) => <option key={source.market_id} value={source.market_id}>{source.pair}</option>)}
                </select>
                <button type="button" onClick={() => setCopyOpen(false)} className="text-slate-600">{ui.copyClose}</button>
              </div>
              {!copyBusy && !copySources.length ? <p className="text-slate-600">{ui.copyEmpty}</p> : null}
              {copyPreview ? (
                <div className="rounded-xl border border-blue-200 bg-blue-50 p-3">
                  <p className="font-semibold">{copyPreview.source_pair} → {copyPreview.target_pair}</p>
                  <p className="mt-1 text-slate-700">{copyPreview.indicators.length} {ui.copyIndicators}: {copyPreview.indicators.map((item) => item.indicator).join(", ") || "—"}</p>
                  <p className="mt-1 text-slate-700">{[
                    [ui.market, copyPreview.source_weights.market],
                    [ui.macro, copyPreview.source_weights.macro],
                    [ui.technical, copyPreview.source_weights.technical],
                  ].map(([label, weight]) => `${label} ${Math.round(weight * 100)}%`).join(" · ")}</p>
                  <p className="mt-1 text-slate-700">{ui.copyReplace}</p>
                  {copyPreview.replace.length ? <p className="mt-1 text-slate-600">{ui.copyReplaced}: {copyPreview.replace.join(", ")}</p> : null}
                  {copyPreview.unsupported.length ? <p className="mt-1 text-amber-700">{ui.copyUnsupported}: {copyPreview.unsupported.join(", ")}</p> : null}
                  <button type="button" onClick={applyCopy} disabled={copyBusy || copyPreview.unsupported.length > 0}
                    className="mt-3 rounded-lg bg-blue-600 px-4 py-2 font-semibold text-white disabled:opacity-50">
                    {ui.copyConfirm}
                  </button>
                </div>
              ) : null}
            </div>
          ) : null}
        </div>
      ) : null}

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
            onEditIndicator={workspace?.market_id ? handleEditIndicator : null}
            onRemoveIndicator={workspace?.market_id ? handleRemoveIndicator : null}
            emptyState={section.emptyState}
            emptyAction={section.emptyAction}
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
          />
        ))}
      </section>

      <ForwardReturnsSection symbol={activeSymbol} ui={ui} />

      <IndicatorConfigModal
        isOpen={Boolean(technicalConfigModal)}
        category="technical"
        indicator={technicalConfigModal}
        assetSymbol={activeSymbol}
        marketId={workspace?.market_id || null}
        marketLabel={workspace?.pair || null}
        mode="edit"
        onClose={() => setTechnicalConfigModal(null)}
        onCompleted={() => void refreshWorkspaceOnce()}
      />
      <IndicatorConfigModal
        isOpen={Boolean(pairConfigModal)}
        category={pairConfigModal?.category}
        indicator={pairConfigModal?.indicator}
        assetSymbol={activeSymbol}
        marketId={workspace?.market_id || null}
        marketLabel={workspace?.pair || null}
        mode="edit"
        onClose={() => setPairConfigModal(null)}
        onCompleted={() => { void refreshWorkspaceOnce(); scheduleScoreRefresh(); }}
      />
    </section>
  );
}
