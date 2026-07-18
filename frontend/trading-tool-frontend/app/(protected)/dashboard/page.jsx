"use client";

import { useEffect, useMemo } from "react";
import Link from "next/link";
import {
  ArrowRight,
  BarChart3,
  Bot,
  Brain,
  ClipboardList,
  LineChart,
  Sparkles,
} from "lucide-react";

import { useTranslation } from "@/app/providers/I18nProvider";
import { useActiveSetup } from "@/app/providers/SetupProvider";
import { useOverviewSnapshot } from "@/hooks/useOverviewSnapshot";
import { useScoresData } from "@/hooks/useScoresData";
import { useCurrentAsset } from "@/hooks/useCurrentAsset";
import { trackAssistantEvent } from "@/lib/api/assistantAnalytics";

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

function scoreTone(value) {
  const numericValue = clampNumber(value);

  if (numericValue >= 70) {
    return {
      label: "Positief",
      card: "border-emerald-200 bg-emerald-50/80 text-emerald-700",
      pill: "border-emerald-200 bg-emerald-50 text-emerald-700",
    };
  }

  if (numericValue <= 35) {
    return {
      label: "Negatief",
      card: "border-red-200 bg-red-50/80 text-red-700",
      pill: "border-red-200 bg-red-50 text-red-700",
    };
  }

  return {
    label: "Gemengd",
    card: "border-slate-200 bg-slate-50 text-slate-700",
    pill: "border-slate-200 bg-slate-50 text-slate-700",
  };
}

function SummaryMetric({ label, value, tone = "neutral" }) {
  const colorClass =
    tone === "positive"
      ? "text-emerald-600"
      : tone === "negative"
      ? "text-red-600"
      : "text-slate-900";

  return (
    <div className="rounded-2xl border border-slate-200 bg-white px-4 py-3 shadow-sm">
      <div className="text-[10px] font-black uppercase tracking-[0.22em] text-slate-400">
        {label}
      </div>
      <div className={`mt-2 text-xl font-black tracking-tight ${colorClass}`}>{value}</div>
    </div>
  );
}

function WorkspaceCard({ icon: Icon, eyebrow, title, body, href, accent, stats }) {
  return (
    <Link
      href={href}
      className="group rounded-[28px] border border-slate-200 bg-white p-5 shadow-[0_18px_50px_-40px_rgba(15,23,42,0.35)] transition hover:-translate-y-0.5 hover:border-blue-200 hover:shadow-[0_24px_60px_-40px_rgba(37,99,235,0.24)]"
    >
      <div className="flex items-start justify-between gap-4">
        <div>
          <div className="flex items-center gap-2 text-[10px] font-black uppercase tracking-[0.24em] text-blue-600">
            <Icon size={12} />
            {eyebrow}
          </div>
          <h2 className="mt-3 text-3xl font-black tracking-tight text-slate-950">{title}</h2>
          <p className="mt-3 max-w-xl text-sm font-medium leading-6 text-slate-500">{body}</p>
        </div>

        <div className={`rounded-full border px-3 py-1 text-[10px] font-black uppercase tracking-[0.22em] ${accent}`}>
          Open
        </div>
      </div>

      {stats?.length ? (
        <div className="mt-5 grid gap-3 md:grid-cols-3">
          {stats.map((stat) => (
            <div key={stat.label} className="rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3">
              <div className="text-[10px] font-black uppercase tracking-[0.22em] text-slate-400">
                {stat.label}
              </div>
              <div className="mt-2 text-base font-black tracking-tight text-slate-950">{stat.value}</div>
            </div>
          ))}
        </div>
      ) : null}

      <div className="mt-5 inline-flex items-center gap-2 text-[11px] font-black uppercase tracking-[0.22em] text-blue-600">
        Open workspace
        <ArrowRight size={14} className="transition group-hover:translate-x-0.5" />
      </div>
    </Link>
  );
}

export default function DashboardPage() {
  const { t, locale } = useTranslation();
  const { activeSetup } = useActiveSetup();
  const { symbol: activeSymbol } = useCurrentAsset({ includeFocusedBotLookup: false });
  const { snapshot, loading } = useOverviewSnapshot(activeSymbol);
  const { market, macro, technical, setup, master } = useScoresData(activeSymbol, {
    includeHistory: false,
    includeMaster: true,
  });

  useEffect(() => {
    trackAssistantEvent({
      event_name: "screen_view",
      page: "/dashboard",
      surface: "web",
      flow_type: "workspace_hub",
      asset: activeSymbol || null,
    });
  }, [activeSymbol]);

  const livePrice = snapshot?.live?.price;
  const liveChange = Number(snapshot?.live?.change_24h);

  const combinedSummary = useMemo(() => {
    const marketScore = clampNumber(market?.score);
    const macroScore = clampNumber(macro?.score);
    const technicalScore = clampNumber(technical?.score);
    const average = Math.round((marketScore + macroScore + technicalScore) / 3);
    const spread = Math.max(marketScore, macroScore, technicalScore) - Math.min(marketScore, macroScore, technicalScore);

    return {
      score: average,
      confidence: Math.max(32, Math.min(92, 100 - spread)),
      tone: scoreTone(average),
      bias: master?.bias && master.bias !== "—" ? master.bias : scoreTone(average).label,
    };
  }, [macro?.score, market?.score, master?.bias, technical?.score]);

  const workspaceCards = [
    {
      icon: LineChart,
      eyebrow: "Analyse",
      title: "Asset intelligence",
      body:
        "Market, Macro en Technisch zijn nu de primaire analyse-workspace. Daar staan ook de chart, contextscore en bewijslijsten.",
      href: `/asset?symbol=${activeSymbol || "BTC"}`,
      accent: "border-blue-200 bg-blue-50 text-blue-700",
      stats: [
        { label: "Markt", value: `${Math.round(clampNumber(market?.score))}/100` },
        { label: "Macro", value: `${Math.round(clampNumber(macro?.score))}/100` },
        { label: "Technisch", value: `${Math.round(clampNumber(technical?.score))}/100` },
      ],
    },
    {
      icon: ClipboardList,
      eyebrow: "Mijn Plan",
      title: "Setup en positionering",
      body:
        "Gebruik Mijn Plan voor setupkwaliteit, risicokader, position sizing en wat je onder deze marktomstandigheden wel of niet mag doen.",
      href: `/setup?symbol=${activeSymbol || "BTC"}`,
      accent: "border-emerald-200 bg-emerald-50 text-emerald-700",
      stats: [
        { label: "Setup score", value: `${Math.round(clampNumber(setup?.score))}/100` },
        { label: "Timeframe", value: activeSetup?.timeframe || "—" },
        { label: "Bias", value: combinedSummary.bias || "—" },
      ],
    },
    {
      icon: Bot,
      eyebrow: "Automation",
      title: "Execution en bots",
      body:
        "Automation bewaakt DCA, execution, botstatus en interventies. De analyse wordt hier niet opnieuw opgebouwd, maar alleen uitgevoerd.",
      href: `/bot?symbol=${activeSymbol || "BTC"}`,
      accent: "border-orange-200 bg-orange-50 text-orange-700",
      stats: [
        { label: "Actieve setup", value: activeSetup?.name || activeSetup?.signal || "Geen setup" },
        { label: "Risk mode", value: activeSetup?.risk_profile || "Dynamic" },
        { label: "Signaal", value: activeSetup?.signal || "Monitor" },
      ],
    },
    {
      icon: Brain,
      eyebrow: "Reflectie",
      title: "Rapport en evaluatie",
      body:
        "Daily reports, terugkijken, leerpunten en historische beoordeling horen in Reflectie. Daarmee blijft Analyse schoon en scanbaar.",
      href: `/report?symbol=${activeSymbol || "BTC"}`,
      accent: "border-slate-200 bg-slate-50 text-slate-700",
      stats: [
        { label: "Context", value: combinedSummary.bias || "—" },
        { label: "Confidence", value: `${combinedSummary.confidence}%` },
        { label: "Laatste update", value: formatTimestamp(snapshot?.live?.timestamp, locale) },
      ],
    },
  ];

  return (
    <div className="page-container min-h-screen bg-white">
      <header className="page-header mb-8 border-l-4 border-blue-600 pl-4 sm:mb-12 sm:pl-8">
        <div className="mb-2 flex items-center gap-2 text-[10px] font-black uppercase tracking-[0.3em] text-blue-600 opacity-80 sm:text-[11px]">
          <BarChart3 size={12} />
          {t.dashboard.title}
        </div>
        <div className="max-w-3xl">
          <h1 className="page-title text-3xl font-black leading-none tracking-tight text-slate-950 sm:text-5xl">
            Workspace Overview
          </h1>
          <p className="page-subtitle mt-3 text-sm font-medium leading-relaxed text-slate-500 sm:text-[15px]">
            De oude Overview is opgesplitst. Analyse toont nu de marktcontext, Mijn Plan bewaakt de setup, Automation voert uit en Reflectie kijkt terug.
          </p>
        </div>
      </header>

      <section className="rounded-[32px] border border-slate-200 bg-white p-5 shadow-[0_22px_60px_-42px_rgba(15,23,42,0.38)] lg:p-6">
        <div className="flex flex-col gap-6 xl:flex-row xl:items-end xl:justify-between">
          <div className="min-w-0">
            <div className="flex items-center gap-2 text-[10px] font-black uppercase tracking-[0.28em] text-blue-600">
              <Sparkles size={12} />
              Active asset
            </div>
            <div className="mt-3 flex flex-wrap items-center gap-x-3 gap-y-2">
              <span className="rounded-full border border-slate-200 bg-slate-50 px-4 py-2 text-sm font-black tracking-tight text-slate-950">
                {activeSymbol || "BTC"}
              </span>
              <span className="text-4xl font-black tracking-tight text-slate-950 lg:text-5xl">
                {loading ? "Laden..." : formatPrice(livePrice, locale)}
              </span>
              <span className={`text-xl font-black ${liveChange >= 0 ? "text-emerald-600" : "text-red-600"}`}>
                {formatPercent(liveChange)}
              </span>
              <span className="text-sm font-black uppercase tracking-[0.18em] text-slate-500">1D</span>
              <span className="text-sm font-semibold text-slate-500">
                Updated {formatTimestamp(snapshot?.live?.timestamp, locale)}
              </span>
            </div>
          </div>

          <div className="grid gap-3 sm:grid-cols-3">
            <SummaryMetric label="Combined score" value={`${combinedSummary.score}/100`} />
            <SummaryMetric label="Bias" value={combinedSummary.bias || "—"} />
            <SummaryMetric label="Confidence" value={`${combinedSummary.confidence}%`} />
          </div>
        </div>
      </section>

      <section className="mt-8 grid gap-6 lg:grid-cols-2">
        {workspaceCards.map((card) => (
          <WorkspaceCard key={card.title} {...card} />
        ))}
      </section>

      <section className="mt-8 rounded-[28px] border border-slate-200 bg-white p-5 shadow-[0_20px_60px_-42px_rgba(15,23,42,0.35)]">
        <div className="flex flex-wrap items-center gap-3">
          <span className="text-[10px] font-black uppercase tracking-[0.24em] text-blue-600">
            Nieuwe verdeling
          </span>
          <span className={`rounded-full border px-3 py-1 text-[10px] font-black uppercase tracking-[0.22em] ${scoreTone(market?.score).pill}`}>
            Markt {Math.round(clampNumber(market?.score))}/100
          </span>
          <span className={`rounded-full border px-3 py-1 text-[10px] font-black uppercase tracking-[0.22em] ${scoreTone(macro?.score).pill}`}>
            Macro {Math.round(clampNumber(macro?.score))}/100
          </span>
          <span className={`rounded-full border px-3 py-1 text-[10px] font-black uppercase tracking-[0.22em] ${scoreTone(technical?.score).pill}`}>
            Technisch {Math.round(clampNumber(technical?.score))}/100
          </span>
          <span className={`rounded-full border px-3 py-1 text-[10px] font-black uppercase tracking-[0.22em] ${scoreTone(setup?.score).pill}`}>
            Setup {Math.round(clampNumber(setup?.score))}/100
          </span>
        </div>

        <div className="mt-4 grid gap-4 lg:grid-cols-4">
          <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
            <div className="text-[10px] font-black uppercase tracking-[0.22em] text-slate-400">Analyse</div>
            <p className="mt-2 text-sm font-medium leading-6 text-slate-600">
              Chart, contextscore, Markt, Macro en Technisch.
            </p>
          </div>
          <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
            <div className="text-[10px] font-black uppercase tracking-[0.22em] text-slate-400">Mijn Plan</div>
            <p className="mt-2 text-sm font-medium leading-6 text-slate-600">
              Setupkwaliteit, position sizing en planvoorwaarden.
            </p>
          </div>
          <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
            <div className="text-[10px] font-black uppercase tracking-[0.22em] text-slate-400">Automation</div>
            <p className="mt-2 text-sm font-medium leading-6 text-slate-600">
              Bots, DCA, execution, alerts en interventies.
            </p>
          </div>
          <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
            <div className="text-[10px] font-black uppercase tracking-[0.22em] text-slate-400">Reflectie</div>
            <p className="mt-2 text-sm font-medium leading-6 text-slate-600">
              Dagrapport, terugblik en historische evaluatie.
            </p>
          </div>
        </div>
      </section>
    </div>
  );
}
