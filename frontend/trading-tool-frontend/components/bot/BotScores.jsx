"use client";

import CardLoader from "@/components/ui/CardLoader";
import {
  AlertTriangle,
  ArrowRight,
  Bot,
  CheckCircle2,
  Gauge,
  Layers3,
  Target,
} from "lucide-react";
import { useTranslation } from "@/app/providers/I18nProvider";

const SCORE_DEFINITIONS = [
  { key: "market", aliases: ["market", "market_score"] },
  { key: "macro", aliases: ["macro", "macro_score"] },
  { key: "technical", aliases: ["technical", "technical_score"] },
  { key: "setup", aliases: ["setup", "setup_score"] },
];

function readScore(scores, aliases) {
  for (const key of aliases) {
    const rawValue = scores?.[key];
    const value =
      rawValue && typeof rawValue === "object"
        ? rawValue.score ?? rawValue.value
        : rawValue;

    if (Number.isFinite(Number(value))) return Number(value);
  }

  return null;
}

function scoreTone(score) {
  if (score === null) {
    return "border-slate-200 bg-slate-50 text-slate-400 dark:border-slate-800 dark:bg-slate-900/60";
  }
  if (score >= 70) {
    return "border-emerald-200 bg-emerald-50/70 text-emerald-700 dark:border-emerald-900/50 dark:bg-emerald-950/20 dark:text-emerald-300";
  }
  if (score <= 35) {
    return "border-red-200 bg-red-50/70 text-red-700 dark:border-red-900/50 dark:bg-red-950/20 dark:text-red-300";
  }
  return "border-slate-200 bg-slate-50 text-slate-700 dark:border-slate-800 dark:bg-slate-900/60 dark:text-slate-200";
}

export default function BotScores({
  scores = {},
  bot = null,
  presentation = null,
  loading = false,
}) {
  const { t } = useTranslation();
  const copy = t?.botPage?.botScores || {};
  const strategy = bot?.strategy || null;
  const setup = strategy?.setup || null;
  const planName = strategy?.name || setup?.name || copy.notLinked;
  const scoreEntries = SCORE_DEFINITIONS.map((definition) => ({
    ...definition,
    value: readScore(scores, definition.aliases),
  }));
  const setupScore = scoreEntries.find((entry) => entry.key === "setup")?.value ?? null;
  const hasScores = scoreEntries.some((entry) => entry.value !== null);
  const hasSetupMismatch = setupScore !== null && setupScore < 40;

  if (loading) {
    return (
      <div className="rounded-3xl border border-slate-200 bg-white p-5 shadow-sm dark:border-slate-800 dark:bg-slate-950">
        <CardLoader text={copy.loading} />
      </div>
    );
  }

  if (!bot) {
    return (
      <div className="rounded-3xl border border-dashed border-slate-200 bg-white px-5 py-8 text-center shadow-sm dark:border-slate-800 dark:bg-slate-950">
        <p className="text-xs font-black uppercase tracking-widest text-slate-400">
          {copy.selectBot}
        </p>
      </div>
    );
  }

  const chain = [
    {
      key: "setup",
      label: copy.setup,
      value: setup?.name || copy.notLinked,
      icon: Layers3,
      missing: !setup,
    },
    {
      key: "strategy",
      label: copy.strategy,
      value: strategy?.name || copy.notLinked,
      icon: Target,
      missing: !strategy,
    },
    {
      key: "decision",
      label: copy.decision,
      value: presentation?.action || copy.insufficientData,
      meta: `${copy.confidence}: ${presentation?.confidence || copy.insufficientData}`,
      icon: Gauge,
      missing: !presentation?.action,
    },
  ];

  return (
    <section className="overflow-hidden rounded-3xl border border-slate-200 bg-white shadow-sm dark:border-slate-800 dark:bg-slate-950">
      <div className="flex flex-col gap-4 border-b border-slate-100 px-5 py-4 dark:border-slate-800 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex min-w-0 items-center gap-3">
          <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-blue-50 text-blue-600 dark:bg-blue-950/50 dark:text-blue-300">
            <Bot size={18} />
          </span>
          <div className="min-w-0">
            <p className="text-[9px] font-black uppercase tracking-[0.2em] text-blue-600">
              {copy.eyebrow}
            </p>
            <div className="mt-1 flex min-w-0 flex-wrap items-center gap-x-2 gap-y-1">
              <h2 className="truncate text-base font-black text-slate-950 dark:text-white">
                {bot.name}
              </h2>
              <span className="text-xs font-bold text-slate-400">
                {presentation?.symbol || "—"} · {presentation?.timeframe || "—"}
              </span>
            </div>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <span className="text-[10px] font-bold text-slate-500">
            {copy.linkedPlan}: <strong className="text-slate-800 dark:text-slate-200">{planName}</strong>
          </span>
          <span className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[9px] font-black uppercase tracking-[0.16em] ${bot.is_active ? "border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-900/50 dark:bg-emerald-950/30 dark:text-emerald-300" : "border-amber-200 bg-amber-50 text-amber-700 dark:border-amber-900/50 dark:bg-amber-950/30 dark:text-amber-300"}`}>
            {bot.is_active ? <CheckCircle2 size={12} /> : <AlertTriangle size={12} />}
            {bot.is_active ? copy.active : copy.paused}
          </span>
        </div>
      </div>

      <div className="px-5 py-4">
        <div className="grid gap-2 md:grid-cols-[1fr_auto_1fr_auto_1fr] md:items-stretch">
          {chain.map((item, index) => {
            const Icon = item.icon;
            return (
              <div key={item.key} className="contents">
                <div className={`flex min-w-0 items-center gap-3 rounded-2xl border px-4 py-3 ${item.missing ? "border-dashed border-amber-200 bg-amber-50/50 dark:border-amber-900/50 dark:bg-amber-950/10" : "border-slate-200 bg-slate-50/70 dark:border-slate-800 dark:bg-slate-900/50"}`}>
                  <span className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-xl ${item.missing ? "bg-amber-100 text-amber-700 dark:bg-amber-950 dark:text-amber-300" : "bg-white text-blue-600 shadow-sm dark:bg-slate-950 dark:text-blue-300"}`}>
                    <Icon size={16} />
                  </span>
                  <div className="min-w-0">
                    <p className="text-[9px] font-black uppercase tracking-[0.18em] text-slate-400">{item.label}</p>
                    <p className={`mt-0.5 truncate text-xs font-black ${item.missing ? "text-amber-700 dark:text-amber-300" : "text-slate-900 dark:text-white"}`}>
                      {item.value}
                    </p>
                    {item.meta ? (
                      <p className="mt-0.5 truncate text-[10px] font-bold text-slate-400">{item.meta}</p>
                    ) : null}
                  </div>
                </div>
                {index < chain.length - 1 ? (
                  <span className="hidden items-center justify-center text-slate-300 md:flex">
                    <ArrowRight size={16} />
                  </span>
                ) : null}
              </div>
            );
          })}
        </div>

        {hasSetupMismatch ? (
          <div className="mt-3 flex items-start gap-2 rounded-xl border border-amber-200 bg-amber-50 px-3 py-2.5 text-amber-800 dark:border-amber-900/50 dark:bg-amber-950/20 dark:text-amber-200">
            <AlertTriangle className="mt-0.5 shrink-0" size={14} />
            <div>
              <p className="text-[10px] font-black uppercase tracking-[0.14em]">{copy.mismatchTitle}</p>
              <p className="mt-0.5 text-xs font-semibold">{copy.mismatchBody}</p>
            </div>
          </div>
        ) : null}

        <div className="mt-4 flex flex-col gap-2 border-t border-slate-100 pt-4 dark:border-slate-800 sm:flex-row sm:items-center">
          <p className="shrink-0 text-[9px] font-black uppercase tracking-[0.2em] text-slate-400">
            {copy.evidence}
          </p>
          <div className="grid flex-1 grid-cols-2 gap-2 sm:grid-cols-4">
            {scoreEntries.map(({ key, value }) => (
              <div key={key} className={`flex items-center justify-between rounded-xl border px-3 py-2 ${scoreTone(value)}`}>
                <span className="text-[9px] font-black uppercase tracking-[0.14em]">
                  {copy.scoreLabels?.[key] || key}
                </span>
                <span className="font-mono text-sm font-black">
                  {value === null ? "—" : Math.round(value)}
                </span>
              </div>
            ))}
          </div>
        </div>

        {!hasScores ? (
          <p className="mt-2 text-[10px] font-bold text-slate-400">{copy.empty}</p>
        ) : null}
      </div>
    </section>
  );
}
