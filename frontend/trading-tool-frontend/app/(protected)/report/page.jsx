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
import { actionButtonStyles } from '@/components/ui/actionButtonStyles';
import { trackAssistantEvent } from '@/lib/api/assistantAnalytics';
import { useTranslation } from '@/app/providers/I18nProvider';
import { useAsset } from '@/app/providers/AssetProvider';
import { formatDateTime, getIntlLocale, getLocaleValue, normalizeLocale } from '@/lib/i18n';
import {
  FALLBACK_FINN_REPORT_OPTIONS,
  resolveActiveFinnReportOption,
  resolveFinnReportOptions,
} from '@/lib/report/finnReportOptions.mjs';

import {
  Download,
  RefreshCw,
  AlertTriangle,
  Loader2,
  Calendar,
  FileText,
  Brain,
  ShieldCheck,
  Shield,
  ClipboardList,
  ChevronDown,
  ChevronRight,
  Activity,
  ShieldAlert,
  CheckCircle2,
  Target,
  Bot,
  Terminal,
  BarChart3,
} from 'lucide-react';

/* =====================================================
CONFIG
===================================================== */

const REPORT_TYPE_KEYS = ['daily', 'weekly', 'monthly', 'quarterly'];
const AUTO_GENERATE_IF_EMPTY = true;
const POLL_INTERVAL_MS = 4000;
const POLL_MAX_ATTEMPTS = 60;

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

const BEHAVIOR_FLAG_LABELS = {
  fomo: 'FOMO',
  overtrades: 'Overtrading',
  leverage_seeking: 'Leverage-neiging',
  holds_losers_too_long: 'Verliezers te lang laten lopen',
  takes_profit_too_early: 'Winst te vroeg nemen',
};

function replaceVars(template, vars = {}) {
  return Object.entries(vars).reduce(
    (result, [key, value]) => result.replaceAll(`{${key}}`, String(value ?? '')),
    template
  );
}

/* =====================================================
HELPERS
===================================================== */

function sortDatesDesc(list) {
  if (!Array.isArray(list)) return [];
  return [...list].sort((a, b) => (a < b ? 1 : -1));
}

function humanizeBehaviorFlagLabel(flag, fallbackLabel = '') {
  return fallbackLabel || BEHAVIOR_FLAG_LABELS[String(flag || '').trim()] || String(flag || '').replaceAll('_', ' ');
}

function pickPrimaryProfileHabitAlignment(source = null) {
  if (!source || typeof source !== 'object') return null;
  return (
    source?.profile_habit_alignment?.primary_alignment ||
    source?.priority_engine?.profile_habit_alignment?.primary_alignment ||
    source?.portfolio_operating_system?.governance_layer?.profile_habit_alignment?.primary_alignment ||
    null
  );
}

function humanizeBehavioralPriorityBadge(item = {}) {
  const bias = String(item?.behavioral_priority_bias || '').toLowerCase();
  if (bias === 'up') return 'extra reviewgewicht';
  if (bias === 'down') return 'impuls geremd';
  return '';
}

function behavioralPriorityBadgeTone(item = {}) {
  const bias = String(item?.behavioral_priority_bias || '').toLowerCase();
  if (bias === 'up') return 'border-amber-200 bg-amber-100 text-amber-700 dark:border-amber-900/50 dark:bg-amber-950/30 dark:text-amber-300';
  if (bias === 'down') return 'border-rose-200 bg-rose-100 text-rose-700 dark:border-rose-900/50 dark:bg-rose-950/30 dark:text-rose-300';
  return 'border-slate-200 bg-slate-100 text-slate-600 dark:border-slate-800 dark:bg-slate-900 dark:text-slate-300';
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

function mergeBehavioralAnalysis(...sources) {
  return sources.reduce((merged, source) => {
    if (!source || typeof source !== 'object') return merged;
    return {
      ...merged,
      ...source,
      behavioral_profile: source.behavioral_profile || merged.behavioral_profile || null,
      trend: source.trend || merged.trend || null,
      week_over_week: source.week_over_week || merged.week_over_week || null,
      month_over_month: source.month_over_month || merged.month_over_month || null,
      risk_flags: Array.isArray(source.risk_flags) && source.risk_flags.length ? source.risk_flags : (merged.risk_flags || []),
      habit_cards: Array.isArray(source.habit_cards) && source.habit_cards.length ? source.habit_cards : (merged.habit_cards || []),
      memory_cards: Array.isArray(source.memory_cards) && source.memory_cards.length ? source.memory_cards : (merged.memory_cards || []),
      behavioral_balance_score:
        source.behavioral_balance_score !== undefined && source.behavioral_balance_score !== null
          ? source.behavioral_balance_score
          : merged.behavioral_balance_score,
    };
  }, {});
}

function getFinnReportSummary(report, fallbackText) {
  const locale = normalizeLocale(report?.locale) || 'nl';
  const text = report?.response || '';
  if (!text) {
    return fallbackText;
  }

  const cleaned = text
    .replace(/^dit is een finn operator-\/disciplinerapport, los van je dagelijkse trading report\.\s*/i, '')
    .replace(/\s+/g, ' ')
    .trim();

  if (!cleaned) {
    return fallbackText;
  }

  return cleaned.length > 220 ? `${cleaned.slice(0, 220).trim()}...` : cleaned;
}

function formatFinnReportSource(report, fallbackText) {
  const source = getNested(report, 'state.source.primary') || getNested(report, 'state.analysis.source.primary');
  return source || fallbackText;
}

function formatFinnReportTimestamp(report, fallbackText) {
  const locale = normalizeLocale(report?.locale) || 'nl';
  const raw =
    getNested(report, 'state.generated_at') ||
    getNested(report, 'state.updated_at') ||
    report?.generated_at ||
    report?.updated_at ||
    null;

  if (!raw) {
    return fallbackText;
  }

  const parsed = new Date(raw);
  if (Number.isNaN(parsed.getTime())) return String(raw);

  return formatDateTime(parsed, locale, {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

function pluralSuffix(count, singular = '', plural = 's') {
  return Number(count) === 1 ? singular : plural;
}

function buildFinnDigestCopy(digestT = {}) {
  const fallback = {
    reportTitle: 'Daily reflection with Finn',
    headlineDefault: 'Finn found no clear plan violations in this period.',
    headlineCautious: 'Finn saw only a limited amount of evidence in this period.',
    headlineLimited: 'There is not enough real activity yet for a firm reflection.',
    headlineOpen: 'Finn saw no clear plan violations, but {count} open decision{s} still need follow-up.',
    headlineBlocked: 'Finn flagged {count} moment{s} that need review before you continue.',
    headlineDeviation: 'Finn saw signs that your process drifted away from your plan.',
    reviewed: 'Reviewed',
    blocked: 'Blocked',
    open: 'Open',
    good: 'What went well',
    attention: 'What needs attention',
    next: 'Next step',
    detailsHint: 'Open the underlying activity only when you want the evidence behind this reflection.',
    detailButton: 'View activity and evidence',
    detailButtonClose: 'Hide activity and evidence',
    primaryActionDefault: 'View reflection details',
    primaryActionOpen: 'View {count} open decision{s}',
    primaryActionBlocked: 'Review {count} blocked moment{s}',
    nextOpen: 'Review the open queue and close the highest-priority decision first.',
    nextBlocked: 'Review the blocked moments first before starting any new decision.',
    activityTitle: 'What happened today?',
    activitySummaryReviewed: '{reviewed} decision{s} were reviewed. {open} remain open.',
    activitySummaryOpen: '{open} decision{s} are still open and waiting for follow-up.',
    blockedSummaryActive: 'Finn stopped {count} moment{s} before you continued.',
    blockedSummaryQuiet: 'Finn did not have to stop you today.',
    deviationSummaryActive: 'Review the blocked moments first to see where your process drifted.',
    deviationSummaryQuiet: 'No clear plan deviations were found in this period.',
    goodDefault: 'No clear plan deviations or impulsive execution signals were found.',
    goodReviewed: 'You slowed down enough to review decisions before moving on.',
    goodKeepCloser: 'No hard break was needed, but your process still stayed reasonably controlled.',
    goodLimited: 'The available evidence is still too limited for a stronger positive conclusion.',
    attentionDefault: 'There is not enough strong evidence yet to make a heavier coaching claim.',
    attentionLimited: 'Keep logging decisions clearly so Finn can judge patterns with more confidence.',
    attentionDeviation: 'A few signals suggest your process may have drifted away from plan-first execution.',
    nextDefault: 'Review open items first before starting a new decision flow.',
    nextLimited: 'Keep decisions explicit and let the next few actions build a clearer reflection.',
    nextDeviation: 'Review the moments where your process drifted and tighten the next decision flow.',
    openAttention: '{count} open item{s} still need to be rounded off first.',
    blockedAttention: '{count} guarded moment{s} need follow-up before you continue.',
    metricsHint: 'Today',
  };
  const text = (key) => digestT?.[key] || fallback[key];

  return {
    reportTitle: text('reportTitle'),
    headlineDefault: text('headlineDefault'),
    headlineCautious: text('headlineCautious'),
    headlineLimited: text('headlineLimited'),
    headlineOpen: (count) => replaceVars(text('headlineOpen'), { count, s: pluralSuffix(count), en: pluralSuffix(count, '', 'en'), e: pluralSuffix(count, '', 'e') }),
    headlineBlocked: (count) => replaceVars(text('headlineBlocked'), { count, s: pluralSuffix(count), en: pluralSuffix(count, '', 'en'), e: pluralSuffix(count, '', 'e') }),
    headlineDeviation: text('headlineDeviation'),
    reviewed: text('reviewed'),
    blocked: text('blocked'),
    open: text('open'),
    good: text('good'),
    attention: text('attention'),
    next: text('next'),
    detailsHint: text('detailsHint'),
    detailButton: text('detailButton'),
    detailButtonClose: text('detailButtonClose'),
    primaryActionDefault: text('primaryActionDefault'),
    primaryActionOpen: (count) => replaceVars(text('primaryActionOpen'), { count, s: pluralSuffix(count), en: pluralSuffix(count, '', 'en'), e: pluralSuffix(count, '', 'e') }),
    primaryActionBlocked: (count) => replaceVars(text('primaryActionBlocked'), { count, s: pluralSuffix(count), en: pluralSuffix(count, '', 'en'), e: pluralSuffix(count, '', 'e') }),
    nextOpen: text('nextOpen'),
    nextBlocked: text('nextBlocked'),
    activityTitle: text('activityTitle'),
    activitySummary: (reviewed, open) => (
      reviewed > 0
        ? replaceVars(text('activitySummaryReviewed'), { reviewed, open, s: pluralSuffix(reviewed), en: pluralSuffix(reviewed, '', 'en'), e: pluralSuffix(reviewed, '', 'e') })
        : replaceVars(text('activitySummaryOpen'), { open, s: pluralSuffix(open), en: pluralSuffix(open, '', 'en'), e: pluralSuffix(open, '', 'e') })
    ),
    blockedSummary: (count) => (
      count > 0
        ? replaceVars(text('blockedSummaryActive'), { count, s: pluralSuffix(count), en: pluralSuffix(count, '', 'en'), e: pluralSuffix(count, '', 'e') })
        : text('blockedSummaryQuiet')
    ),
    deviationSummary: (count) => (count > 0 ? text('deviationSummaryActive') : text('deviationSummaryQuiet')),
    goodDefault: text('goodDefault'),
    goodReviewed: text('goodReviewed'),
    goodKeepCloser: text('goodKeepCloser'),
    goodLimited: text('goodLimited'),
    attentionDefault: text('attentionDefault'),
    attentionLimited: text('attentionLimited'),
    attentionDeviation: text('attentionDeviation'),
    nextDefault: text('nextDefault'),
    nextLimited: text('nextLimited'),
    nextDeviation: text('nextDeviation'),
    openAttention: (count) => replaceVars(text('openAttention'), { count, s: pluralSuffix(count), en: pluralSuffix(count, '', 'en'), e: pluralSuffix(count, '', 'e') }),
    blockedAttention: (count) => replaceVars(text('blockedAttention'), { count, s: pluralSuffix(count), en: pluralSuffix(count, '', 'en'), e: pluralSuffix(count, '', 'e') }),
    metricsHint: text('metricsHint'),
  };
}

function buildFinnReflectionSummary({
  digest,
  activityEntries = [],
  blockedEntries = [],
  deviationEntries = [],
  reviewedCount = 0,
  blockedCount = 0,
  openActionCount = 0,
}) {
  const concreteReviewed = activityEntries.length;
  const concreteBlocked = blockedEntries.length;
  const concreteDeviation = deviationEntries.length;
  const concreteOpen = activityEntries.filter((entry) => {
    const haystack = [entry?.status, entry?.resolve_state, entry?.label, entry?.type]
      .filter(Boolean)
      .join(' ')
      .toLowerCase();
    return ['pending', 'open', 'later', 'snooz', 'skip'].some((pattern) => haystack.includes(pattern));
  }).length;

  const evidenceCount = concreteReviewed + concreteBlocked + concreteDeviation;
  const hasThinEvidence = evidenceCount <= 1;
  const hasStrongBlockedEvidence = concreteBlocked > 0 || blockedCount >= 2;
  const hasStrongOpenEvidence = concreteOpen > 0 || openActionCount >= 2;
  const hasClearDeviationEvidence = concreteDeviation > 0;

  if (evidenceCount === 0 && openActionCount === 0 && blockedCount === 0) {
    return {
      headline: digest.headlineLimited,
      good: digest.goodLimited,
      attention: digest.attentionLimited,
      next: digest.nextLimited,
      primaryAction: digest.primaryActionDefault,
    };
  }

  if (hasStrongBlockedEvidence) {
    const blockedTotal = Math.max(blockedCount, concreteBlocked);
    return {
      headline: digest.headlineBlocked(blockedTotal),
      good: reviewedCount > 0 ? digest.goodReviewed : digest.goodLimited,
      attention: digest.blockedAttention(blockedTotal),
      next: digest.nextBlocked,
      primaryAction: digest.primaryActionBlocked(blockedTotal),
    };
  }

  if (hasStrongOpenEvidence) {
    return {
      headline: digest.headlineOpen(openActionCount),
      good: hasClearDeviationEvidence ? digest.goodKeepCloser : digest.goodDefault,
      attention: digest.openAttention(openActionCount),
      next: digest.nextOpen,
      primaryAction: digest.primaryActionOpen(openActionCount),
    };
  }

  if (hasClearDeviationEvidence) {
    return {
      headline: digest.headlineDeviation,
      good: reviewedCount > 0 ? digest.goodReviewed : digest.goodKeepCloser,
      attention: digest.attentionDeviation,
      next: digest.nextDeviation,
      primaryAction: digest.primaryActionDefault,
    };
  }

  if (hasThinEvidence) {
    return {
      headline: digest.headlineCautious,
      good: reviewedCount > 0 ? digest.goodReviewed : digest.goodLimited,
      attention: digest.attentionLimited,
      next: digest.nextLimited,
      primaryAction: digest.primaryActionDefault,
    };
  }

  return {
    headline: digest.headlineDefault,
    good: reviewedCount > 0 ? digest.goodReviewed : digest.goodDefault,
    attention: digest.attentionDefault,
    next: digest.nextDefault,
    primaryAction: digest.primaryActionDefault,
  };
}

function countMatchingEntries(entries = [], patterns = []) {
  if (!Array.isArray(entries) || entries.length === 0) return 0;
  const normalizedPatterns = patterns.map((pattern) => String(pattern).toLowerCase());
  return entries.filter((entry) => {
    const haystack = [
      entry?.status,
      entry?.resolve_state,
      entry?.label,
      entry?.type,
      entry?.message,
      entry?.outcome,
    ]
      .filter(Boolean)
      .join(' ')
      .toLowerCase();
    return normalizedPatterns.some((pattern) => haystack.includes(pattern));
  }).length;
}

function getFirstNonEmptyText(...values) {
  return values.find((value) => typeof value === 'string' && value.trim()) || '';
}

function normalizeReportNarrative(value) {
  if (value === null || value === undefined) return '';
  if (typeof value === 'string') return value.trim();
  if (Array.isArray(value)) {
    return value.map((item) => normalizeReportNarrative(item)).filter(Boolean).join(' ');
  }
  if (typeof value === 'object') {
    return normalizeReportNarrative(
      value.text ?? value.summary ?? value.description ?? value.content ?? ''
    );
  }
  return String(value).trim();
}

function getTradingReportSummary(report, fallbackText) {
  const text = getFirstNonEmptyText(
    normalizeReportNarrative(report?.executive_summary),
    normalizeReportNarrative(report?.market_overview),
    normalizeReportNarrative(report?.outlook),
    fallbackText
  );

  const cleaned = String(text || '')
    .replace(/\s+/g, ' ')
    .trim();

  return cleaned.length > 190 ? `${cleaned.slice(0, 190).trim()}...` : cleaned;
}

function getTradingReportPanelCopy(locale = 'nl') {
  const normalized = String(locale || 'nl').toLowerCase();
  if (normalized.startsWith('en')) {
    return {
      eyebrow: 'Trading report',
      sectionTitle: 'Trading Report',
      collapsedCta: 'View full trading report',
      expandedCta: 'Hide full trading report',
      summaryFallback: 'Open the full trading report for the latest market context and setup guidance.',
      statusReady: 'Ready',
    };
  }
  if (normalized.startsWith('de')) {
    return {
      eyebrow: 'Trading-Bericht',
      sectionTitle: 'Trading-Bericht',
      collapsedCta: 'Vollständigen Trading-Bericht ansehen',
      expandedCta: 'Vollständigen Trading-Bericht ausblenden',
      summaryFallback: 'Öffne den vollständigen Trading-Bericht für den aktuellen Marktkontext und Setup-Hinweise.',
      statusReady: 'Bereit',
    };
  }
  return {
    eyebrow: 'Tradingrapport',
    sectionTitle: 'Tradingrapport',
    collapsedCta: 'Bekijk volledig tradingrapport',
    expandedCta: 'Verberg volledig tradingrapport',
    summaryFallback: 'Open het volledige tradingrapport voor de laatste marktcontext en setup-richting.',
    statusReady: 'Klaar',
  };
}

function normalizeFinnEntryKey(entry = {}) {
  return [
    entry?.label,
    entry?.type,
    entry?.status,
    entry?.resolve_state,
    entry?.asset,
  ]
    .filter(Boolean)
    .join('|')
    .toLowerCase();
}

function dedupeFinnEntries(entries = []) {
  const seen = new Set();
  return (Array.isArray(entries) ? entries : []).filter((entry) => {
    const key = normalizeFinnEntryKey(entry);
    if (!key || seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

function isGenericFinnEntry(entry = {}) {
  const haystack = [
    entry?.label,
    entry?.type,
    entry?.message,
    entry?.outcome,
    entry?.status,
    entry?.resolve_state,
  ]
    .filter(Boolean)
    .join(' ')
    .toLowerCase();

  return [
    'mission control item',
    'ai_pending_actions',
    'contract ok',
    'pending resolved',
    'status updated',
    'status gewijzigd',
    'agent handoff',
    'handoff',
    'timestamp',
    'refreshed',
    'refresh',
    'sync',
    'gesynchroniseerd',
    'item bijgewerkt',
    'item updated',
  ].some((pattern) => haystack.includes(pattern));
}

function cleanFinnEntries(entries = []) {
  return dedupeFinnEntries(entries).filter((entry) => !isGenericFinnEntry(entry));
}

function getFinnEntryHaystack(entry = {}) {
  return [
    entry?.status,
    entry?.resolve_state,
    entry?.label,
    entry?.type,
    entry?.message,
    entry?.outcome,
    entry?.severity,
  ]
    .filter(Boolean)
    .join(' ')
    .toLowerCase();
}

function isMeaningfulReviewedEntry(entry = {}) {
  const haystack = getFinnEntryHaystack(entry);
  const hasReviewSignal = ['review', 'reviewed', 'resolved', 'completed', 'confirmed', 'approved', 'closed'].some((pattern) => haystack.includes(pattern));
  const hasOpenSignal = ['pending', 'open', 'later', 'snooz', 'skip', 'waiting'].some((pattern) => haystack.includes(pattern));
  return hasReviewSignal && !hasOpenSignal;
}

function isMeaningfulOpenEntry(entry = {}) {
  const haystack = getFinnEntryHaystack(entry);
  const hasOpenSignal = ['pending', 'open', 'later', 'snooz', 'waiting', 'needs review', 'needs input', 'confirm'].some((pattern) => haystack.includes(pattern));
  const isResolved = ['resolved', 'completed', 'closed', 'approved', 'confirmed'].some((pattern) => haystack.includes(pattern));
  return hasOpenSignal && !isResolved;
}

function isMeaningfulBlockedEntry(entry = {}) {
  const haystack = getFinnEntryHaystack(entry);
  return ['blocked', 'guardrail', 'intervened', 'stopped', 'denied', 'prevented', 'risk'].some((pattern) => haystack.includes(pattern));
}

function isMeaningfulDeviationEntry(entry = {}) {
  const haystack = getFinnEntryHaystack(entry);
  return ['deviation', 'override', 'breach', 'violat', 'adherence'].some((pattern) => haystack.includes(pattern));
}

function getMeaningfulFinnMetrics({
  activityEntries = [],
  blockedEntries = [],
  deviationEntries = [],
}) {
  const reviewedEntries = activityEntries.filter(isMeaningfulReviewedEntry);
  const openEntries = activityEntries.filter(isMeaningfulOpenEntry);
  const blockedMeaningfulEntries = blockedEntries.filter(isMeaningfulBlockedEntry);
  const deviationMeaningfulEntries = deviationEntries.filter(isMeaningfulDeviationEntry);

  return {
    reviewedCount: reviewedEntries.length,
    openActionCount: openEntries.length,
    blockedCount: blockedMeaningfulEntries.length,
    deviationCount: deviationMeaningfulEntries.length,
    reviewedEntries,
    openEntries,
    blockedMeaningfulEntries,
    deviationMeaningfulEntries,
  };
}

function humanizeEvidenceDetail(entry = {}, kind, reflectionT) {
  const status = String(entry?.status || entry?.resolve_state || '').toLowerCase();
  const combined = [
    entry?.status,
    entry?.resolve_state,
    entry?.label,
    entry?.type,
  ]
    .filter(Boolean)
    .join(' ')
    .toLowerCase();

  if (kind === 'blocked') return reflectionT.evidenceBlocked;
  if (kind === 'deviation') return reflectionT.evidenceDeviation;
  if (status.includes('resolve') || combined.includes('resolve')) return reflectionT.evidenceResolved;
  if (status.includes('skip') || combined.includes('skip') || combined.includes('later') || combined.includes('snooz')) return reflectionT.evidenceSkipped;
  if (status.includes('review') || combined.includes('review')) return reflectionT.evidenceReviewed;
  if (status.includes('pending') || combined.includes('pending') || combined.includes('open')) return reflectionT.evidencePending;
  return reflectionT.noExtraDetails;
}

function humanizeEvidenceTitle(entry = {}, kind, reflectionT) {
  if (entry?.asset) return String(entry.asset).toUpperCase();
  if (kind === 'blocked') return reflectionT.genericBlockedItem;
  if (kind === 'deviation') return reflectionT.genericDeviationItem;
  return reflectionT.genericOpenItem;
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
          Controlelagen
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
  const { t } = useTranslation();
  const controllerT = t.pages.report.finn.controller;
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
          {controllerT.headline}
        </span>
        <span className="rounded-full bg-white/75 dark:bg-slate-950/40 px-3 py-1 text-[9px] font-black uppercase tracking-widest">
          {controller.dominant_label || controller.dominant_agent}
        </span>
      </div>
      <p className="mt-3 text-sm font-semibold leading-relaxed">
        {controller.reason || controller.next_action || controllerT.fallback}
      </p>
      {controller.next_action && (
        <p className="mt-2 text-[10px] font-black uppercase tracking-[0.14em] opacity-75">
          {controller.next_action}
        </p>
      )}
      {controller.primary_action?.prompt && (
        <div className="mt-3 inline-flex items-center gap-2 rounded-xl bg-white/75 dark:bg-slate-950/40 px-3 py-2 text-[10px] font-black uppercase tracking-[0.14em]">
          {controllerT.primaryHandoff}: {controller.primary_action.label || controller.primary_action.prompt}
        </div>
      )}
      {controller.primary_item_id && (
        <p className="mt-2 text-[9px] font-black uppercase tracking-[0.14em] opacity-65">
          {controllerT.accountabilityItem}: {controller.primary_item_id}
        </p>
      )}
    </div>
  );
}

function FinnPortfolioRisk({ portfolioRisk }) {
  const { t } = useTranslation();
  const riskT = t.pages.report.finn.portfolioRisk;
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
          {riskT.title}
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
            {riskT.ignoreToday}
          </div>
          <div className="mt-2 grid grid-cols-1 md:grid-cols-2 gap-2">
            {ignoreToday.map((item) => (
              <div key={`ignore-${item.asset}`} className="rounded-xl border border-white/60 dark:border-slate-900/50 bg-white/70 dark:bg-slate-950/35 p-3">
                <div className="flex items-center justify-between gap-3">
                  <span className="text-[10px] font-black uppercase tracking-[0.14em]">{item.asset}</span>
                  <span className="text-[8px] font-black uppercase tracking-widest opacity-70">
                    {riskT.scoreLabel} {item.risk_score}
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
            {riskT.liveHotspots}
          </div>
          <div className="mt-2 grid grid-cols-1 md:grid-cols-2 gap-2">
            {liveHotspots.map((item) => (
              <div key={`hotspot-${item.asset}`} className="rounded-xl border border-white/60 dark:border-slate-900/50 bg-white/70 dark:bg-slate-950/35 p-3">
                <div className="flex items-center justify-between gap-3">
                  <span className="text-[10px] font-black uppercase tracking-[0.14em]">{item.asset}</span>
                  <span className="text-[8px] font-black uppercase tracking-widest opacity-70">
                    {item.live_bot_count} {riskT.liveLabel}
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
            {riskT.topConflicts}
          </div>
          <div className="mt-2 space-y-2">
            {rankedConflicts.map((item, index) => (
              <div key={`conflict-${item.asset || 'portfolio'}-${index}`} className="rounded-xl border border-white/60 dark:border-slate-900/50 bg-white/70 dark:bg-slate-950/35 p-3">
                <div className="flex items-center justify-between gap-3">
                  <span className="text-[10px] font-black uppercase tracking-[0.14em]">{item.asset || riskT.portfolioFallback}</span>
                  <span className="text-[8px] font-black uppercase tracking-widest opacity-70">
                    {item.severity || item.risk_level || riskT.reviewFallback}
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
  const { t } = useTranslation();
  const reflectionT = t.pages.report.finn.reflection;
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
                      {entry.label || entry.type || reflectionT.itemFallback}
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

function FinnReflectionBlocks({
  analysis,
  showActivityEntries = false,
  variant = 'default',
  copy = null,
  reviewedCount = 0,
  blockedCount = 0,
  openActionCount = 0,
}) {
  const { t } = useTranslation();
  const reflectionT = t.pages.report.finn.reflection;
  const sections = analysis?.sections || {};
  const dayClose = analysis?.day_close || {};

  const whatIDid = dayClose?.what_i_did_today || sections?.activity_journal || null;
  const whatFinnBlocked = dayClose?.what_finn_blocked || sections?.blocked_summary || null;
  const whereIDeviated = dayClose?.where_i_deviated || sections?.plan_adherence || null;
  const activityEntries = cleanFinnEntries(whatIDid?.entries || []).filter((entry) => (
    isMeaningfulReviewedEntry(entry) || isMeaningfulOpenEntry(entry)
  ));
  const blockedEntries = cleanFinnEntries(whatFinnBlocked?.entries || []).filter(isMeaningfulBlockedEntry);
  const deviationEntries = cleanFinnEntries(whereIDeviated?.entries || []).filter(isMeaningfulDeviationEntry);
  const digest = copy || buildFinnDigestCopy();
  const cards = [
    {
      key: 'activity',
      icon: ClipboardList,
      title: digest.activityTitle || reflectionT.todayTitle,
      summary: digest.activitySummary(reviewedCount, openActionCount),
      entries: showActivityEntries ? activityEntries : [],
      accent: 'slate',
      renderEntry: (entry) => (
        <>
          <div className="flex items-center justify-between gap-3">
            <span className="text-[10px] font-black uppercase tracking-[0.14em]">
              {humanizeEvidenceTitle(entry, 'activity', reflectionT)}
            </span>
            {entry.asset && (
              <span className="text-[8px] font-black uppercase tracking-widest opacity-70">
                {entry.asset}
              </span>
            )}
          </div>
          <p className="mt-2 text-xs font-semibold leading-relaxed">
            {humanizeEvidenceDetail(entry, 'activity', reflectionT)}
          </p>
        </>
      ),
    },
    {
      key: 'blocked',
      icon: ShieldAlert,
      title: reflectionT.blockedTitle,
      summary: digest.blockedSummary(blockedCount),
      entries: blockedEntries,
      accent: 'rose',
      renderEntry: (entry) => (
        <>
          <div className="flex items-center justify-between gap-3">
            <span className="text-[10px] font-black uppercase tracking-[0.14em]">
              {humanizeEvidenceTitle(entry, 'blocked', reflectionT)}
            </span>
            <span className="text-[8px] font-black uppercase tracking-widest opacity-70">
              {entry.asset || reflectionT.guardrailFallback}
            </span>
          </div>
          <p className="mt-2 text-xs font-semibold leading-relaxed">
            {humanizeEvidenceDetail(entry, 'blocked', reflectionT)}
          </p>
        </>
      ),
    },
    {
      key: 'deviation',
      icon: Activity,
      title: reflectionT.deviationTitle,
      summary: digest.deviationSummary(blockedCount),
      entries: deviationEntries,
      accent: 'emerald',
      renderEntry: (entry) => (
        <>
          <div className="flex items-center justify-between gap-3">
            <span className="text-[10px] font-black uppercase tracking-[0.14em]">
              {humanizeEvidenceTitle(entry, 'deviation', reflectionT)}
            </span>
            <span className="text-[8px] font-black uppercase tracking-widest opacity-70">
              {entry.asset || reflectionT.deviationFallback}
            </span>
          </div>
          <p className="mt-2 text-xs font-semibold leading-relaxed">
            {humanizeEvidenceDetail(entry, 'deviation', reflectionT)}
          </p>
        </>
      ),
    },
  ].filter((card) => card && (card.summary || (Array.isArray(card.entries) && card.entries.length > 0)));

  if (cards.length === 0) return null;

  return (
    <div className="mt-5 grid grid-cols-1 xl:grid-cols-3 gap-4">
      {cards.map((card) => (
        <FinnReflectionSectionCard
          key={card.key}
          icon={card.icon}
          title={card.title}
          summary={card.summary}
          entries={card.entries}
          accent={card.accent}
          renderEntry={card.renderEntry}
        />
      ))}

    </div>
  );
}

function FinnBehavioralIntelligenceBlocks({ analysis, forceVisible = false }) {
  const { t } = useTranslation();
  const behaviorT = t.pages.report.finn.behavior;
  const profile = analysis?.behavioral_profile || null;
  const trend = analysis?.trend || analysis?.week_over_week || analysis?.month_over_month || null;
  const riskFlags = Array.isArray(analysis?.risk_flags) ? analysis.risk_flags : [];
  const habitCards = Array.isArray(analysis?.habit_cards) ? analysis.habit_cards : [];
  const memoryCards = Array.isArray(analysis?.memory_cards) ? analysis.memory_cards : [];
  const balanceScore = analysis?.behavioral_balance_score;

  if (!forceVisible && !profile && !trend && riskFlags.length === 0 && habitCards.length === 0 && memoryCards.length === 0) {
    return null;
  }

  return (
    <div className="mt-5 space-y-4">
      <div className="rounded-2xl border border-violet-200 dark:border-violet-900/50 bg-violet-50/70 dark:bg-violet-950/20 p-4 text-violet-700 dark:text-violet-300">
        <div className="flex items-center gap-2">
          <Brain size={14} />
          <span className="text-[10px] font-black uppercase tracking-[0.16em]">
            {behaviorT.title}
          </span>
        </div>
        <p className="mt-2 text-sm font-semibold leading-relaxed">
          {behaviorT.description}
        </p>
        <div className="mt-3 grid grid-cols-2 md:grid-cols-4 gap-2">
          {[
            [behaviorT.profile, profile?.label || behaviorT.building],
            [behaviorT.trend, trend?.status || trend?.momentum || behaviorT.building],
            [behaviorT.brake, riskFlags[0]?.label || memoryCards[0]?.label || behaviorT.noBrake],
            [behaviorT.style, habitCards[0]?.label || behaviorT.building],
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
                {behaviorT.profile}
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
                {behaviorT.watchFor}: {profile.watch_for}
              </p>
            )}
          </div>
        )}

        {trend && (
          <div className="rounded-2xl border border-amber-200 dark:border-amber-900/50 bg-amber-50/70 dark:bg-amber-950/20 p-4 text-amber-700 dark:text-amber-300">
            <div className="flex items-center justify-between gap-3">
              <span className="inline-flex items-center gap-2 text-[10px] font-black uppercase tracking-[0.16em]">
                <Activity size={13} />
                {behaviorT.trend}
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
                  {behaviorT.balanceScore}
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
              {behaviorT.brake}
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
            {behaviorT.style}
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

function FinnGovernanceSurface({ analysis }) {
  const { t } = useTranslation();
  const governanceT = t.pages.report.finn.governance;
  const priorityEngine = analysis?.priority_engine || null;
  const memoryV2 = analysis?.memory_v2 || null;
  const portfolioOS = analysis?.portfolio_operating_system || null;
  const governanceSummary = analysis?.governance_events_summary || null;
  const primaryProfileHabitAlignment = pickPrimaryProfileHabitAlignment(analysis);
  const behaviorLabel = primaryProfileHabitAlignment
    ? humanizeBehaviorFlagLabel(primaryProfileHabitAlignment.flag, primaryProfileHabitAlignment.label)
    : '';
  const telemetryKeyRef = useRef('');

  useEffect(() => {
    if (!primaryProfileHabitAlignment) return;
    const nextKey = [
      primaryProfileHabitAlignment.flag || 'unknown',
      primaryProfileHabitAlignment.evidence_strength || 'unknown',
      priorityEngine?.headline || portfolioOS?.operating_posture || 'report',
    ].join(':');
    if (telemetryKeyRef.current === nextKey) return;
    telemetryKeyRef.current = nextKey;
    trackAssistantEvent({
      event_name: 'behavioral_intervention_seen',
      page: '/report',
      surface: 'report_governance',
      flow_type: 'behavioral_intervention',
      action_type: 'report_alignment_visible',
      next_best_action: primaryProfileHabitAlignment.recommended_rule || null,
      metadata: {
        behavior_flag: primaryProfileHabitAlignment.flag,
        behavior_label: behaviorLabel,
        evidence_strength: primaryProfileHabitAlignment.evidence_strength,
      },
    });
  }, [behaviorLabel, portfolioOS?.operating_posture, primaryProfileHabitAlignment, priorityEngine?.headline]);

  if (!priorityEngine && !memoryV2 && !portfolioOS && !governanceSummary) {
    return null;
  }

  const phaseCards = [
    [governanceT.decisionReview, governanceSummary?.decision_review_count || 0, 'text-blue-600 dark:text-blue-300', <FileText size={11} className="text-blue-500" />],
    [governanceT.planAdherence, governanceSummary?.plan_adherence_count || 0, 'text-rose-600 dark:text-rose-300', <Shield size={11} className="text-rose-500" />],
    [governanceT.outcomeTracking, governanceSummary?.outcome_tracking_count || 0, 'text-emerald-600 dark:text-emerald-300', <BarChart3 size={11} className="text-emerald-500" />],
    [governanceT.portfolioIntelligence, governanceSummary?.portfolio_intelligence_count || 0, 'text-amber-700 dark:text-amber-300', <Activity size={11} className="text-amber-500" />],
    [governanceT.priorityEngine, governanceSummary?.priority_engine_count || 0, 'text-violet-600 dark:text-violet-300', <Target size={11} className="text-violet-500" />],
    [governanceT.memoryV2, governanceSummary?.memory_v2_count || 0, 'text-fuchsia-600 dark:text-fuchsia-300', <Brain size={11} className="text-fuchsia-500" />],
    [governanceT.portfolioOverview, governanceSummary?.portfolio_operating_system_count || 0, 'text-cyan-600 dark:text-cyan-300', <Bot size={11} className="text-cyan-500" />],
  ];

  const topPriorities = Array.isArray(priorityEngine?.top_priorities) ? priorityEngine.top_priorities.slice(0, 3) : [];
  const nextActions = Array.isArray(portfolioOS?.next_best_actions) ? portfolioOS.next_best_actions.slice(0, 3) : [];
  const reviewSummary = [
    {
      label: governanceT.decisionReview,
      tone: 'border-blue-200 dark:border-blue-900/50 bg-blue-50/70 dark:bg-blue-950/20 text-blue-700 dark:text-blue-300',
      summary:
        governanceSummary?.decision_review_count > 0
          ? replaceVars(governanceT.decisionReviewSummary, { count: governanceSummary.decision_review_count })
          : governanceT.decisionReviewEmpty,
    },
    {
      label: governanceT.planAdherence,
      tone: 'border-rose-200 dark:border-rose-900/50 bg-rose-50/70 dark:bg-rose-950/20 text-rose-700 dark:text-rose-300',
      summary:
        governanceSummary?.plan_adherence_count > 0
          ? replaceVars(governanceT.planAdherenceSummary, { count: governanceSummary.plan_adherence_count, detail: memoryV2?.recommended_rule || governanceT.planAdherenceFallback })
          : governanceT.planAdherenceEmpty,
    },
    {
      label: governanceT.outcomeTracking,
      tone: 'border-emerald-200 dark:border-emerald-900/50 bg-emerald-50/70 dark:bg-emerald-950/20 text-emerald-700 dark:text-emerald-300',
      summary:
        governanceSummary?.outcome_tracking_count > 0
          ? replaceVars(governanceT.outcomeTrackingSummary, { count: governanceSummary.outcome_tracking_count, detail: memoryV2?.behavioral_cost || governanceT.outcomeTrackingFallback })
          : governanceT.outcomeTrackingEmpty,
    },
  ];

  return (
    <div className="mt-5 space-y-4">
      <div className="rounded-2xl border border-slate-200 dark:border-slate-800 bg-slate-50/70 dark:bg-slate-900/40 p-4">
        <div className="flex items-center justify-between gap-3">
          <div>
            <div className="inline-flex items-center gap-2 text-[10px] font-black uppercase tracking-[0.16em] text-slate-500 dark:text-slate-400">
              <Terminal size={14} className="text-cyan-500" />
              {governanceT.title}
            </div>
            <p className="mt-2 text-sm font-black leading-relaxed text-slate-900 dark:text-slate-100">
              {portfolioOS?.control_plane?.headline || priorityEngine?.headline || governanceT.headlineFallback}
            </p>
            {primaryProfileHabitAlignment && (
              <div className="mt-3 inline-flex items-center gap-2 rounded-full border border-amber-200 bg-amber-100 px-3 py-1 text-[9px] font-black uppercase tracking-widest text-amber-700 dark:border-amber-900/50 dark:bg-amber-950/25 dark:text-amber-300">
                <Shield size={12} />
                {governanceT.behavioralBrake}: {behaviorLabel}
              </div>
            )}
          </div>
          {portfolioOS?.operating_posture && (
            <span className="rounded-full bg-white/75 dark:bg-slate-950/40 px-3 py-1 text-[9px] font-black uppercase tracking-widest text-cyan-700 dark:text-cyan-300">
              {portfolioOS.operating_posture}
            </span>
          )}
        </div>

        <div className="mt-4 grid grid-cols-2 gap-2 lg:grid-cols-4">
          {phaseCards.map(([label, value, tone, icon]) => (
            <div
              key={label}
              className="rounded-xl border border-white/60 dark:border-slate-900/50 bg-white/70 dark:bg-slate-950/35 p-3"
            >
              <div className="flex items-center justify-between gap-2">
                <span className="inline-flex items-center gap-1 text-[8px] font-black uppercase tracking-[0.14em] text-slate-400 dark:text-slate-500">
                  {icon}
                  <span className="truncate">{label}</span>
                </span>
                <span className={`text-sm font-black ${tone}`}>{value}</span>
              </div>
            </div>
          ))}
        </div>
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-3 gap-4">
        {reviewSummary.map((item) => (
          <div key={item.label} className={`rounded-2xl border p-4 ${item.tone}`}>
            <div className="text-[10px] font-black uppercase tracking-[0.16em]">
              {item.label}
            </div>
            <p className="mt-3 text-sm font-semibold leading-relaxed">{item.summary}</p>
          </div>
        ))}
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-3 gap-4">
        {priorityEngine && (
          <div className="rounded-2xl border border-violet-200 dark:border-violet-900/50 bg-violet-50/70 dark:bg-violet-950/20 p-4 text-violet-700 dark:text-violet-300">
            <div className="flex items-center justify-between gap-3">
              <span className="inline-flex items-center gap-2 text-[10px] font-black uppercase tracking-[0.16em]">
                <Target size={13} />
                {governanceT.priorityEngine}
              </span>
              <span className="rounded-full bg-white/75 dark:bg-slate-950/40 px-3 py-1 text-[9px] font-black uppercase tracking-widest">
                {(priorityEngine.open_counts?.high_priority_count || 0)} {governanceT.priorityHigh}
              </span>
            </div>
            {priorityEngine.why_now && (
              <p className="mt-3 text-sm font-semibold leading-relaxed">{priorityEngine.why_now}</p>
            )}
            {primaryProfileHabitAlignment?.recommended_rule && (
              <div className="mt-3 rounded-xl border border-amber-200 bg-white/80 p-3 dark:border-amber-900/40 dark:bg-slate-950/35">
                <div className="text-[9px] font-black uppercase tracking-[0.14em] text-amber-700 dark:text-amber-300">
                  {governanceT.whyFinnBrakes}
                </div>
                <p className="mt-2 text-xs font-semibold leading-relaxed text-slate-700 dark:text-slate-200">
                  {primaryProfileHabitAlignment.recommended_rule}
                </p>
              </div>
            )}
            {topPriorities.length > 0 && (
              <div className="mt-3 space-y-2">
                {topPriorities.map((item, index) => (
                  <div key={`${item.id || item.title}-${index}`} className="rounded-xl border border-white/60 dark:border-slate-900/50 bg-white/70 dark:bg-slate-950/35 p-3">
                    <div className="flex items-center justify-between gap-3">
                      <span className="text-[10px] font-black uppercase tracking-[0.14em] text-violet-900 dark:text-violet-100">
                        {item.title}
                      </span>
                      <div className="flex flex-col items-end gap-1">
                        <span className="text-[8px] font-black uppercase tracking-widest opacity-70">
                          {item.lane || item.priority}
                        </span>
                        {humanizeBehavioralPriorityBadge(item) && (
                          <span className={`rounded-full border px-2 py-0.5 text-[8px] font-black uppercase tracking-widest ${behavioralPriorityBadgeTone(item)}`}>
                            {humanizeBehavioralPriorityBadge(item)}
                          </span>
                        )}
                      </div>
                    </div>
                    {(item.why_now || item.source_reason) && (
                      <p className="mt-2 text-xs font-semibold leading-relaxed">{item.why_now || item.source_reason}</p>
                    )}
                    {item.behavioral_priority_reason && (
                      <div className="mt-2 rounded-lg border border-white/60 dark:border-slate-900/50 bg-white/80 dark:bg-slate-950/35 p-2.5">
                        <div className="text-[8px] font-black uppercase tracking-widest opacity-70">
                          {governanceT.whyFinnBrakesBecause}
                        </div>
                        <p className="mt-1 text-[11px] font-semibold leading-relaxed text-slate-700 dark:text-slate-200">
                          {item.behavioral_priority_reason}
                        </p>
                      </div>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {memoryV2 && (
          <div className="rounded-2xl border border-fuchsia-200 dark:border-fuchsia-900/50 bg-fuchsia-50/70 dark:bg-fuchsia-950/20 p-4 text-fuchsia-700 dark:text-fuchsia-300">
            <div className="flex items-center justify-between gap-3">
              <span className="inline-flex items-center gap-2 text-[10px] font-black uppercase tracking-[0.16em]">
                <Brain size={13} />
                {governanceT.memoryV2}
              </span>
              <span className="rounded-full bg-white/75 dark:bg-slate-950/40 px-3 py-1 text-[9px] font-black uppercase tracking-widest">
                {memoryV2.confidence_level || governanceT.memoryEarly}
              </span>
            </div>
            {memoryV2.memory_pattern && (
              <div className="mt-3 text-sm font-black text-fuchsia-900 dark:text-fuchsia-100">
                {memoryV2.memory_pattern}
              </div>
            )}
            {memoryV2.behavioral_cost && (
              <p className="mt-2 text-sm font-semibold leading-relaxed">{memoryV2.behavioral_cost}</p>
            )}
            {memoryV2.recommended_rule && (
                <div className="mt-3 rounded-xl border border-white/60 dark:border-slate-900/50 bg-white/70 dark:bg-slate-950/35 p-3">
                <div className="text-[9px] font-black uppercase tracking-[0.14em] opacity-80">
                  {governanceT.recommendedRule}
                </div>
                <p className="mt-2 text-xs font-semibold leading-relaxed">{memoryV2.recommended_rule}</p>
              </div>
            )}
          </div>
        )}

        {portfolioOS && (
          <div className="rounded-2xl border border-cyan-200 dark:border-cyan-900/50 bg-cyan-50/70 dark:bg-cyan-950/20 p-4 text-cyan-700 dark:text-cyan-300">
            <div className="flex items-center justify-between gap-3">
              <span className="inline-flex items-center gap-2 text-[10px] font-black uppercase tracking-[0.16em]">
                <Bot size={13} />
                {governanceT.portfolioOperatingSystem}
              </span>
              <span className="rounded-full bg-white/75 dark:bg-slate-950/40 px-3 py-1 text-[9px] font-black uppercase tracking-widest">
                {portfolioOS.operating_posture || governanceT.steady}
              </span>
            </div>
            {portfolioOS.control_plane?.why_now && (
              <p className="mt-3 text-sm font-semibold leading-relaxed">{portfolioOS.control_plane.why_now}</p>
            )}
            {portfolioOS.control_plane?.habit_override && (
              <div className="mt-3 rounded-xl border border-white/60 dark:border-slate-900/50 bg-white/70 dark:bg-slate-950/35 p-3">
                <div className="text-[9px] font-black uppercase tracking-[0.14em] opacity-80">
                  {governanceT.behaviorRuleNow}
                </div>
                <p className="mt-2 text-xs font-semibold leading-relaxed text-slate-700 dark:text-slate-200">
                  {portfolioOS.control_plane.habit_override}
                </p>
              </div>
            )}
            {nextActions.length > 0 && (
              <div className="mt-3 space-y-2">
                {nextActions.map((item, index) => (
                  <div key={`${item}-${index}`} className="rounded-xl border border-white/60 dark:border-slate-900/50 bg-white/70 dark:bg-slate-950/35 p-3 text-xs font-semibold leading-relaxed">
                    {item}
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

function FinnReportsPanel({ report }) {
  const { t, locale } = useTranslation();
  const reportT = t.pages.report;
  const finnT = reportT.finn || {};
  const digestCopy = useMemo(() => buildFinnDigestCopy(finnT?.digest), [finnT?.digest]);
  const panelRef = useRef(null);
  const detailsRef = useRef(null);
  const [activeFinnReport, setActiveFinnReport] = useState('today');
  const [finnReportCache, setFinnReportCache] = useState({});
  const [finnReport, setFinnReport] = useState(null);
  const [finnLoading, setFinnLoading] = useState(false);
  const [finnError, setFinnError] = useState('');
  const [expanded, setExpanded] = useState(false);
  const [shouldLoadFinn, setShouldLoadFinn] = useState(false);

  const finnReportOptions = useMemo(() => resolveFinnReportOptions(finnT?.options), [finnT?.options]);
  const safeFinnReportOptions = useMemo(() => {
    const options = Array.isArray(finnReportOptions) ? finnReportOptions : [];
    const sanitized = options.filter((option) => option && typeof option.key === 'string' && option.key);
    return sanitized.length ? sanitized : FALLBACK_FINN_REPORT_OPTIONS;
  }, [finnReportOptions]);

  const activeOption = useMemo(
    () => resolveActiveFinnReportOption(safeFinnReportOptions, activeFinnReport),
    [activeFinnReport, safeFinnReportOptions]
  );
  const primaryReflectionTabs = useMemo(
    () => safeFinnReportOptions.filter((option) => ['today', 'week', 'behavior'].includes(option?.key)),
    [safeFinnReportOptions]
  );

  const loadFinnReport = async (option = activeOption, force = false) => {
    if (!option?.key || !option?.prompt) {
      setFinnReport(null);
      setFinnError(finnT?.loadError || 'Finn report could not be loaded.');
      setFinnLoading(false);
      return;
    }

    if (!force && finnReportCache[option.key]) {
      setFinnReport(finnReportCache[option.key]);
      setFinnError('');
      setFinnLoading(false);
      return;
    }

    setFinnLoading(true);
    setFinnError('');
    trackAssistantEvent({
      event_name: 'report_ask_finn_used',
      page: '/report',
      surface: 'web',
      flow_type: 'report_explain',
      report_type: option.key,
    });
    trackAssistantEvent({
      event_name: 'report_finn_requested',
      page: '/report',
      surface: 'web',
      flow_type: 'report_explain',
      report_type: option.key,
    });

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
      setFinnError(finnT?.loadError || 'Finn report could not be loaded.');
    } finally {
      setFinnLoading(false);
    }
  };

  useEffect(() => {
    trackAssistantEvent({
      event_name: 'screen_view',
      page: '/report',
      surface: 'web',
      flow_type: 'report',
    });
  }, []);

  useEffect(() => {
    if (!shouldLoadFinn) {
      setFinnLoading(false);
      return;
    }
    if (!activeOption?.key) {
      setFinnLoading(false);
      setFinnError(finnT?.loadError || 'Finn report could not be loaded.');
      return;
    }
    loadFinnReport(activeOption);
  }, [activeFinnReport, shouldLoadFinn, activeOption, finnT?.loadError]);

  const analysis = finnReport?.state?.analysis || finnReport?.analysis || {};
  const metrics = analysis?.metrics || {};
  const activeOptionKey = activeOption?.key || 'today';
  const sections = analysis?.sections || {};
  const dayClose = analysis?.day_close || {};
  const whatIDid = dayClose?.what_i_did_today || sections?.activity_journal || null;
  const whatFinnBlocked = dayClose?.what_finn_blocked || sections?.blocked_summary || null;
  const whereIDeviated = dayClose?.where_i_deviated || sections?.plan_adherence || null;
  const cleanedActivityEntries = cleanFinnEntries(whatIDid?.entries || []);
  const cleanedBlockedEntries = cleanFinnEntries(whatFinnBlocked?.entries || []);
  const cleanedDeviationEntries = cleanFinnEntries(whereIDeviated?.entries || []);
  const meaningfulMetrics = getMeaningfulFinnMetrics({
    activityEntries: cleanedActivityEntries,
    blockedEntries: cleanedBlockedEntries,
    deviationEntries: cleanedDeviationEntries,
  });
  const reviewedCount = meaningfulMetrics.reviewedCount;
  const blockedCount = meaningfulMetrics.blockedCount;
  const openActionCount = meaningfulMetrics.openActionCount;
  const deviationCount = meaningfulMetrics.deviationCount;
  const reflectionSummary = buildFinnReflectionSummary({
    digest: digestCopy,
    activityEntries: meaningfulMetrics.reviewedEntries.concat(meaningfulMetrics.openEntries),
    blockedEntries: meaningfulMetrics.blockedMeaningfulEntries,
    deviationEntries: meaningfulMetrics.deviationMeaningfulEntries,
    reviewedCount,
    blockedCount,
    openActionCount,
  });
  const compactMetricItems = [
    [digestCopy.reviewed, reviewedCount],
    [digestCopy.blocked, blockedCount],
    [digestCopy.open, openActionCount],
  ];
  const isTodayView = activeOptionKey === 'today';
  const evidenceCount = reviewedCount + blockedCount + openActionCount;
  const evidenceTarget = 3;
  const evidenceProgress = Math.max(0, Math.min(100, (evidenceCount / evidenceTarget) * 100));
  const totalEvents = cleanedActivityEntries.length + cleanedBlockedEntries.length + cleanedDeviationEntries.length;
  const hasLimitedEvidence = evidenceCount < evidenceTarget;
  const reflectionDateLabel = formatDateTime(new Date(report?.report_date || Date.now()), locale, {
    day: 'numeric',
    month: 'short',
    year: 'numeric',
  });
  const headerRangeLabel = activeOptionKey === 'today' ? 'Today' : activeOption?.label || digestCopy.metricsHint;
  const emptyStateSupport = hasLimitedEvidence
    ? 'FINN needs a few explicit decisions before it can identify a meaningful pattern.'
    : 'FINN reviews how closely you followed your plan and what to improve next.';
  const primaryActionLabel = reflectionSummary.primaryAction;
  const reflectionPanel = finnT?.reflectionPanel || {};
  const openReflectionDetails = () => {
    setExpanded(true);
    if (typeof window !== 'undefined') {
      window.requestAnimationFrame(() => {
        detailsRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' });
      });
    }
  };

  return (
    <section ref={panelRef} className="my-8 md:my-10">
      <div className="flex items-center gap-2 mb-4">
        <Brain size={14} className="text-blue-600 dark:text-blue-400" />
        <span className="text-[11px] font-black uppercase tracking-[0.28em] text-slate-400 dark:text-slate-500">
          {finnT.sectionEyebrow}
        </span>
      </div>

      <div className="rounded-3xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-950 shadow-lg shadow-slate-900/5 overflow-hidden">
        <div className="p-6 md:p-7 border-b border-slate-100 dark:border-slate-800/80">
          <div className="flex flex-col gap-5 lg:flex-row lg:items-start lg:justify-between">
            <div>
              <h2 className="text-3xl md:text-4xl font-black tracking-tight text-slate-950 dark:text-slate-100">
                {reflectionPanel.title || 'Reflection'}
              </h2>
              <p className="mt-2 text-base font-medium text-slate-500 dark:text-slate-400 max-w-2xl">
                {reflectionPanel.description || 'FINN reviews how closely you followed your plan and what to improve next.'}
              </p>
            </div>
            <div className="flex flex-wrap items-center gap-3">
              <span className="text-base font-medium text-slate-600 dark:text-slate-300">
                {headerRangeLabel} · {reflectionDateLabel}
              </span>
              <span className={`inline-flex items-center rounded-2xl border px-4 py-2 text-sm font-semibold ${
                hasLimitedEvidence
                  ? 'border-blue-200 bg-blue-50 text-blue-600 dark:border-blue-900/40 dark:bg-blue-950/20 dark:text-blue-300'
                  : 'border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-900/40 dark:bg-emerald-950/20 dark:text-emerald-300'
              }`}>
                {hasLimitedEvidence ? 'Limited evidence' : 'Reflection active'}
              </span>
            </div>
          </div>
        </div>

        <div className="p-6 md:p-7">
          {!shouldLoadFinn ? (
            <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 rounded-2xl border border-slate-200 dark:border-slate-800 bg-slate-50/70 dark:bg-slate-900/40 p-4">
              <div className="text-sm font-semibold text-slate-600 dark:text-slate-300">
                {finnT.deferredLoad}
              </div>
              <button
                onClick={() => setShouldLoadFinn(true)}
                className="self-start sm:self-auto px-4 py-2 rounded-xl bg-white dark:bg-slate-950 border border-slate-200 dark:border-slate-800 text-[10px] font-black uppercase tracking-widest text-slate-700 dark:text-slate-200 hover:bg-slate-100 dark:hover:bg-slate-900 transition-colors"
              >
                {finnT.loadButton}
              </button>
            </div>
          ) : finnLoading ? (
            <div className="flex items-center gap-3 text-sm font-bold text-slate-500 dark:text-slate-400">
              <Loader2 size={16} className="animate-spin text-blue-600" />
              {finnT.loading}
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
                {finnT.retry}
              </button>
            </div>
          ) : (
            <div className="space-y-5">
              <div className="flex flex-col gap-4">
                <div className="overflow-x-auto">
                  <div className="inline-flex rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-950 overflow-hidden min-w-max">
                    {primaryReflectionTabs.map((option, index) => {
                      const active = option.key === activeFinnReport;
                      const label = option.key === 'behavior' ? '30 days' : option.label;
                      return (
                        <button
                          key={`${option.key}-${index}`}
                          onClick={() => setActiveFinnReport(option.key)}
                          className={`px-6 py-3 text-sm font-semibold transition-colors ${
                            active
                              ? 'bg-blue-50 text-blue-600 dark:bg-blue-950/30 dark:text-blue-300'
                              : 'text-slate-600 hover:text-slate-950 dark:text-slate-400 dark:hover:text-slate-100'
                          } ${index !== primaryReflectionTabs.length - 1 ? 'border-r border-slate-200 dark:border-slate-800' : ''}`}
                        >
                          {label}
                        </button>
                      );
                    })}
                  </div>
                </div>
              </div>

              <div className="rounded-[28px] border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-950 p-5 md:p-6">
                <div className="grid grid-cols-1 gap-5 xl:grid-cols-[minmax(0,1.65fr)_minmax(240px,0.8fr)]">
                  <div className="min-w-0">
                    <div className="text-[11px] font-black uppercase tracking-[0.22em] text-blue-600 dark:text-blue-300">
                      {reflectionPanel.eyebrow || "FINN'S REFLECTION"}
                    </div>
                    <p className="mt-4 max-w-3xl text-2xl md:text-3xl font-black tracking-tight text-slate-950 dark:text-slate-100">
                      {reflectionSummary.headline}
                    </p>
                    <p className="mt-3 text-base font-medium text-slate-500 dark:text-slate-400 max-w-2xl">
                      {emptyStateSupport}
                    </p>

                    <div className="mt-6 grid grid-cols-1 gap-4 sm:grid-cols-3">
                      {[
                        [ClipboardList, digestCopy.reviewed, reviewedCount],
                        [ShieldAlert, digestCopy.blocked, blockedCount],
                        [Activity, digestCopy.open, openActionCount],
                      ].map(([Icon, label, value]) => (
                        <div key={label} className="flex items-center gap-4">
                          <div className="flex h-10 w-10 items-center justify-center rounded-full border border-slate-200 text-slate-500 dark:border-slate-800 dark:text-slate-400">
                            <Icon size={18} />
                          </div>
                          <div>
                            <div className="text-sm font-medium text-slate-500 dark:text-slate-400">{label}</div>
                            <div className="text-2xl font-black text-slate-950 dark:text-slate-100">{value}</div>
                          </div>
                        </div>
                      ))}
                    </div>

                    <div className="mt-6 border-t border-slate-200 dark:border-slate-800 pt-5">
                      <div className="flex items-center justify-between gap-4">
                        <span className="text-sm font-medium text-slate-500 dark:text-slate-400">
                          {reflectionPanel.evidenceCollected || 'Evidence collected'}
                        </span>
                        <span className="text-sm font-medium text-slate-600 dark:text-slate-300">
                          {Math.min(evidenceCount, evidenceTarget)} of {evidenceTarget} decisions
                        </span>
                      </div>
                      <div className="mt-3 h-2 overflow-hidden rounded-full bg-slate-200 dark:bg-slate-800">
                        <div
                          className="h-full rounded-full bg-blue-500 dark:bg-blue-400 transition-all"
                          style={{ width: `${evidenceProgress}%` }}
                        />
                      </div>
                    </div>
                  </div>

                  <div className="rounded-3xl border border-blue-100 bg-blue-50/50 p-5 text-slate-700 dark:border-blue-900/40 dark:bg-blue-950/20 dark:text-slate-200">
                    <div className="text-[11px] font-black uppercase tracking-[0.22em] text-blue-600 dark:text-blue-300">
                      {reflectionPanel.whenVisibleTitle || 'WHEN REFLECTION APPEARS'}
                    </div>
                    <p className="mt-4 text-base font-medium leading-relaxed">
                      {reflectionPanel.whenVisibleBody || 'FINN will show patterns here once enough existing activity and reviews have been recorded.'}
                    </p>
                  </div>
                </div>

                <button
                  onClick={() => setExpanded((value) => !value)}
                  className="mt-5 flex w-full items-center justify-between rounded-2xl border border-slate-200 bg-white px-5 py-5 text-left transition hover:border-slate-300 dark:border-slate-800 dark:bg-slate-950"
                >
                  <div className="flex min-w-0 items-center gap-4">
                    <div className="flex h-11 w-11 items-center justify-center rounded-2xl border border-slate-200 text-slate-500 dark:border-slate-800 dark:text-slate-400">
                      <FileText size={18} />
                    </div>
                    <div className="min-w-0">
                      <div className="text-2xl font-black tracking-tight text-slate-950 dark:text-slate-100">
                        {reflectionPanel.activityEvidenceTitle || 'Activity & evidence'}
                      </div>
                      <div className="mt-1 text-sm font-medium text-slate-500 dark:text-slate-400">
                        {reflectionPanel.activityEvidenceBody || 'See the decisions and events behind this reflection'}
                      </div>
                    </div>
                  </div>
                  <div className="ml-4 flex items-center gap-4 text-slate-500 dark:text-slate-400">
                    <span className="text-sm font-medium">{totalEvents} events</span>
                    <ChevronRight size={18} className={`transition-transform ${expanded ? 'rotate-90' : ''}`} />
                  </div>
                </button>

                {!hasLimitedEvidence ? (
                  <div className="mt-5 grid grid-cols-1 lg:grid-cols-3 gap-3">
                    {[
                      [digestCopy.good, reflectionSummary.good, 'border-emerald-200 dark:border-emerald-900/50 bg-emerald-50/70 dark:bg-emerald-950/20 text-emerald-800 dark:text-emerald-200'],
                      [digestCopy.attention, reflectionSummary.attention, 'border-amber-200 dark:border-amber-900/50 bg-amber-50/70 dark:bg-amber-950/20 text-amber-800 dark:text-amber-200'],
                      [digestCopy.next, reflectionSummary.next, 'border-blue-200 dark:border-blue-900/50 bg-blue-50/70 dark:bg-blue-950/20 text-blue-800 dark:text-blue-200'],
                    ].map(([label, value, tone]) => (
                      <div key={label} className={`rounded-2xl border p-4 ${tone}`}>
                        <div className="text-[10px] font-black uppercase tracking-[0.16em]">
                          {label}
                        </div>
                        <p className="mt-3 text-sm font-semibold leading-relaxed">
                          {value}
                        </p>
                      </div>
                    ))}
                  </div>
                ) : null}
              </div>

              {expanded ? (
                <div ref={detailsRef} className="rounded-2xl border border-slate-200 dark:border-slate-800 bg-slate-50/60 dark:bg-slate-900/40 p-5 md:p-6">
                  <div className="mb-4 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                    <div>
                      <div className="text-[10px] font-black uppercase tracking-[0.16em] text-slate-400 dark:text-slate-500">
                        {reflectionPanel.detailsTitle || 'Reflection details'}
                      </div>
                      <div className="mt-1 text-lg font-black text-slate-950 dark:text-slate-100">
                        {primaryActionLabel}
                      </div>
                    </div>
                    <button
                      onClick={() => setExpanded(false)}
                      className="text-sm font-semibold text-slate-500 transition-colors hover:text-slate-900 dark:text-slate-400 dark:hover:text-slate-100"
                    >
                      {digestCopy.detailButtonClose}
                    </button>
                  </div>
                  <FinnReflectionBlocks
                    analysis={analysis}
                    showActivityEntries={!isTodayView}
                    variant={isTodayView ? 'today' : 'default'}
                    copy={digestCopy}
                    reviewedCount={reviewedCount}
                    blockedCount={blockedCount}
                    openActionCount={openActionCount}
                  />
                </div>
              ) : null}
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
  const { t, locale } = useTranslation();
  const { selectedAsset } = useAsset();
  const reportT = t.pages.report;
  const tradingPanelCopy = useMemo(() => getTradingReportPanelCopy(locale), [locale]);

  const [reportType, setReportType] = useState('daily');
  const [report, setReport] = useState(null);
  const [dates, setDates] = useState([]);
  const [selectedDate, setSelectedDate] = useState('latest');
  const [tradingReportExpanded, setTradingReportExpanded] = useState(false);

  const [loading, setLoading] = useState(true);
  const [pdfLoading, setPdfLoading] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [generateInfo, setGenerateInfo] = useState('');
  const [error, setError] = useState('');

  const pollTokenRef = useRef(0);
  const lastSignatureRef = useRef('');

  const handleBoundaryRetry = () => {
    if (typeof window !== 'undefined' && typeof window.__TRADAMIND_CLEAR_STALE_APP__ === 'function') {
      window.__TRADAMIND_CLEAR_STALE_APP__('Widget Crash Detected');
      return;
    }
    if (typeof window !== 'undefined') {
      window.location.reload();
    }
  };

  const fallbackLabel = reportT.types[reportType] || reportT.hudDefaultTitle;
  const tradingReportSummary = useMemo(
    () => getTradingReportSummary(report, tradingPanelCopy.summaryFallback),
    [report, tradingPanelCopy.summaryFallback]
  );

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
      const [rawDates, data] = await Promise.all([
        current.getDates(),
        date === 'latest'
          ? current.getLatest()
          : current.getByDate(date),
      ]);

      setDates(sortDatesDesc(rawDates || []));

      if (!data && AUTO_GENERATE_IF_EMPTY) {
        setLoading(false);
        handleGenerate(true, date);
        return;
      }

      setReport(data || null);
      lastSignatureRef.current = getReportSignature(data);
    } catch {
      setError('Rapport laden mislukt. De inhoud kan tijdelijk verouderd zijn.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData('latest');
  }, [reportType]);

  useEffect(() => {
    setTradingReportExpanded(false);
  }, [reportType, selectedDate]);

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
    setLoading(true);
    setGenerateInfo(
      fromAuto
        ? `Geen ${fallbackLabel.toLowerCase()} gevonden. We maken nu een nieuwe versie voor je klaar.`
        : `We genereren nu een nieuw ${fallbackLabel.toLowerCase()}.`
    );

    try {
      await current.generate();
      await pollUntilNewReport(preferDate);
      showSnackbar(`${fallbackLabel} staat klaar`, 'success');
    } catch (err) {
      console.error(err);
      setError('Genereren van het rapport mislukt. Probeer het zo opnieuw.');
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
      showSnackbar('Het rapport is nog niet volledig geladen', 'warning');
      return;
    }

    try {
      setPdfLoading(true);

      const date =
        selectedDate === 'latest'
          ? report.report_date
          : selectedDate;

      await current.pdf(date);
      showSnackbar(reportT.pdfStarted, 'success');

    } catch (err) {
      console.error(err);
      showSnackbar(reportT.pdfFailed, 'error');
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
           {reportT.pageEyebrow}
        </div>
        <h1 className="page-title text-5xl font-black text-slate-900 dark:text-slate-100 tracking-tight leading-none mb-4">{reportT.title}</h1>
        <div className="flex flex-col sm:flex-row sm:items-center gap-3 sm:gap-4">
          <p className="page-subtitle text-[15px] font-medium text-slate-400 dark:text-slate-500 max-w-2xl leading-relaxed">
            {reportT.subtitle}
          </p>
          <div className="hidden sm:block h-4 w-[1px] bg-slate-200 dark:bg-slate-800" />
          <div className="flex items-center gap-1.5">
            <div className="w-1.5 h-1.5 rounded-full bg-blue-500" />
            <span className="text-[10px] font-black text-blue-600 dark:text-blue-400 uppercase tracking-[0.15em] opacity-80">
              {reportT.generatedBy}
            </span>
          </div>
        </div>
      </header>

      {/* ⚠️ ERROR MESSAGE */}
      {error && (
        <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-900/30 p-6 rounded-2xl flex items-center gap-4 text-red-700 dark:text-red-300 shadow-sm transition-colors">
           <AlertTriangle size={24} />
           <div>
               <div className="text-[11px] font-black uppercase tracking-widest">{reportT.errorTitle}</div>
               <div className="text-sm font-medium">{error}</div>
               <div className="mt-1 text-xs opacity-80">{reportT.errorHelper}</div>
           </div>
        </div>
      )}

      {/* 📄 REPORT CONTENT */}
      {loading ? (
        <div className="pt-8">
          <ReportSkeleton />
        </div>
      ) : (
        report && (
          <div className="animate-fade-slide pb-24">
            <DashboardErrorBoundary onRetry={handleBoundaryRetry}>
              <FinnReportsPanel report={report} />
            </DashboardErrorBoundary>

            <DashboardErrorBoundary onRetry={handleBoundaryRetry}>
              <section className="mt-10 rounded-[28px] border border-slate-200/80 bg-white shadow-[0_18px_40px_-36px_rgba(15,23,42,0.26)]">
                <div className="border-b border-slate-100 px-6 py-6 md:px-8">
                  <div className="max-w-3xl">
                      <div className="text-[10px] font-black uppercase tracking-[0.24em] text-blue-600">
                        {tradingPanelCopy.eyebrow}
                      </div>
                      <h2 className="mt-2 text-3xl font-black tracking-tight text-slate-950">
                        {tradingPanelCopy.sectionTitle}
                      </h2>
                      <div className="mt-4 flex flex-wrap items-center gap-2 text-[11px] font-black uppercase tracking-[0.16em] text-slate-400">
                        <span>{reportT.hudPeriod}: {report?.report_date || '—'}</span>
                        <span className="h-1 w-1 rounded-full bg-slate-300" />
                        <span>{tradingPanelCopy.statusReady}</span>
                      </div>
                  </div>
                </div>

                <div className="px-6 py-6 md:px-8">
                  <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
                    <ReportTabs selected={reportType} onChange={setReportType} />

                    <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 p-1 rounded-xl shadow-sm flex items-center gap-2 transition-colors">
                      <div className="flex items-center gap-2 px-3 py-1 border-r border-slate-100 dark:border-slate-800">
                        <Calendar size={13} className="text-slate-400 dark:text-slate-500" />
                        <select
                          value={selectedDate}
                          onChange={(e) => loadData(e.target.value)}
                          className="bg-transparent text-[11px] font-bold text-slate-600 dark:text-slate-400 focus:outline-none appearance-none"
                        >
                          <option value="latest">{reportT.recent}</option>
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
                          <span className="text-[11px] font-black uppercase tracking-widest">{reportT.pdf}</span>
                        </button>

                        <button
                          onClick={() => handleGenerate(false, selectedDate)}
                          disabled={generating}
                          className="flex items-center gap-2 bg-blue-600 text-white px-4 py-2 rounded-lg hover:bg-blue-700 transition-all shadow-lg shadow-blue-600/10 active:scale-95 disabled:bg-slate-300"
                        >
                          <RefreshCw size={13} className={generating ? "animate-spin" : ""} />
                          <span className="text-[11px] font-black uppercase tracking-widest">{reportT.new}</span>
                        </button>
                      </div>
                    </div>
                  </div>

                  <div className="mt-8">
                    <DashboardErrorBoundary onRetry={handleBoundaryRetry}>
                      <ReportTerminalHUD report={report} type={reportType} loading={loading} />
                    </DashboardErrorBoundary>

                    <div className="mt-5 flex justify-end">
                      <button
                        onClick={() => setTradingReportExpanded((value) => !value)}
                        className="inline-flex items-center gap-2 rounded-xl border border-slate-200 bg-white px-4 py-3 text-[11px] font-black uppercase tracking-[0.16em] text-slate-700 transition hover:border-blue-200 hover:text-blue-600"
                      >
                        {tradingReportExpanded ? tradingPanelCopy.expandedCta : tradingPanelCopy.collapsedCta}
                        <ChevronDown
                          size={14}
                          className={`transition-transform ${tradingReportExpanded ? 'rotate-180' : ''}`}
                        />
                      </button>
                    </div>

                    {tradingReportExpanded && (
                      <DashboardErrorBoundary onRetry={handleBoundaryRetry}>
                        <div className="mt-8">
                          <ReportContainer>
                            <ReportLayout report={report} />
                          </ReportContainer>
                        </div>
                      </DashboardErrorBoundary>
                    )}
                  </div>
                </div>
              </section>
            </DashboardErrorBoundary>
          </div>
        )
      )}
    </div>
  );
}
