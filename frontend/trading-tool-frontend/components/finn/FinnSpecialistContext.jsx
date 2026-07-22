"use client";

import { useEffect, useRef, useState } from "react";
import { AlertTriangle, CheckCircle2, Loader2, Sparkles } from "lucide-react";

import { useTranslation } from "@/app/providers/I18nProvider";
import { requestWorkspaceContext } from "@/lib/api/workspace";

const COPY = {
  nl: {
    finnLabel: "FINN ·",
    setup: "Setup-context",
    strategy: "Strategie-context",
    automation: "Automation-context",
    reflection: "Reflectie-context",
    ask: "Vraag FINN om context",
    loading: "FINN controleert de huidige feiten...",
    unavailable: "Extra AI-context is momenteel niet beschikbaar. De platformgegevens blijven leidend.",
    notFound: "Er is nog geen passende data om te verdiepen.",
    findings: "Bevindingen",
    risks: "Aandachtspunten",
    next: "Volgende stap",
    ready: "Basisgegevens compleet",
    incomplete: "Basisgegevens onvolledig",
    source: "Bron",
  },
  en: {
    finnLabel: "FINN ·",
    setup: "Setup context",
    strategy: "Strategy context",
    automation: "Automation context",
    reflection: "Reflection context",
    ask: "Ask FINN for context",
    loading: "FINN is checking the current facts...",
    unavailable: "Additional AI context is currently unavailable. Platform data remains authoritative.",
    notFound: "There is no matching data to review yet.",
    findings: "Findings",
    risks: "Watchouts",
    next: "Next step",
    ready: "Base data complete",
    incomplete: "Base data incomplete",
    source: "Source",
  },
  de: {
    finnLabel: "FINN ·",
    setup: "Setup-Kontext",
    strategy: "Strategie-Kontext",
    automation: "Automationskontext",
    reflection: "Reflexionskontext",
    ask: "FINN nach Kontext fragen",
    loading: "FINN prüft die aktuellen Fakten...",
    unavailable: "Zusätzlicher KI-Kontext ist derzeit nicht verfügbar. Die Plattformdaten bleiben maßgeblich.",
    notFound: "Es sind noch keine passenden Daten zur Vertiefung vorhanden.",
    findings: "Erkenntnisse",
    risks: "Hinweise",
    next: "Nächster Schritt",
    ready: "Basisdaten vollständig",
    incomplete: "Basisdaten unvollständig",
    source: "Quelle",
  },
};

export default function FinnSpecialistContext({
  subjectType,
  subjectId = null,
  symbol = "BTC",
  timeframe = "1D",
  period = "day",
  compact = false,
}) {
  const { locale } = useTranslation();
  const copy = COPY[String(locale || "nl").slice(0, 2)] || COPY.nl;
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const requestVersion = useRef(0);

  useEffect(() => {
    requestVersion.current += 1;
    setResult(null);
    setLoading(false);
  }, [subjectType, subjectId, symbol, timeframe, period, locale]);

  const requestContext = async () => {
    if (loading) return;
    const version = ++requestVersion.current;
    setLoading(true);
    try {
      const response = await requestWorkspaceContext({
        subject_type: subjectType,
        subject_id: subjectId || undefined,
        symbol,
        timeframe,
        period,
        locale,
      });
      if (requestVersion.current === version) setResult(response);
    } catch (error) {
      const detail = error?.data?.detail || error?.detail || null;
      if (requestVersion.current === version) setResult(detail || { status: "not_found" });
    } finally {
      if (requestVersion.current === version) setLoading(false);
    }
  };

  const detail = result?.detail;
  const context = result?.context;
  const ready = detail?.readiness?.ready;

  return (
    <section className={`rounded-2xl border border-blue-100 bg-[linear-gradient(110deg,#eff6ff_0%,#ffffff_70%)] dark:border-blue-950 dark:bg-[linear-gradient(110deg,#0b1b35_0%,#0f172a_70%)] ${compact ? "p-4" : "p-5"}`}>
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-start gap-3">
          <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-blue-600 text-white"><Sparkles size={16} /></span>
          <div>
            <div className="text-[10px] font-black uppercase tracking-[0.22em] text-blue-600 dark:text-blue-300">{copy.finnLabel} {copy[subjectType]}</div>
            {detail ? (
              <div className="mt-1 flex flex-wrap items-center gap-2 text-xs font-bold text-slate-500 dark:text-slate-400">
                <span className={ready ? "text-emerald-600 dark:text-emerald-400" : "text-amber-600 dark:text-amber-400"}>{ready ? copy.ready : copy.incomplete}</span>
                <span>·</span><span>{copy.source}: {detail.source}</span>
              </div>
            ) : null}
          </div>
        </div>
        <button type="button" onClick={requestContext} disabled={loading} className="inline-flex min-h-10 items-center justify-center gap-2 rounded-xl bg-blue-600 px-4 text-xs font-black text-white transition hover:bg-blue-700 disabled:opacity-60">
          {loading ? <Loader2 size={15} className="animate-spin" /> : <Sparkles size={15} />}
          {loading ? copy.loading : copy.ask}
        </button>
      </div>

      {result?.status === "available" && context ? (
        <div className="mt-4 grid gap-3 border-t border-blue-100 pt-4 text-sm text-slate-600 dark:border-blue-950 dark:text-slate-300 lg:grid-cols-3">
          <div className="lg:col-span-3 font-semibold text-slate-900 dark:text-white">{context.summary}</div>
          <ContextList title={copy.findings} items={context.findings} />
          <ContextList title={copy.risks} items={context.risks} warning />
          <div><strong className="mb-1 block text-slate-950 dark:text-white">{copy.next}</strong>{context.next_step}</div>
        </div>
      ) : null}

      {result?.status === "unavailable" ? (
        <div className="mt-4 flex items-start gap-2 border-t border-blue-100 pt-4 text-xs font-semibold text-slate-500 dark:border-blue-950 dark:text-slate-400">
          <AlertTriangle size={15} className="mt-0.5 shrink-0 text-amber-500" /> {copy.unavailable}
        </div>
      ) : null}

      {result?.status === "not_found" ? (
        <div className="mt-4 flex items-center gap-2 border-t border-blue-100 pt-4 text-xs font-semibold text-slate-500 dark:border-blue-950 dark:text-slate-400">
          <CheckCircle2 size={15} /> {copy.notFound}
        </div>
      ) : null}
    </section>
  );
}

function ContextList({ title, items = [], warning = false }) {
  return (
    <div>
      <strong className="mb-1 block text-slate-950 dark:text-white">{title}</strong>
      {items.length ? items.map((item) => <div key={item} className={warning ? "text-amber-700 dark:text-amber-300" : ""}>• {item}</div>) : <span>–</span>}
    </div>
  );
}
