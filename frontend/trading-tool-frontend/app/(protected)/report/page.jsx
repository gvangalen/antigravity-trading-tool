'use client';

import { useState, useEffect, useMemo, useRef } from 'react';
import {
  fetchDailyReportLatest,
  fetchDailyReportByDate,
  fetchDailyReportDates,
  generateDailyReport,
  fetchDailyReportPDF,
  fetchWeeklyReportLatest,
  fetchWeeklyReportByDate,
  fetchWeeklyReportDates,
  generateWeeklyReport,
  fetchWeeklyReportPDF,
  fetchMonthlyReportLatest,
  fetchMonthlyReportByDate,
  fetchMonthlyReportDates,
  generateMonthlyReport,
  fetchMonthlyReportPDF,
  fetchQuarterlyReportLatest,
  fetchQuarterlyReportByDate,
  fetchQuarterlyReportDates,
  generateQuarterlyReport,
  fetchQuarterlyReportPDF,
} from '@/lib/api/report';
import { assistantChat } from '@/lib/api/ai';

// Components
import ReportTabs from '@/components/report/ReportTabs';
import ReportContainer from '@/components/report/layout/ReportContainer';
import ReportLayout from '@/components/report/layout/ReportLayout';
import ReportTerminalHUD from '@/components/report/ReportTerminalHUD';
import { ReportSkeleton } from '@/components/dashboard/DashboardSkeleton';
import DashboardErrorBoundary from '@/components/ui/DashboardErrorBoundary';

import ReportGenerateOverlay from '@/components/ui/ReportGenerateOverlay';
import { useModal } from '@/components/modal/ModalProvider';
import { waitUntilVisible } from '@/hooks/useVisibilityPolling';

import {
  Download,
  RefreshCw,
  AlertTriangle,
  Loader2,
  Calendar,
  FileText,
  Brain,
  ShieldCheck,
  ClipboardList,
  ChevronDown,
  Activity,
  ShieldAlert,
  CheckCircle2,
} from 'lucide-react';

/* =====================================================
CONFIG
===================================================== */

const REPORT_TYPES = {
  daily: 'Daily',
  weekly: 'Weekly',
  monthly: 'Monthly',
  quarterly: 'Quarterly',
};

const AUTO_GENERATE_IF_EMPTY = true;
const POLL_INTERVAL_MS = 4000;
const POLL_MAX_ATTEMPTS = 60;

const FINN_REPORT_OPTIONS = [
  {
    key: 'today',
    label: 'Vandaag',
    eyebrow: 'Operator dagrapport',
    prompt: 'Geef mijn Finn rapport van vandaag',
    empty: 'Nog geen Finn-activiteit vandaag. Zodra Finn iets begeleidt, blokkeert of vastlegt, verschijnt het hier.',
  },
  {
    key: 'week',
    label: 'Weekreflectie',
    eyebrow: 'Discipline weekbeeld',
    prompt: 'Geef mijn weekreflectie',
    empty: 'Nog te weinig weekhistorie. Finn toont hier pas patronen wanneer er auditdata is.',
  },
  {
    key: 'blocked',
    label: 'Geblokkeerd',
    eyebrow: 'Risk-officer log',
    prompt: 'Wat heeft Finn vandaag geblokkeerd?',
    empty: 'Geen blokkades vandaag. Finn heeft nog geen risicovolle actie hoeven afremmen.',
  },
  {
    key: 'behavior',
    label: '30 dagen gedrag',
    eyebrow: 'Behavioral memory',
    prompt: 'Geef mijn gedragsrapport van de laatste 30 dagen',
    empty: 'Nog te weinig gedragsdata over 30 dagen. Finn verzint hier geen profiel zonder bewijs.',
  },
];

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

/* =====================================================
HELPERS
===================================================== */

function sortDatesDesc(list) {
  if (!Array.isArray(list)) return [];
  return [...list].sort((a, b) => (a < b ? 1 : -1));
}

function getReportSignature(report) {
  if (!report) return '';
  return (
    report.generated_at ||
    report.updated_at ||
    report.created_at ||
    JSON.stringify(report)
  );
}

function getNested(obj, path, fallback = null) {
  return path.split('.').reduce((acc, key) => acc?.[key], obj) ?? fallback;
}

function getFinnReportSummary(report) {
  const text = report?.response || '';
  if (!text) {
    return 'Finn analyseerde je recente interacties, risicochecks en beslisflows.';
  }

  const cleaned = text
    .replace(/^dit is een finn operator-\/disciplinerapport, los van je dagelijkse trading report\.\s*/i, '')
    .replace(/\s+/g, ' ')
    .trim();

  if (!cleaned) {
    return 'Finn analyseerde je recente interacties, risicochecks en beslisflows.';
  }

  return cleaned.length > 220 ? `${cleaned.slice(0, 220).trim()}...` : cleaned;
}

function formatFinnReportSource(report) {
  const source = getNested(report, 'state.source.primary') || getNested(report, 'state.analysis.source.primary');
  return source || 'Finn auditdata';
}

function finnAgentVerdictTone(verdict = {}) {
  const status = String(verdict.status || '').toLowerCase();
  const priority = String(verdict.priority || '').toLowerCase();
  if (priority === 'high' || status.includes('block') || status.includes('attention') || status.includes('intervened')) {
    return 'border-rose-200 dark:border-rose-900/50 bg-rose-50 dark:bg-rose-950/20 text-rose-700 dark:text-rose-300';
  }
  if (priority === 'medium' || status.includes('need') || status.includes('missing') || status.includes('review') || status.includes('waiting')) {
    return 'border-amber-200 dark:border-amber-900/50 bg-amber-50 dark:bg-amber-950/20 text-amber-700 dark:text-amber-300';
  }
  return 'border-emerald-200 dark:border-emerald-900/50 bg-emerald-50 dark:bg-emerald-950/20 text-emerald-700 dark:text-emerald-300';
}

function FinnAgentVerdicts({ verdicts = [] }) {
  const items = Array.isArray(verdicts) ? verdicts.filter(Boolean).slice(0, 6) : [];
  if (items.length === 0) return null;

  return (
    <div className="mt-5 rounded-2xl border border-slate-200 dark:border-slate-800 bg-white/80 dark:bg-slate-950/50 p-4">
      <div className="flex items-center justify-between gap-3 mb-3">
        <span className="inline-flex items-center gap-2 text-[10px] font-black uppercase tracking-[0.16em] text-slate-500 dark:text-slate-400">
          <Brain size={13} className="text-blue-600 dark:text-blue-400" />
          Agent Verdicts
        </span>
        <span className="text-[10px] font-black uppercase tracking-[0.16em] text-slate-400">
          {items.length}
        </span>
      </div>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
        {items.map((verdict, index) => (
          <div
            key={`${verdict.agent || verdict.label || 'agent'}-${index}`}
            className={`rounded-xl border p-3 ${finnAgentVerdictTone(verdict)}`}
          >
            <div className="flex items-center justify-between gap-3">
              <span className="text-[10px] font-black uppercase tracking-[0.14em] truncate">
                {verdict.label || verdict.agent || 'Agent'}
              </span>
              <span className="shrink-0 rounded-full bg-white/75 dark:bg-slate-950/40 px-2 py-1 text-[8px] font-black uppercase tracking-widest">
                {verdict.status || 'unknown'}
              </span>
            </div>
            <p className="mt-2 text-xs font-semibold leading-relaxed opacity-90">
              {verdict.reason || verdict.next_action || 'Geen toelichting beschikbaar.'}
            </p>
            {verdict.next_action && (
              <p className="mt-2 text-[9px] font-black uppercase tracking-[0.14em] opacity-75">
                {verdict.next_action}
              </p>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

function FinnAgentController({ controller }) {
  if (!controller?.dominant_agent) return null;
  const score = Number(controller.dominant_score || 0);
  const tone = score >= 90
    ? 'border-rose-200 dark:border-rose-900/50 bg-rose-50 dark:bg-rose-950/20 text-rose-700 dark:text-rose-300'
    : score >= 65
      ? 'border-amber-200 dark:border-amber-900/50 bg-amber-50 dark:bg-amber-950/20 text-amber-700 dark:text-amber-300'
      : 'border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-950/50 text-slate-600 dark:text-slate-300';

  return (
    <div className={`mt-5 rounded-2xl border p-4 ${tone}`}>
      <div className="flex items-center justify-between gap-3">
        <span className="inline-flex items-center gap-2 text-[10px] font-black uppercase tracking-[0.16em]">
          <Brain size={13} />
          Finn Controller
        </span>
        <span className="rounded-full bg-white/75 dark:bg-slate-950/40 px-3 py-1 text-[9px] font-black uppercase tracking-widest">
          {controller.dominant_label || controller.dominant_agent}
        </span>
      </div>
      <p className="mt-3 text-sm font-semibold leading-relaxed">
        {controller.reason || controller.next_action || 'Finn heeft de agent-verdicts gewogen.'}
      </p>
      {controller.next_action && (
        <p className="mt-2 text-[10px] font-black uppercase tracking-[0.14em] opacity-75">
          {controller.next_action}
        </p>
      )}
      {controller.primary_action?.prompt && (
        <div className="mt-3 inline-flex items-center gap-2 rounded-xl bg-white/75 dark:bg-slate-950/40 px-3 py-2 text-[10px] font-black uppercase tracking-[0.14em]">
          Primaire handoff: {controller.primary_action.label || controller.primary_action.prompt}
        </div>
      )}
      {controller.primary_item_id && (
        <p className="mt-2 text-[9px] font-black uppercase tracking-[0.14em] opacity-65">
          Accountability item: {controller.primary_item_id}
        </p>
      )}
    </div>
  );
}

function FinnPortfolioRisk({ portfolioRisk }) {
  if (!portfolioRisk?.status || portfolioRisk.status === 'balanced' || portfolioRisk.status === 'no_assets') {
    return null;
  }

  const ignoreToday = Array.isArray(portfolioRisk.ignore_today_assets) ? portfolioRisk.ignore_today_assets.slice(0, 3) : [];
  const liveHotspots = Array.isArray(portfolioRisk.live_bot_hotspots) ? portfolioRisk.live_bot_hotspots.slice(0, 3) : [];
  const rankedConflicts = Array.isArray(portfolioRisk.ranked_conflicts) ? portfolioRisk.ranked_conflicts.slice(0, 3) : [];

  if (ignoreToday.length === 0 && liveHotspots.length === 0 && rankedConflicts.length === 0) {
    return null;
  }

  const tone = portfolioRisk.status === 'high_attention'
    ? 'border-rose-200 dark:border-rose-900/50 bg-rose-50 dark:bg-rose-950/20 text-rose-700 dark:text-rose-300'
    : 'border-amber-200 dark:border-amber-900/50 bg-amber-50 dark:bg-amber-950/20 text-amber-700 dark:text-amber-300';

  return (
    <div className={`mt-5 rounded-2xl border p-4 ${tone}`}>
      <div className="flex items-center justify-between gap-3">
        <span className="inline-flex items-center gap-2 text-[10px] font-black uppercase tracking-[0.16em]">
          <ShieldCheck size={13} />
          Portfolio Risk
        </span>
        <span className="rounded-full bg-white/75 dark:bg-slate-950/40 px-3 py-1 text-[9px] font-black uppercase tracking-widest">
          {portfolioRisk.status}
        </span>
      </div>
      {portfolioRisk.message && (
        <p className="mt-3 text-sm font-semibold leading-relaxed">
          {portfolioRisk.message}
        </p>
      )}

      {ignoreToday.length > 0 && (
        <div className="mt-4">
          <div className="text-[10px] font-black uppercase tracking-[0.14em] opacity-75">
            Vandaag liever negeren
          </div>
          <div className="mt-2 grid grid-cols-1 md:grid-cols-2 gap-2">
            {ignoreToday.map((item) => (
              <div key={`ignore-${item.asset}`} className="rounded-xl border border-white/60 dark:border-slate-900/50 bg-white/70 dark:bg-slate-950/35 p-3">
                <div className="flex items-center justify-between gap-3">
                  <span className="text-[10px] font-black uppercase tracking-[0.14em]">{item.asset}</span>
                  <span className="text-[8px] font-black uppercase tracking-widest opacity-70">
                    score {item.risk_score}
                  </span>
                </div>
                <p className="mt-2 text-xs font-semibold leading-relaxed">{item.reason}</p>
              </div>
            ))}
          </div>
        </div>
      )}

      {liveHotspots.length > 0 && (
        <div className="mt-4">
          <div className="text-[10px] font-black uppercase tracking-[0.14em] opacity-75">
            Live bot-hotspots
          </div>
          <div className="mt-2 grid grid-cols-1 md:grid-cols-2 gap-2">
            {liveHotspots.map((item) => (
              <div key={`hotspot-${item.asset}`} className="rounded-xl border border-white/60 dark:border-slate-900/50 bg-white/70 dark:bg-slate-950/35 p-3">
                <div className="flex items-center justify-between gap-3">
                  <span className="text-[10px] font-black uppercase tracking-[0.14em]">{item.asset}</span>
                  <span className="text-[8px] font-black uppercase tracking-widest opacity-70">
                    {item.live_bot_count} live
                  </span>
                </div>
                <p className="mt-2 text-xs font-semibold leading-relaxed">{item.summary}</p>
              </div>
            ))}
          </div>
        </div>
      )}

      {rankedConflicts.length > 0 && (
        <div className="mt-4">
          <div className="text-[10px] font-black uppercase tracking-[0.14em] opacity-75">
            Topconflicten
          </div>
          <div className="mt-2 space-y-2">
            {rankedConflicts.map((item, index) => (
              <div key={`conflict-${item.asset || 'portfolio'}-${index}`} className="rounded-xl border border-white/60 dark:border-slate-900/50 bg-white/70 dark:bg-slate-950/35 p-3">
                <div className="flex items-center justify-between gap-3">
                  <span className="text-[10px] font-black uppercase tracking-[0.14em]">{item.asset || 'Portfolio'}</span>
                  <span className="text-[8px] font-black uppercase tracking-widest opacity-70">
                    {item.severity || item.risk_level || 'review'}
                  </span>
                </div>
                <p className="mt-2 text-xs font-semibold leading-relaxed">{item.reason}</p>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function FinnReflectionSectionCard({ icon: Icon, title, summary, entries = [], accent = 'slate', renderEntry }) {
  const tones = {
    slate: 'border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-950/50 text-slate-700 dark:text-slate-300',
    amber: 'border-amber-200 dark:border-amber-900/50 bg-amber-50/70 dark:bg-amber-950/20 text-amber-700 dark:text-amber-300',
    rose: 'border-rose-200 dark:border-rose-900/50 bg-rose-50/70 dark:bg-rose-950/20 text-rose-700 dark:text-rose-300',
    emerald: 'border-emerald-200 dark:border-emerald-900/50 bg-emerald-50/70 dark:bg-emerald-950/20 text-emerald-700 dark:text-emerald-300',
  };

  const tone = tones[accent] || tones.slate;
  if (!summary && (!Array.isArray(entries) || entries.length === 0)) return null;

  return (
    <div className={`rounded-2xl border p-4 ${tone}`}>
      <div className="flex items-center gap-2">
        <Icon size={14} />
        <span className="text-[10px] font-black uppercase tracking-[0.16em]">
          {title}
        </span>
      </div>
      {summary && (
        <p className="mt-3 text-sm font-semibold leading-relaxed">
          {summary}
        </p>
      )}
      {Array.isArray(entries) && entries.length > 0 && (
        <div className="mt-4 space-y-2">
          {entries.slice(0, 4).map((entry, index) => (
            <div
              key={`${title}-${entry.type || entry.label || index}`}
              className="rounded-xl border border-white/60 dark:border-slate-900/50 bg-white/70 dark:bg-slate-950/35 p-3"
            >
              {renderEntry ? renderEntry(entry, index) : (
                <>
                  <div className="flex items-center justify-between gap-3">
                    <span className="text-[10px] font-black uppercase tracking-[0.14em]">
                      {entry.label || entry.type || 'Item'}
                    </span>
                    {entry.asset && (
                      <span className="text-[8px] font-black uppercase tracking-widest opacity-70">
                        {entry.asset}
                      </span>
                    )}
                  </div>
                  {(entry.message || entry.outcome) && (
                    <p className="mt-2 text-xs font-semibold leading-relaxed">
                      {entry.message || entry.outcome}
                    </p>
                  )}
                </>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function FinnReflectionBlocks({ analysis }) {
  const sections = analysis?.sections || {};
  const dayClose = analysis?.day_close || {};

  const whatIDid = dayClose?.what_i_did_today || sections?.activity_journal || null;
  const whatFinnBlocked = dayClose?.what_finn_blocked || sections?.blocked_summary || null;
  const whereIDeviated = dayClose?.where_i_deviated || sections?.plan_adherence || null;

  if (!whatIDid && !whatFinnBlocked && !whereIDeviated) return null;

  return (
    <div className="mt-5 grid grid-cols-1 xl:grid-cols-3 gap-4">
      <FinnReflectionSectionCard
        icon={ClipboardList}
        title={whatIDid?.title || 'Wat heb ik gedaan?'}
        summary={whatIDid?.summary}
        entries={whatIDid?.entries || []}
        accent="slate"
        renderEntry={(entry) => (
          <>
            <div className="flex items-center justify-between gap-3">
              <span className="text-[10px] font-black uppercase tracking-[0.14em]">
                {entry.label || entry.type || 'Finn-actie'}
              </span>
              {entry.asset && (
                <span className="text-[8px] font-black uppercase tracking-widest opacity-70">
                  {entry.asset}
                </span>
              )}
            </div>
            <div className="mt-2 flex flex-wrap gap-2 text-[9px] font-black uppercase tracking-[0.12em] opacity-75">
              {entry.status && <span>{entry.status}</span>}
              {entry.resolve_state && <span>{entry.resolve_state}</span>}
            </div>
          </>
        )}
      />

      <FinnReflectionSectionCard
        icon={ShieldAlert}
        title={whatFinnBlocked?.title || 'Wat heeft Finn geblokkeerd?'}
        summary={whatFinnBlocked?.summary}
        entries={whatFinnBlocked?.entries || []}
        accent="rose"
        renderEntry={(entry) => (
          <>
            <div className="flex items-center justify-between gap-3">
              <span className="text-[10px] font-black uppercase tracking-[0.14em]">
                {entry.label || entry.type || 'Guardrail'}
              </span>
              <span className="text-[8px] font-black uppercase tracking-widest opacity-70">
                {entry.asset || entry.severity || 'review'}
              </span>
            </div>
            <p className="mt-2 text-xs font-semibold leading-relaxed">
              {entry.outcome || 'Geen extra toelichting.'}
            </p>
          </>
        )}
      />

      <FinnReflectionSectionCard
        icon={Activity}
        title={whereIDeviated?.title || 'Waar week ik af?'}
        summary={whereIDeviated?.summary}
        entries={whereIDeviated?.entries || []}
        accent={whereIDeviated?.status === 'steady' ? 'emerald' : whereIDeviated?.status === 'disciplined' ? 'amber' : 'amber'}
        renderEntry={(entry) => (
          <>
            <div className="flex items-center justify-between gap-3">
              <span className="text-[10px] font-black uppercase tracking-[0.14em]">
                {entry.label || entry.type || 'Afwijking'}
              </span>
              <span className="text-[8px] font-black uppercase tracking-widest opacity-70">
                {entry.asset || entry.severity || 'review'}
              </span>
            </div>
            <p className="mt-2 text-xs font-semibold leading-relaxed">
              {entry.message || 'Geen extra toelichting.'}
            </p>
          </>
        )}
      />

      {dayClose?.tomorrow_focus?.length > 0 && (
        <div className="xl:col-span-3 rounded-2xl border border-emerald-200 dark:border-emerald-900/50 bg-emerald-50/70 dark:bg-emerald-950/20 p-4 text-emerald-700 dark:text-emerald-300">
          <div className="flex items-center gap-2">
            <CheckCircle2 size={14} />
            <span className="text-[10px] font-black uppercase tracking-[0.16em]">
              Morgen meenemen
            </span>
          </div>
          <div className="mt-3 grid grid-cols-1 md:grid-cols-2 gap-2">
            {dayClose.tomorrow_focus.slice(0, 4).map((item) => (
              <div
                key={item}
                className="rounded-xl border border-white/60 dark:border-slate-900/50 bg-white/70 dark:bg-slate-950/35 p-3 text-xs font-semibold leading-relaxed"
              >
                {item}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function FinnBehavioralIntelligenceBlocks({ analysis }) {
  const profile = analysis?.behavioral_profile || null;
  const trend = analysis?.trend || analysis?.week_over_week || analysis?.month_over_month || null;
  const riskFlags = Array.isArray(analysis?.risk_flags) ? analysis.risk_flags : [];
  const habitCards = Array.isArray(analysis?.habit_cards) ? analysis.habit_cards : [];
  const memoryCards = Array.isArray(analysis?.memory_cards) ? analysis.memory_cards : [];
  const balanceScore = analysis?.behavioral_balance_score;

  if (!profile && !trend && riskFlags.length === 0 && habitCards.length === 0 && memoryCards.length === 0) {
    return null;
  }

  return (
    <div className="mt-5 space-y-4">
      <div className="rounded-2xl border border-violet-200 dark:border-violet-900/50 bg-violet-50/70 dark:bg-violet-950/20 p-4 text-violet-700 dark:text-violet-300">
        <div className="flex items-center gap-2">
          <Brain size={14} />
          <span className="text-[10px] font-black uppercase tracking-[0.16em]">
            Behavioral Intelligence 2.0+
          </span>
        </div>
        <p className="mt-2 text-sm font-semibold leading-relaxed">
          Finn laat hier je gedragsprofiel, meerweekse trend, remsignalen en werkstijl apart zien in plaats van alleen in prose.
        </p>
        <div className="mt-3 grid grid-cols-2 md:grid-cols-4 gap-2">
          {[
            ['Gedragsprofiel', profile?.label || 'Nog opbouwen'],
            ['Meerweekse trend', trend?.status || trend?.momentum || 'Nog opbouwen'],
            ['Waar Finn rem houdt', riskFlags[0]?.label || memoryCards[0]?.label || 'Geen extra rem nu'],
            ['Werkstijl die Finn herkent', habitCards[0]?.label || 'Nog opbouwen'],
          ].map(([label, value]) => (
            <div
              key={label}
              className="rounded-xl border border-white/60 dark:border-slate-900/50 bg-white/70 dark:bg-slate-950/35 p-3"
            >
              <div className="text-[9px] font-black uppercase tracking-[0.14em] opacity-80">
                {label}
              </div>
              <div className="mt-1 text-xs font-semibold leading-snug text-violet-900 dark:text-violet-100">
                {value}
              </div>
            </div>
          ))}
        </div>
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-3 gap-4">
        {profile && (
          <div className="rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-950/50 p-4">
            <div className="flex items-center justify-between gap-3">
              <span className="inline-flex items-center gap-2 text-[10px] font-black uppercase tracking-[0.16em] text-slate-500 dark:text-slate-400">
                <Brain size={13} className="text-blue-600 dark:text-blue-400" />
                Gedragsprofiel
              </span>
              {profile.confidence && (
                <span className="rounded-full bg-slate-50 dark:bg-slate-900 px-3 py-1 text-[9px] font-black uppercase tracking-widest text-slate-500 dark:text-slate-400 border border-slate-200 dark:border-slate-800">
                  {profile.confidence}
                </span>
              )}
            </div>
            <div className="mt-3 text-sm font-black text-slate-900 dark:text-slate-100">
              {profile.label}
            </div>
            <p className="mt-2 text-sm font-semibold leading-relaxed text-slate-700 dark:text-slate-300">
              {profile.summary}
            </p>
            {profile.watch_for && (
              <p className="mt-3 text-[11px] font-black uppercase tracking-[0.12em] text-slate-500 dark:text-slate-400">
                Let op: {profile.watch_for}
              </p>
            )}
          </div>
        )}

        {trend && (
          <div className="rounded-2xl border border-amber-200 dark:border-amber-900/50 bg-amber-50/70 dark:bg-amber-950/20 p-4 text-amber-700 dark:text-amber-300">
            <div className="flex items-center justify-between gap-3">
              <span className="inline-flex items-center gap-2 text-[10px] font-black uppercase tracking-[0.16em]">
                <Activity size={13} />
                Meerweekse trend
              </span>
              {(trend.status || trend.momentum) && (
                <span className="rounded-full bg-white/75 dark:bg-slate-950/40 px-3 py-1 text-[9px] font-black uppercase tracking-widest">
                  {trend.status || trend.momentum}
                </span>
              )}
            </div>
            <p className="mt-3 text-sm font-semibold leading-relaxed">
              {trend.summary}
            </p>
            {balanceScore !== undefined && balanceScore !== null && (
              <div className="mt-3 rounded-xl border border-white/60 dark:border-slate-900/50 bg-white/70 dark:bg-slate-950/35 p-3">
                <div className="text-[9px] font-black uppercase tracking-[0.14em] opacity-70">
                  Behavioral balance score
                </div>
                <div className="mt-1 text-lg font-black">
                  {balanceScore}/100
                </div>
              </div>
            )}
          </div>
        )}

        {(riskFlags.length > 0 || memoryCards.length > 0) && (
          <div className="rounded-2xl border border-rose-200 dark:border-rose-900/50 bg-rose-50/70 dark:bg-rose-950/20 p-4 text-rose-700 dark:text-rose-300">
            <div className="flex items-center gap-2 text-[10px] font-black uppercase tracking-[0.16em]">
              <ShieldAlert size={13} />
              Waar Finn rem houdt
            </div>
            <div className="mt-3 space-y-2">
              {(riskFlags.length > 0 ? riskFlags : memoryCards).slice(0, 3).map((item) => (
                <div
                  key={item.id || item.type || item.label}
                  className="rounded-xl border border-white/60 dark:border-slate-900/50 bg-white/70 dark:bg-slate-950/35 p-3"
                >
                  <div className="flex items-center justify-between gap-3">
                    <span className="text-[10px] font-black uppercase tracking-[0.14em]">
                      {item.label || item.type}
                    </span>
                    {(item.severity || item.confidence) && (
                      <span className="text-[8px] font-black uppercase tracking-widest opacity-70">
                        {item.severity || item.confidence}
                      </span>
                    )}
                  </div>
                  <p className="mt-2 text-xs font-semibold leading-relaxed">
                    {item.summary}
                  </p>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>

      {habitCards.length > 0 && (
        <div className="rounded-2xl border border-emerald-200 dark:border-emerald-900/50 bg-emerald-50/70 dark:bg-emerald-950/20 p-4 text-emerald-700 dark:text-emerald-300">
          <div className="flex items-center gap-2 text-[10px] font-black uppercase tracking-[0.16em]">
            <CheckCircle2 size={13} />
            Werkstijl die Finn herkent
          </div>
          <div className="mt-3 grid grid-cols-1 md:grid-cols-2 gap-3">
            {habitCards.slice(0, 4).map((card) => (
              <div
                key={card.id || card.label}
                className="rounded-xl border border-white/60 dark:border-slate-900/50 bg-white/70 dark:bg-slate-950/35 p-3"
              >
                <div className="flex items-center justify-between gap-3">
                  <span className="text-[10px] font-black uppercase tracking-[0.14em]">
                    {card.label}
                  </span>
                  {card.status && (
                    <span className="text-[8px] font-black uppercase tracking-widest opacity-70">
                      {card.status}
                    </span>
                  )}
                </div>
                <p className="mt-2 text-xs font-semibold leading-relaxed">
                  {card.summary}
                </p>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function FinnReportsPanel() {
  const [activeFinnReport, setActiveFinnReport] = useState(FINN_REPORT_OPTIONS[0].key);
  const [finnReportCache, setFinnReportCache] = useState({});
  const [finnReport, setFinnReport] = useState(null);
  const [finnLoading, setFinnLoading] = useState(true);
  const [finnError, setFinnError] = useState('');
  const [expanded, setExpanded] = useState(false);

  const activeOption = FINN_REPORT_OPTIONS.find((option) => option.key === activeFinnReport) || FINN_REPORT_OPTIONS[0];

  const loadFinnReport = async (option = activeOption, force = false) => {
    if (!force && finnReportCache[option.key]) {
      setFinnReport(finnReportCache[option.key]);
      setFinnError('');
      setFinnLoading(false);
      return;
    }

    setFinnLoading(true);
    setFinnError('');

    try {
      const data = await assistantChat(
        option.prompt,
        {
          page: '/report',
          page_type: 'Reports',
          report_family: 'finn_reports',
          finn_report_type: option.key,
        },
        []
      );
      setFinnReportCache((cache) => ({ ...cache, [option.key]: data || null }));
      setFinnReport(data || null);
      setExpanded(false);
    } catch (err) {
      console.error('Finn report load failed:', err);
      setFinnError('Finn rapport kon niet geladen worden.');
    } finally {
      setFinnLoading(false);
    }
  };

  useEffect(() => {
    loadFinnReport(activeOption);
  }, [activeFinnReport]);

  const analysis = finnReport?.state?.analysis || finnReport?.analysis || {};
  const portfolioRisk = analysis?.portfolio_risk || finnReport?.state?.portfolio_risk || null;
  const metrics = analysis?.metrics || {};
  const source = formatFinnReportSource(finnReport);
  const summary = getFinnReportSummary(finnReport);
  const reportType = finnReport?.state?.report_type || analysis?.report_type || 'finn_reflection_report';
  const separateFrom = finnReport?.state?.separate_from || analysis?.separate_from || 'daily_trading_report';
  const isFinnReport = finnReport?.intent === 'finn_report' && finnReport?.flow === 'finn_report';
  const isBehavioralMemory = finnReport?.intent === 'behavioral_memory' && finnReport?.flow === 'behavioral_memory';
  const isWeeklyReflection = finnReport?.intent === 'weekly_reflection' && finnReport?.flow === 'weekly_reflection';
  const isContractValid = (
    isFinnReport ||
    (activeOption.key === 'behavior' && isBehavioralMemory) ||
    (activeOption.key === 'week' && isWeeklyReflection)
  );

  const metricItems = [
    ['Acties', metrics.actions_today ?? metrics.actions_7d ?? metrics.actions_30d],
    ['Afgeremd', metrics.plan_deviation_events_today ?? metrics.plan_deviation_events_7d ?? metrics.plan_deviation_events_30d],
    ['Skips', metrics.skipped_today ?? metrics.skipped_7d ?? metrics.skipped_30d],
  ].filter(([, value]) => value !== undefined && value !== null);

  return (
    <section className="my-10 md:my-12">
      <div className="flex items-center gap-2 mb-4">
        <Brain size={14} className="text-blue-600 dark:text-blue-400" />
        <span className="text-[11px] font-black uppercase tracking-[0.28em] text-slate-400 dark:text-slate-500">
          Finn Reports
        </span>
      </div>

      <div className="rounded-[2rem] border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-950 shadow-xl shadow-blue-900/5 overflow-hidden">
        <div className="p-6 md:p-8 border-b border-slate-100 dark:border-slate-800/80">
          <div className="flex flex-col lg:flex-row lg:items-start lg:justify-between gap-5">
            <div className="max-w-3xl">
              <h2 className="text-2xl md:text-3xl font-black tracking-tight text-slate-950 dark:text-slate-100">
                Persoonlijke Finn rapportage
              </h2>
              <p className="mt-3 text-sm md:text-[15px] leading-relaxed text-slate-500 dark:text-slate-400 max-w-2xl">
                Read-only rapporten over je Finn-activiteit, risicochecks en beslisflows.
                Los van trading reports. Dit rapport analyseert je gebruik van Finn, niet de markt.
              </p>
            </div>

            <div className="flex flex-wrap gap-2">
              {['READ-ONLY', 'AUDITDATA', 'LOS VAN TRADING REPORTS'].map((label) => (
                <span
                  key={label}
                  className="px-3 py-1.5 rounded-full bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-800 text-[10px] font-black uppercase tracking-[0.16em] text-slate-500 dark:text-slate-400"
                >
                  {label}
                </span>
              ))}
            </div>
          </div>
        </div>

        <div className="p-6 md:p-8">
          <div className="mb-6 overflow-x-auto">
            <div className="inline-flex min-w-full sm:min-w-0 rounded-2xl border border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-900/50 p-1">
              {FINN_REPORT_OPTIONS.map((option) => {
                const active = option.key === activeFinnReport;
                return (
                  <button
                    key={option.key}
                    onClick={() => setActiveFinnReport(option.key)}
                    className={`flex-1 sm:flex-none px-4 py-3 rounded-xl text-[10px] font-black uppercase tracking-[0.16em] whitespace-nowrap transition-all ${
                      active
                        ? 'bg-white dark:bg-slate-950 text-blue-600 dark:text-blue-400 shadow-sm border border-slate-200 dark:border-slate-800'
                        : 'text-slate-500 dark:text-slate-400 hover:text-slate-900 dark:hover:text-slate-100'
                    }`}
                  >
                    {option.label}
                  </button>
                );
              })}
            </div>
          </div>

          {finnLoading ? (
            <div className="flex items-center gap-3 text-sm font-bold text-slate-500 dark:text-slate-400">
              <Loader2 size={16} className="animate-spin text-blue-600" />
              Finn rapport ophalen...
            </div>
          ) : finnError ? (
            <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 rounded-2xl border border-red-200 dark:border-red-900/40 bg-red-50 dark:bg-red-950/20 p-4">
              <div className="flex items-center gap-3 text-sm font-bold text-red-700 dark:text-red-300">
                <AlertTriangle size={16} />
                {finnError}
              </div>
              <button
                onClick={() => loadFinnReport(activeOption, true)}
                className="self-start sm:self-auto px-4 py-2 rounded-xl bg-white dark:bg-slate-950 border border-red-200 dark:border-red-900/40 text-[10px] font-black uppercase tracking-widest text-red-700 dark:text-red-300 hover:bg-red-100 dark:hover:bg-red-950/40 transition-colors"
              >
                Opnieuw
              </button>
            </div>
          ) : (
            <div className="rounded-2xl border border-slate-200 dark:border-slate-800 bg-slate-50/60 dark:bg-slate-900/40 p-5 md:p-6">
              <div className="flex flex-col xl:flex-row xl:items-start xl:justify-between gap-5">
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2 mb-3">
                    <span className="inline-flex items-center gap-1.5 text-[10px] font-black uppercase tracking-[0.18em] text-blue-600 dark:text-blue-400">
                      <ClipboardList size={13} />
                      {activeOption.eyebrow}
                    </span>
                    <span className="px-2.5 py-1 rounded-full bg-white dark:bg-slate-950 border border-slate-200 dark:border-slate-800 text-[9px] font-black uppercase tracking-[0.14em] text-slate-500 dark:text-slate-400">
                      Gebruikersactiviteit
                    </span>
                    <span className="px-2.5 py-1 rounded-full bg-emerald-50 dark:bg-emerald-950/30 border border-emerald-200 dark:border-emerald-900/40 text-[9px] font-black uppercase tracking-[0.14em] text-emerald-700 dark:text-emerald-300">
                      Auditdata
                    </span>
                  </div>

                  <p className="text-sm md:text-[15px] leading-relaxed text-slate-700 dark:text-slate-300 max-w-3xl">
                    {summary || activeOption.empty}
                  </p>

                  <div className="mt-5 grid grid-cols-1 sm:grid-cols-3 gap-3 max-w-2xl">
                    {(metricItems.length ? metricItems : [['Bron', source], ['Type', reportType], ['Scheiding', separateFrom]]).map(([label, value]) => (
                      <div
                        key={label}
                        className="rounded-xl bg-white dark:bg-slate-950 border border-slate-200 dark:border-slate-800 p-3"
                      >
                        <div className="text-[9px] font-black uppercase tracking-[0.16em] text-slate-400 dark:text-slate-500">
                          {label}
                        </div>
                        <div className="mt-1 text-sm font-black text-slate-900 dark:text-slate-100 truncate">
                          {String(value)}
                        </div>
                      </div>
                    ))}
                  </div>

                  <FinnAgentController controller={analysis?.agent_controller} />
                  <FinnPortfolioRisk portfolioRisk={portfolioRisk} />
                  <FinnBehavioralIntelligenceBlocks analysis={analysis} />
                  {analysis?.agent_accountability?.performance_light?.summary && (
                    <div className="mt-5 rounded-2xl border border-blue-200 dark:border-blue-900/50 bg-blue-50 dark:bg-blue-950/20 p-4 text-blue-700 dark:text-blue-300">
                      <div className="text-[10px] font-black uppercase tracking-[0.16em] mb-2">
                        Agent learning light
                      </div>
                      <p className="text-sm font-semibold leading-relaxed">
                        {analysis.agent_accountability.performance_light.summary}
                      </p>
                    </div>
                  )}
                  <FinnAgentVerdicts verdicts={analysis?.agent_verdicts || []} />
                  <FinnReflectionBlocks analysis={analysis} />
                </div>

                <div className="flex flex-col gap-2 sm:flex-row xl:flex-col xl:min-w-[180px]">
                  <button
                    onClick={() => setExpanded((value) => !value)}
                    className="inline-flex items-center justify-center gap-2 rounded-xl bg-slate-950 dark:bg-blue-600 px-5 py-3 text-[11px] font-black uppercase tracking-widest text-white hover:bg-blue-700 dark:hover:bg-blue-500 transition-all active:scale-[0.98]"
                  >
                    Lees Finn rapport
                    <ChevronDown
                      size={14}
                      className={`transition-transform ${expanded ? 'rotate-180' : ''}`}
                    />
                  </button>
                  <button
                    onClick={() => loadFinnReport(activeOption, true)}
                    className="inline-flex items-center justify-center gap-2 rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-950 px-5 py-3 text-[11px] font-black uppercase tracking-widest text-slate-600 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-900 transition-all active:scale-[0.98]"
                  >
                    <RefreshCw size={13} />
                    Vernieuw
                  </button>
                </div>
              </div>

              {expanded && (
                <div className="mt-6 border-t border-slate-200 dark:border-slate-800 pt-5">
                  <div className="flex flex-wrap items-center gap-2 mb-4">
                    <span className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-[10px] font-black uppercase tracking-[0.14em] border ${
                      isContractValid
                        ? 'bg-emerald-50 dark:bg-emerald-950/30 border-emerald-200 dark:border-emerald-900/40 text-emerald-700 dark:text-emerald-300'
                        : 'bg-amber-50 dark:bg-amber-950/30 border-amber-200 dark:border-amber-900/40 text-amber-700 dark:text-amber-300'
                    }`}>
                      <ShieldCheck size={12} />
                      {isContractValid ? 'Contract OK' : 'Contract controleren'}
                    </span>
                    <span className="text-[10px] font-black uppercase tracking-[0.16em] text-slate-400 dark:text-slate-500">
                      Bron: {source}
                    </span>
                  </div>
                  <div className="rounded-xl bg-white dark:bg-slate-950 border border-slate-200 dark:border-slate-800 p-4">
                    <p className="whitespace-pre-wrap text-sm leading-7 text-slate-700 dark:text-slate-300">
                      {finnReport?.response || 'Geen rapporttekst beschikbaar.'}
                    </p>
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </section>
  );
}

/* =====================================================
PAGE
==================================================== */

export default function ReportPage() {
  const { showSnackbar } = useModal();

  const [reportType, setReportType] = useState('daily');
  const [report, setReport] = useState(null);
  const [dates, setDates] = useState([]);
  const [selectedDate, setSelectedDate] = useState('latest');

  const [loading, setLoading] = useState(true);
  const [pdfLoading, setPdfLoading] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [generateInfo, setGenerateInfo] = useState('');
  const [error, setError] = useState('');

  const pollTokenRef = useRef(0);
  const lastSignatureRef = useRef('');

  const fallbackLabel = REPORT_TYPES[reportType] || 'Report';

  const reportFns = useMemo(
    () => ({
      daily: {
        getLatest: fetchDailyReportLatest,
        getByDate: fetchDailyReportByDate,
        getDates: fetchDailyReportDates,
        generate: generateDailyReport,
        pdf: fetchDailyReportPDF,
      },
      weekly: {
        getLatest: fetchWeeklyReportLatest,
        getByDate: fetchWeeklyReportByDate,
        getDates: fetchWeeklyReportDates,
        generate: generateWeeklyReport,
        pdf: fetchWeeklyReportPDF,
      },
      monthly: {
        getLatest: fetchMonthlyReportLatest,
        getByDate: fetchMonthlyReportByDate,
        getDates: fetchMonthlyReportDates,
        generate: generateMonthlyReport,
        pdf: fetchMonthlyReportPDF,
      },
      quarterly: {
        getLatest: fetchQuarterlyReportLatest,
        getByDate: fetchQuarterlyReportByDate,
        getDates: fetchQuarterlyReportDates,
        generate: generateQuarterlyReport,
        pdf: fetchQuarterlyReportPDF,
      },
    }),
    []
  );

  const current = reportFns[reportType];

  /* =====================================================
LOAD
===================================================== */

  const loadData = async (date = 'latest') => {
    setLoading(true);
    setError('');
    setSelectedDate(date);

    try {
      const rawDates = await current.getDates();
      setDates(sortDatesDesc(rawDates || []));

      const data =
        date === 'latest'
          ? await current.getLatest()
          : await current.getByDate(date);

      if (!data && AUTO_GENERATE_IF_EMPTY) {
        setLoading(false);
        handleGenerate(true, date);
        return;
      }

      setReport(data || null);
      lastSignatureRef.current = getReportSignature(data);
    } catch {
      setError('An error occurred while loading the report.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData('latest');
  }, [reportType]);

  /* =====================================================
GENERATE
===================================================== */

  const pollUntilNewReport = async (preferDate = 'latest') => {
    pollTokenRef.current += 1;
    const token = pollTokenRef.current;

    let attempts = 0;

    while (attempts < POLL_MAX_ATTEMPTS) {
      if (pollTokenRef.current !== token) return;

      await sleep(POLL_INTERVAL_MS);
      await waitUntilVisible();

      const data =
        preferDate === 'latest'
          ? await current.getLatest({ forceFresh: true })
          : await current.getByDate(preferDate, { forceFresh: true });

      const sig = getReportSignature(data);

      if (sig && sig !== lastSignatureRef.current) {
        lastSignatureRef.current = sig;
        setReport(data);
        return;
      }

      attempts++;
    }

    throw new Error('Polling timeout');
  };

  const handleGenerate = async (fromAuto = false, preferDate = 'latest') => {
    setGenerating(true);
    setLoading(true); // 🔥 Toon skeleton achter de overlay
    setGenerateInfo(
      fromAuto
        ? `No ${fallbackLabel.toLowerCase()} report found. Creating…`
        : `Generating new ${fallbackLabel.toLowerCase()} report…`
    );

    try {
      await current.generate();
      await pollUntilNewReport(preferDate);
      showSnackbar(`${fallbackLabel} report is ready`, 'success');
    } catch (err) {
      console.error(err);
      setError('Failed to generate report.');
    } finally {
      setGenerating(false);
      setLoading(false);
    }
  };

  /* =====================================================
🔥 PDF
===================================================== */

  const handleDownload = async () => {
    if (!report?.report_date) {
      showSnackbar('Report not yet loaded', 'warning');
      return;
    }

    try {
      setPdfLoading(true);

      const date =
        selectedDate === 'latest'
          ? report.report_date
          : selectedDate;

      await current.pdf(date);
      showSnackbar('Download started', 'success');

    } catch (err) {
      console.error(err);
      showSnackbar('Error downloading PDF', 'error');
    } finally {
      setPdfLoading(false);
    }
  };

  /* =====================================================
RENDER
===================================================== */

  return (
    <div className="page-container bg-white dark:bg-[#020617] transition-colors min-h-screen">
      {generating && <ReportGenerateOverlay text={generateInfo} />}

      {/* 🟢 STANDARD PAGE HEADER */}
      <header className="page-header border-l-4 border-blue-600 pl-8 mb-16">
        <div className="page-label text-[11px] font-black text-blue-600 dark:text-blue-500 uppercase tracking-[0.3em] mb-2 opacity-80 flex items-center gap-2">
           <FileText size={12} />
           Tradamind Intelligence
        </div>
        <h1 className="page-title text-5xl font-black text-slate-900 dark:text-slate-100 tracking-tight leading-none mb-4">Tradamind Reports</h1>
        <div className="flex flex-col sm:flex-row sm:items-center gap-3 sm:gap-4">
          <p className="page-subtitle text-[15px] font-medium text-slate-400 dark:text-slate-500 max-w-2xl leading-relaxed">
            Detailed analysis of trading discipline and results
          </p>
          <div className="hidden sm:block h-4 w-[1px] bg-slate-200 dark:bg-slate-800" />
          <div className="flex items-center gap-1.5">
            <div className="w-1.5 h-1.5 rounded-full bg-blue-500" />
            <span className="text-[10px] font-black text-blue-600 dark:text-blue-400 uppercase tracking-[0.15em] opacity-80">
              Generated by Tradamind AI
            </span>
          </div>
        </div>
      </header>

      {/* 📊 OVERVIEW HUD */}
      <DashboardErrorBoundary>
        <ReportTerminalHUD report={report} type={reportType} loading={loading} />
      </DashboardErrorBoundary>

      {/* 🕹️ CONTROLS */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 py-8">
          <ReportTabs selected={reportType} onChange={setReportType} />

          <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 p-1 rounded-xl shadow-sm flex items-center gap-2 transition-colors">
              <div className="flex items-center gap-2 px-3 py-1 border-r border-slate-100 dark:border-slate-800">
                  <Calendar size={13} className="text-slate-400 dark:text-slate-500" />
                  <select
                      value={selectedDate}
                      onChange={(e) => loadData(e.target.value)}
                      className="bg-transparent text-[11px] font-bold text-slate-600 dark:text-slate-400 focus:outline-none appearance-none"
                  >
                      <option value="latest">Recent</option>
                      {dates.map((d) => (
                          <option key={d} value={d}>{d}</option>
                      ))}
                  </select>
              </div>

              <div className="flex items-center gap-2 pr-1">
                  <button
                      onClick={handleDownload}
                      disabled={pdfLoading || !report}
                      className="flex items-center gap-2 px-3 py-1.5 hover:bg-slate-50 dark:hover:bg-slate-800 text-slate-500 dark:text-slate-400 hover:text-slate-900 dark:hover:text-white rounded-lg transition-all disabled:opacity-30"
                  >
                      {pdfLoading ? <Loader2 size={13} className="animate-spin" /> : <Download size={13} />}
                      <span className="text-[11px] font-black uppercase tracking-widest">PDF</span>
                  </button>

                  <button
                      onClick={() => handleGenerate(false, selectedDate)}
                      disabled={generating}
                      className="flex items-center gap-2 bg-blue-600 text-white px-4 py-2 rounded-lg hover:bg-blue-700 transition-all shadow-lg shadow-blue-600/10 active:scale-95 disabled:bg-slate-300"
                  >
                      <RefreshCw size={13} className={generating ? "animate-spin" : ""} />
                      <span className="text-[11px] font-black uppercase tracking-widest">New</span>
                  </button>
              </div>
          </div>
      </div>

      {/* ⚠️ ERROR MESSAGE */}
      {error && (
        <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-900/30 p-6 rounded-2xl flex items-center gap-4 text-red-700 dark:text-red-300 shadow-sm transition-colors">
           <AlertTriangle size={24} />
           <div>
               <div className="text-[11px] font-black uppercase tracking-widest">Error Message</div>
               <div className="text-sm font-medium">{error}</div>
           </div>
        </div>
      )}

      <DashboardErrorBoundary>
        <FinnReportsPanel />
      </DashboardErrorBoundary>

      {/* 📄 REPORT CONTENT */}
      {loading ? (
        <div className="pt-8">
          <ReportSkeleton />
        </div>
      ) : (
        report && (
          <div className="animate-fade-slide pb-24">
            <DashboardErrorBoundary>
              <ReportContainer>
                <ReportLayout report={report} />
              </ReportContainer>
            </DashboardErrorBoundary>
          </div>
        )
      )}
    </div>
  );
}
