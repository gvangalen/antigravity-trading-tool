"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import {
  Brain,
  ChevronDown,
  Globe,
  LineChart,
  Plus,
  Settings2,
  Target,
  TrendingUp,
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
  if (score >= 70) return "Verbetert";
  if (score <= 35) return "Verslechtert";
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

function fallbackAssessment(label, direction, tone) {
  return `${label} ${direction === "Stabiel" ? "blijft stabiel" : direction === "Verbetert" ? "verbetert" : direction === "Verslechtert" ? "verslechtert" : "blijft actief"} en geeft nu een ${tone.label.toLowerCase()} signaal.`;
}

function buildRows(items, locale) {
  const source = Array.isArray(items) ? items : [];

  return source.map((item, index) => {
    const name = item?.name || item?.indicator || `indicator_${index}`;
    const label = prettifyName(name);
    const score = clampNumber(item?.score, 50);
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
      scoreLabel: `${tone.label} · ${score}`,
      detail,
      timestamp: item?.timestamp || item?.date || null,
      raw: item,
    };
  });
}

function buildSectionInsight(sectionId, sectionScore, rows) {
  const score = clampNumber(sectionScore, 50);
  const focus = rows.slice(0, 2).map((row) => row.label.toLowerCase());

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

function SummaryPill({ label, value, tone = "neutral" }) {
  const toneClass =
    tone === "positive"
      ? "border-emerald-200 bg-emerald-50 text-emerald-700"
      : tone === "negative"
      ? "border-red-200 bg-red-50 text-red-700"
      : "border-slate-200 bg-white text-slate-700";

  return (
    <div className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[10px] font-black ${toneClass}`}>
      <span className="uppercase tracking-[0.18em]">{label}</span>
      <span className="tracking-tight">{value}</span>
    </div>
  );
}

function ScoreOverview({ market, macro, technical, combined, setup }) {
  const items = [
    {
      id: "market",
      label: "Markt",
      score: clampNumber(market?.score),
      summary: market?.bias || market?.trend || "Gemengd",
    },
    {
      id: "macro",
      label: "Macro",
      score: clampNumber(macro?.score),
      summary: macro?.bias || macro?.trend || "Tegenwind",
    },
    {
      id: "technical",
      label: "Technisch",
      score: clampNumber(technical?.score),
      summary: technical?.bias || technical?.trend || "Zwak",
    },
    {
      id: "combined",
      label: "Gecombineerd",
      score: clampNumber(combined?.score),
      summary: combined?.bias || "Voorzichtig",
    },
  ];

  return (
    <section className="rounded-[24px] border border-slate-200/80 bg-white shadow-[0_18px_40px_-36px_rgba(15,23,42,0.26)]">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-100 px-4 py-3.5">
        <div className="min-w-0">
          <div className="text-[10px] font-black uppercase tracking-[0.24em] text-blue-600">
            Context Scores
          </div>
        </div>
        <div className="inline-flex items-center gap-2 rounded-full border border-slate-200 bg-slate-50 px-3 py-1 text-[10px] font-black uppercase tracking-[0.14em] text-slate-600">
          Setup {clampNumber(setup?.score)}/100
          <span className="text-slate-400">·</span>
          Bekijk in Mijn Plan
        </div>
      </div>

      <div className="grid gap-3 px-4 py-3 lg:grid-cols-4">
        {items.map((item) => {
          const tone = scoreTone(item.score);
          return (
            <div key={item.id} className={`rounded-[18px] border px-4 py-3 ${tone.pill}`}>
              <div className="text-[9px] font-black uppercase tracking-[0.2em] opacity-70">
                {item.label}
              </div>
              <div className="mt-1.5 flex items-baseline gap-2">
                <span className="text-[28px] font-black leading-none tracking-tight">{item.score}</span>
                <span className="text-xs font-bold uppercase tracking-[0.14em] opacity-80">
                  {item.summary}
                </span>
              </div>
            </div>
          );
        })}
      </div>
    </section>
  );
}

function AnalysisChartSection({ symbol, isOpen, onToggle }) {
  const tvSymbol = `BINANCE:${symbol}USDT`;

  return (
    <section className="rounded-[24px] border border-slate-200/80 bg-white shadow-[0_18px_40px_-36px_rgba(15,23,42,0.26)]">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-100 px-4 py-3.5">
        <div>
          <div className="text-[10px] font-black uppercase tracking-[0.24em] text-blue-600">
            TradingView Chart
          </div>
          <p className="mt-1.5 text-[13px] font-medium text-slate-500">
            Prijsstructuur en visueel bewijs voor de actieve assetanalyse.
          </p>
        </div>
        <button
          type="button"
          onClick={onToggle}
          className="inline-flex items-center gap-2 rounded-full border border-slate-200 bg-slate-50 px-3 py-1 text-[10px] font-black uppercase tracking-[0.16em] text-slate-600 transition hover:border-blue-200 hover:text-blue-600"
        >
          {isOpen ? "Chart sluiten" : "Open chart"}
        </button>
      </div>

      {isOpen ? (
        <div className="p-4">
          <TradingViewSmartChart
            symbol={tvSymbol}
            interval="D"
            indicators={[]}
            focusedBotId={null}
            setFocusedBotId={() => {}}
            height={430}
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

function PlanBridge({ setup }) {
  return (
    <section className="rounded-[24px] border border-slate-200/80 bg-slate-50/70 px-5 py-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <div className="text-[10px] font-black uppercase tracking-[0.22em] text-slate-400">
            Overgang naar Mijn Plan
          </div>
          <p className="mt-1 text-sm font-medium text-slate-600">
            Actieve setup: {clampNumber(setup?.score)}/100. De volledige setupkwaliteit, position sizing en risk/reward horen in Mijn Plan.
          </p>
        </div>
        <div className="inline-flex items-center rounded-full border border-slate-200 bg-white px-4 py-2 text-[11px] font-black uppercase tracking-[0.16em] text-slate-600">
          Setup {clampNumber(setup?.score)}/100
        </div>
      </div>
    </section>
  );
}

function formatBiasLabel(value) {
  const source = String(value || "").trim();
  if (!source || source === "—") return "Neutraal";
  return source;
}

function AssetList({ rows, activeSymbol, onSelect, onAddAsset }) {
  return (
    <div className="rounded-[22px] border border-slate-200 bg-slate-50/70 p-3.5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <span className="text-[10px] font-black uppercase tracking-[0.24em] text-slate-400">
            Watchlist
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
          Asset toevoegen
        </button>
      </div>

      <div className="mt-3 overflow-hidden rounded-[18px] border border-slate-200 bg-white">
        <div className="grid grid-cols-[minmax(0,1.5fr)_120px_100px_80px_120px] gap-3 border-b border-slate-100 px-4 py-2.5 text-[9px] font-black uppercase tracking-[0.2em] text-slate-400">
          <div>Asset</div>
          <div className="text-right">Laatste</div>
          <div className="text-right">24u</div>
          <div className="text-right">Score</div>
          <div className="text-right">Bias</div>
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
    </div>
  );
}

function SectionScorePill({ score }) {
  const tone = scoreTone(score);
  return (
    <div className={`inline-flex items-center rounded-full border px-2.5 py-0.5 text-[10px] font-black uppercase tracking-[0.18em] ${tone.pill}`}>
      {clampNumber(score)}/100
    </div>
  );
}

function EvidenceRow({ row, expanded, onToggle, renderExpandedActions }) {
  return (
    <div className="border-t border-slate-100">
      <button
        type="button"
        onClick={onToggle}
        className="w-full px-4 py-3 text-left transition hover:bg-slate-50/80"
      >
        <div className="grid gap-4 lg:grid-cols-[minmax(0,1.1fr)_minmax(120px,0.5fr)_minmax(160px,0.55fr)_minmax(240px,0.9fr)] lg:items-center">
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
              <div className="text-[15px] font-black leading-tight text-slate-950">{row.label}</div>
            </div>
          </div>

          <div className="lg:text-right">
            <div className="text-[10px] font-black uppercase tracking-[0.22em] text-slate-400 lg:hidden">
              Waarde
            </div>
            <div className="text-[15px] font-black text-slate-950">{row.value}</div>
          </div>

          <div>
            <div className="text-[10px] font-black uppercase tracking-[0.22em] text-slate-400 lg:hidden">
              Ontwikkeling
            </div>
            <span className="inline-flex items-center gap-2 rounded-full bg-slate-100 px-2.5 py-0.5 text-[10px] font-bold text-slate-600">
              <span className={`h-2 w-2 rounded-full ${row.signalTone.dot}`} />
              {row.direction}
            </span>
          </div>

          <div>
            <div className="text-[10px] font-black uppercase tracking-[0.22em] text-slate-400 lg:hidden">
              Beoordeling
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <span className={`inline-flex items-center rounded-full border px-2.5 py-0.5 text-[10px] font-black uppercase tracking-[0.14em] ${row.signalTone.pill}`}>
                {row.scoreLabel}
              </span>
            </div>
            <p className="mt-1.5 text-[13px] font-medium leading-6 text-slate-500">
              {row.detail}
            </p>
          </div>
        </div>
      </button>

      {expanded ? (
        <div className="bg-slate-50/70 px-4 py-3.5">
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
      <div className="flex flex-wrap items-start justify-between gap-3 border-b border-slate-100 px-4 py-4">
        <div className="min-w-0">
          <div className="flex items-center gap-2 text-[10px] font-black uppercase tracking-[0.26em] text-blue-600">
            <Icon size={12} />
            {eyebrow}
          </div>
          <div className="mt-1.5 flex items-center gap-3">
            <h2 className="text-[20px] font-black tracking-tight text-slate-950">{title}</h2>
            <SectionScorePill score={score} />
          </div>
          <p className="mt-2 max-w-3xl text-[13px] font-medium leading-6 text-slate-500">
            {insight}
          </p>
        </div>
        {action}
      </div>

      <div className="hidden border-b border-slate-100 px-4 py-2.5 lg:grid lg:grid-cols-[minmax(0,1.1fr)_minmax(120px,0.5fr)_minmax(160px,0.55fr)_minmax(240px,0.9fr)] lg:gap-4">
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
  const { watchlist } = useWatchlist();
  const symbolFromUrl = searchParams.get("symbol")?.toUpperCase();
  const activeSymbol = symbolFromUrl || selectedAsset || "BTC";
  const [macroTimeframe] = useState("day");
  const [technicalTimeframe] = useState("day");
  const [expandedRowKey, setExpandedRowKey] = useState(null);
  const [technicalConfigModal, setTechnicalConfigModal] = useState(null);
  const [watchlistRows, setWatchlistRows] = useState([]);
  const [showChart, setShowChart] = useState(false);
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

  const { market, macro, technical, setup, master } = useScoresData(activeSymbol, {
    includeHistory: false,
    includeMaster: true,
  });
  const { snapshot: overviewSnapshot, loading: overviewLoading } = useOverviewSnapshot(activeSymbol);

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

  const assetOptions = useMemo(() => {
    const base =
      Array.isArray(availableAssets) && availableAssets.length
        ? availableAssets
        : ["BTC", "ETH", "SOL", "ADA", "DOT"];
    return Array.from(new Set([activeSymbol, ...(watchlist || []), ...base]));
  }, [activeSymbol, availableAssets, watchlist]);

  const watchlistSymbols = useMemo(() => {
    const preferred = Array.isArray(watchlist) && watchlist.length ? watchlist : assetOptions;
    return Array.from(new Set([activeSymbol, ...preferred])).slice(0, 6);
  }, [activeSymbol, assetOptions, watchlist]);

  useEffect(() => {
    let cancelled = false;

    async function loadWatchlistRows() {
      const nextRows = await Promise.all(
        watchlistSymbols.map(async (symbol) => {
          try {
            const [latestResult, scoresResult] = await Promise.allSettled([
              fetchLatestPrice(symbol, { forceFresh: false }),
              getDailyScores(symbol),
            ]);

            const latest = latestResult.status === "fulfilled" ? latestResult.value : null;
            const scores = scoresResult.status === "fulfilled" ? scoresResult.value : null;
            const combinedScore = Math.round(
              (
                clampNumber(scores?.market?.score, 50) +
                clampNumber(scores?.macro?.score, 50) +
                clampNumber(scores?.technical?.score, 50)
              ) / 3
            );
            const bias = formatBiasLabel(scores?.market?.advies || scores?.market?.bias);
            const biasTone = scoreTone(combinedScore).pill;
            const changeValue = Number(latest?.change_24h);

            return {
              symbol,
              lastPrice: formatPrice(latest?.price, locale),
              change24h: formatPercent(changeValue, 2),
              changeTone: changeValue >= 0 ? "text-emerald-600" : "text-red-600",
              score: combinedScore,
              bias,
              biasTone,
            };
          } catch {
            return {
              symbol,
              lastPrice: "—",
              change24h: "—",
              changeTone: "text-slate-400",
              score: "—",
              bias: "Neutraal",
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
  }, [locale, watchlistSymbols]);

  const combinedSummary = useMemo(() => {
    const marketScore = clampNumber(market?.score);
    const macroScore = clampNumber(macro?.score);
    const technicalScore = clampNumber(technical?.score);
    const average = Math.round((marketScore + macroScore + technicalScore) / 3);
    const spread = Math.max(marketScore, macroScore, technicalScore) - Math.min(marketScore, macroScore, technicalScore);
    const confidence = Math.max(32, Math.min(92, 100 - spread));
    const tone = scoreTone(average);

    return {
      score: average,
      confidence,
      bias: master?.bias && master.bias !== "—" ? master.bias : tone.label,
      tone,
    };
  }, [macro, market, master, technical]);

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
        insight: buildSectionInsight("market", market?.score, marketRows),
        rows: marketRows,
        emptyState: marketLoading ? "Marktdata laden..." : SECTION_META.market.empty,
      },
      {
        id: "macro",
        title: SECTION_META.macro.label,
        eyebrow: SECTION_META.macro.eyebrow,
        icon: SECTION_META.macro.icon,
        score: macro?.score,
        insight: buildSectionInsight("macro", macro?.score, macroRows),
        rows: macroRows,
        emptyState: macroLoading ? "Macrodata laden..." : SECTION_META.macro.empty,
      },
      {
        id: "technical",
        title: SECTION_META.technical.label,
        eyebrow: SECTION_META.technical.eyebrow,
        icon: SECTION_META.technical.icon,
        score: technical?.score,
        insight: buildSectionInsight("technical", technical?.score, technicalRows),
        rows: technicalRows,
        emptyState: technicalLoading ? "Technische data laden..." : SECTION_META.technical.empty,
      },
    ];
  }, [locale, macro, macroData, macroLoading, market, marketDayData, marketLoading, technical, technicalData, technicalLoading]);

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
      <section className="rounded-[28px] border border-slate-200/80 bg-white p-4 shadow-[0_18px_40px_-36px_rgba(15,23,42,0.26)] lg:p-5">
        <div className="space-y-4">
          <AssetList
            rows={watchlistRows}
            activeSymbol={activeSymbol}
            onSelect={handleAssetSelect}
            onAddAsset={() => openSearch()}
          />

          <div className="min-w-0">
        <div className="flex flex-col gap-4 xl:flex-row xl:items-end xl:justify-between">
          <div className="min-w-0">
            <div className="flex items-center gap-2 text-[10px] font-black uppercase tracking-[0.22em] text-blue-600">
              <Brain size={12} />
              Asset Intelligence
            </div>

            <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1.5">
              <button
                type="button"
                onClick={() => openSearch()}
                className="inline-flex items-center gap-2 rounded-full border border-slate-200 bg-slate-50 px-3 py-1.5 text-[13px] font-black tracking-tight text-slate-950 transition hover:border-blue-200 hover:text-blue-600"
              >
                <span>{activeSymbol}</span>
                <span className="text-slate-400">{ASSET_NAMES[activeSymbol] || "Asset"}</span>
              </button>
              <span className="text-[34px] font-black leading-none tracking-tight text-slate-950 lg:text-[38px]">
                {formatPrice(btcLive?.price, locale)}
              </span>
              <span className={`text-lg font-black ${Number(btcLive?.change_24h) >= 0 ? "text-emerald-600" : "text-red-600"}`}>
                {formatPercent(btcLive?.change_24h)}
              </span>
              <span className="text-[13px] font-black uppercase tracking-[0.14em] text-slate-500">1D</span>
              <span className="text-[13px] font-semibold text-slate-500">
                Updated {formatTimestamp(btcLive?.timestamp, locale)}
              </span>
            </div>
          </div>

          <div className="flex flex-wrap gap-2 xl:justify-end">
            <SummaryPill label="Combined score" value={`${combinedSummary.score}/100`} />
            <SummaryPill
              label="Bias"
              value={combinedSummary.bias}
              tone={
                combinedSummary.tone.label === "Positief"
                  ? "positive"
                  : combinedSummary.tone.label === "Negatief"
                  ? "negative"
                  : "neutral"
              }
            />
            <SummaryPill label="Confidence" value={`${combinedSummary.confidence}%`} />
          </div>
        </div>
        </div>
        </div>
      </section>

      <ScoreOverview
        market={market}
        macro={macro}
        technical={technical}
        combined={combinedSummary}
        setup={setup}
      />

      <AnalysisChartSection
        symbol={activeSymbol}
        isOpen={showChart}
        onToggle={() => setShowChart((current) => !current)}
      />

      <section className="rounded-[24px] border border-slate-200/80 bg-white p-4 shadow-[0_18px_40px_-36px_rgba(15,23,42,0.26)]">
        <div className="mb-3">
          <div className="text-[10px] font-black uppercase tracking-[0.24em] text-blue-600">
            Marktregime
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
                  Indicator toevoegen
                </button>
              ) : section.id === "macro" ? (
                <button
                  type="button"
                  onClick={() => openSearch({ mode: "indicator", category: "macro" })}
                  className="inline-flex items-center gap-2 rounded-full border border-slate-200 bg-white px-3 py-1.5 text-[10px] font-black uppercase tracking-[0.16em] text-slate-700 transition hover:border-blue-200 hover:text-blue-600"
                >
                  <Plus size={12} />
                  Indicator toevoegen
                </button>
              ) : section.id === "technical" ? (
                <button
                  type="button"
                  onClick={() => openSearch({ mode: "indicator", category: "technical" })}
                  className="inline-flex items-center gap-2 rounded-full border border-slate-200 bg-white px-3 py-1.5 text-[10px] font-black uppercase tracking-[0.16em] text-slate-700 transition hover:border-blue-200 hover:text-blue-600"
                >
                  <Plus size={12} />
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

      <PlanBridge setup={setup} />

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
