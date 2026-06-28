"use client";

import React, { useCallback, useMemo, useRef, useState } from "react";
import {
  Activity,
  AlertTriangle,
  ArrowRight,
  BrainCircuit,
  CheckCircle2,
  Clock3,
  Layers3,
  RefreshCcw,
  ShieldCheck,
  Sparkles,
  UserPlus,
  Users,
} from "lucide-react";

import { useTranslation } from "@/app/providers/I18nProvider";
import { fetchAdminTelemetry } from "@/lib/api/admin";
import { actionButtonStyles } from "@/components/ui/actionButtonStyles";
import { useVisibilityPolling } from "@/hooks/useVisibilityPolling";
import { formatDateTime } from "@/lib/i18n";

function replaceTemplate(template, values = {}) {
  return String(template || "").replace(/\{(\w+)\}/g, (_, key) => String(values[key] ?? ""));
}

function formatTimestamp(isoValue, locale, fallbackUnknown) {
  if (!isoValue) return fallbackUnknown;
  const date = new Date(isoValue);
  if (Number.isNaN(date.getTime())) return fallbackUnknown;
  return formatDateTime(date, locale, {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function formatPercent(part, total) {
  if (!total) return "0%";
  return `${Math.round((part / total) * 100)}%`;
}

function toSentenceCase(value, fallbackUnknown) {
  if (!value) return fallbackUnknown;
  return String(value)
    .replaceAll("_", " ")
    .replace(/\b\w/g, (char) => char.toUpperCase());
}

function TelemetryMetricCard({ title, value, subtitle, icon, tone = "slate" }) {
  const tones = {
    slate: "bg-slate-50 border-slate-100 text-slate-900",
    blue: "bg-blue-50 border-blue-100 text-blue-900",
    green: "bg-emerald-50 border-emerald-100 text-emerald-900",
    amber: "bg-amber-50 border-amber-100 text-amber-900",
  };

  return (
    <div className={`rounded-3xl border p-5 shadow-sm ${tones[tone] || tones.slate}`}>
      <div className="flex items-center justify-between gap-4">
        <div>
          <p className="text-[10px] font-black uppercase tracking-[0.2em] opacity-70">{title}</p>
          <div className="mt-2 text-3xl font-black tracking-tight">{value}</div>
          {subtitle ? <p className="mt-2 text-xs font-semibold opacity-80">{subtitle}</p> : null}
        </div>
        <div className="rounded-2xl bg-white/70 p-3 shadow-sm">{icon}</div>
      </div>
    </div>
  );
}

function SectionCard({ title, subtitle, children, actions = null }) {
  return (
    <div className="rounded-[28px] border border-slate-100 bg-white p-6 shadow-sm">
      <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
        <div>
          <h3 className="text-sm font-black uppercase tracking-[0.2em] text-slate-500">{title}</h3>
          {subtitle ? <p className="mt-1 text-sm font-semibold text-slate-500">{subtitle}</p> : null}
        </div>
        {actions}
      </div>
      <div className="mt-5">{children}</div>
    </div>
  );
}

function SimpleList({ title, subtitle, items, renderItem, emptyText }) {
  return (
    <SectionCard title={title} subtitle={subtitle}>
      <div className="space-y-3">
        {items?.length ? (
          items.map(renderItem)
        ) : (
          <div className="rounded-2xl border border-dashed border-slate-200 bg-slate-50 px-4 py-5 text-sm font-semibold text-slate-500">
            {emptyText}
          </div>
        )}
      </div>
    </SectionCard>
  );
}

function InsightPill({ tone = "slate", children }) {
  const tones = {
    slate: "border-slate-200 bg-slate-50 text-slate-700",
    blue: "border-blue-100 bg-blue-50 text-blue-700",
    green: "border-emerald-100 bg-emerald-50 text-emerald-700",
    amber: "border-amber-100 bg-amber-50 text-amber-700",
    rose: "border-rose-100 bg-rose-50 text-rose-700",
  };

  return (
    <div className={`rounded-2xl border px-4 py-3 text-sm font-semibold ${tones[tone] || tones.slate}`}>
      {children}
    </div>
  );
}

function FunnelRow({ label, value, total, helpText, tone = "blue" }) {
  const percentage = total ? Math.max(4, Math.round((value / total) * 100)) : 0;
  const fills = {
    blue: "bg-blue-500",
    green: "bg-emerald-500",
    amber: "bg-amber-500",
  };

  return (
    <div className="rounded-2xl border border-slate-100 bg-slate-50 p-4">
      <div className="flex items-center justify-between gap-4">
        <div>
          <p className="text-sm font-semibold text-slate-800">{label}</p>
          {helpText ? <p className="mt-1 text-xs font-medium text-slate-500">{helpText}</p> : null}
        </div>
        <div className="text-right">
          <p className="text-lg font-black tracking-tight text-slate-900">{value}</p>
          <p className="text-[10px] font-black uppercase tracking-[0.2em] text-slate-400">
            {formatPercent(value, total)}
          </p>
        </div>
      </div>
      <div className="mt-3 h-2 overflow-hidden rounded-full bg-slate-200">
        <div
          className={`h-full rounded-full ${fills[tone] || fills.blue}`}
          style={{ width: `${Math.min(100, percentage)}%` }}
        />
      </div>
    </div>
  );
}

function LatestEventCard({ event, copy, locale }) {
  return (
    <div className="rounded-2xl border border-slate-100 bg-slate-50 p-4">
      <div className="flex items-start justify-between gap-4">
        <div>
          <p className="text-sm font-semibold text-slate-800">
            {toSentenceCase(event.event_name, copy.unknown)}
          </p>
          <p className="mt-1 text-xs font-medium text-slate-500">
            {event.page || event.surface || copy.noScreenContext}
          </p>
        </div>
        <span className="text-[10px] font-black uppercase tracking-[0.2em] text-slate-400">
          {formatTimestamp(event.timestamp, locale, copy.unknown)}
        </span>
      </div>
      <div className="mt-3 flex flex-wrap gap-2">
        {event.flow_type ? (
          <span className="rounded-full bg-white px-3 py-1 text-[10px] font-black uppercase tracking-[0.18em] text-slate-500">
            {event.flow_type}
          </span>
        ) : null}
        {event.action_type ? (
          <span className="rounded-full bg-white px-3 py-1 text-[10px] font-black uppercase tracking-[0.18em] text-slate-500">
            {event.action_type}
          </span>
        ) : null}
        {event.prompt_text ? (
          <span className="rounded-full bg-white px-3 py-1 text-[10px] font-black uppercase tracking-[0.18em] text-blue-600">
            {copy.promptBadge}
          </span>
        ) : null}
      </div>
      {event.prompt_text ? <p className="mt-3 text-sm font-medium text-slate-700">{event.prompt_text}</p> : null}
    </div>
  );
}

export default function AdminTelemetryPage() {
  const { t, locale } = useTranslation();
  const copy = t.adminTelemetryPage;
  const latestEventCopy = copy.latestEvents;
  const [telemetry, setTelemetry] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const isFetchingRef = useRef(false);

  const loadTelemetry = useCallback(async () => {
    if (isFetchingRef.current) return;
    isFetchingRef.current = true;
    try {
      const payload = await fetchAdminTelemetry();
      setTelemetry(payload);
      setError(null);
    } catch (err) {
      console.error("Failed to load telemetry", err);
      setError(copy.loadError);
    } finally {
      setLoading(false);
      isFetchingRef.current = false;
    }
  }, [copy.loadError]);

  useVisibilityPolling(loadTelemetry, {
    intervalMs: 15000,
    backgroundIntervalMs: 60000,
    runImmediately: true,
  });

  const derived = useMemo(() => {
    if (!telemetry) return null;

    const { health, analytics, openaiRuntime } = telemetry;
    const queueDepths = Object.entries(health?.components?.broker?.queue_depths || {});
    const runtimeIdentity = health?.runtime_identity || {};
    const onboardingFunnel = analytics?.onboarding_funnel || {};
    const firstSessionSummary = analytics?.first_session_summary || {};
    const confirmFunnel = analytics?.confirm_funnel || {};
    const repeatedUserSignal = analytics?.repeated_user_signal || {};
    const latestEvents = analytics?.latest_events || [];
    const breakerActive = Boolean(
      openaiRuntime?.breaker_active ??
        openaiRuntime?.quota_breaker_active ??
        openaiRuntime?.quota_circuit_breaker_active
    );

    const totalSessions = firstSessionSummary?.sessions_seen ?? 0;
    const promptRate = formatPercent(firstSessionSummary?.sessions_with_prompt ?? 0, totalSessions);
    const confirmRate = formatPercent(firstSessionSummary?.sessions_with_confirm ?? 0, totalSessions);
    const reportRate = formatPercent(firstSessionSummary?.sessions_reaching_report ?? 0, totalSessions);
    const dashboardRate = formatPercent(firstSessionSummary?.sessions_reaching_dashboard ?? 0, totalSessions);
    const queueTotal = health?.cluster_observability?.total_queue_depth ?? 0;
    const topPrompt = analytics?.top_prompts?.[0]?.prompt || null;
    const topFirstScreen = analytics?.top_first_screens?.[0]?.page || null;
    const topScreen = analytics?.top_screens?.[0]?.page || null;
    const topBehavioralFlag = analytics?.top_behavioral_flags?.[0] || null;
    const topBehavioralSurface = analytics?.top_behavioral_surfaces?.[0] || null;

    const summaryNotes = [
      queueTotal > 0
        ? {
            tone: "amber",
            icon: AlertTriangle,
            text: replaceTemplate(copy.summary.queueBusy, { queueTotal }),
          }
        : {
            tone: "green",
            icon: CheckCircle2,
            text: copy.summary.queueCalm,
          },
      totalSessions > 0
        ? {
            tone: "blue",
            icon: UserPlus,
            text: replaceTemplate(copy.summary.sessionsActive, {
              dashboardRate,
              reportRate,
              promptRate,
            }),
          }
        : {
            tone: "slate",
            icon: Users,
            text: copy.summary.noSessions,
          },
      topPrompt
        ? {
            tone: "slate",
            icon: Sparkles,
            text: replaceTemplate(copy.summary.topPrompt, { topPrompt }),
          }
        : {
            tone: "slate",
            icon: BrainCircuit,
            text: copy.summary.noPrompts,
          },
      topFirstScreen
        ? {
            tone: "blue",
            icon: Activity,
            text: replaceTemplate(copy.summary.topScreen, {
              topFirstScreen,
              topScreen: topScreen || topFirstScreen,
            }),
          }
        : {
            tone: "slate",
            icon: Activity,
            text: copy.summary.noScreenTelemetry,
          },
      topBehavioralFlag
        ? {
            tone: "amber",
            icon: ShieldCheck,
            text: replaceTemplate(copy.summary.topBehavioralFlag, {
              flag: toSentenceCase(topBehavioralFlag.flag, copy.unknown),
              count: topBehavioralFlag.count,
              surface: topBehavioralSurface?.surface || copy.knownSurfaces,
            }),
          }
        : {
            tone: "slate",
            icon: ShieldCheck,
            text: copy.summary.noBehavioralEvents,
          },
    ];

    return {
      health,
      analytics,
      queueDepths,
      runtimeIdentity,
      onboardingFunnel,
      firstSessionSummary,
      confirmFunnel,
      repeatedUserSignal,
      breakerActive,
      latestEvents,
      promptRate,
      confirmRate,
      reportRate,
      dashboardRate,
      totalSessions,
      topBehavioralFlag,
      topBehavioralSurface,
      summaryNotes,
    };
  }, [copy, telemetry]);

  if (loading) {
    return (
      <div className="flex min-h-[60vh] flex-col items-center justify-center p-10">
        <div className="mb-4 h-12 w-12 animate-spin rounded-full border-4 border-blue-600/20 border-t-blue-600" />
        <p className="text-xs font-bold uppercase tracking-widest text-slate-400">{copy.loading}</p>
      </div>
    );
  }

  if (error || !telemetry || !derived) {
    return (
      <div className="p-10 text-center">
        <div className="mb-4 inline-flex rounded-full bg-rose-50 p-4 text-rose-500">
          <ShieldCheck size={32} />
        </div>
        <h1 className="mb-2 text-2xl font-black text-slate-900">{copy.unavailableTitle}</h1>
        <p className="mx-auto max-w-md text-slate-500">{error}</p>
      </div>
    );
  }

  const {
    health,
    analytics,
    queueDepths,
    runtimeIdentity,
    onboardingFunnel,
    firstSessionSummary,
    confirmFunnel,
    repeatedUserSignal,
    breakerActive,
    latestEvents,
    promptRate,
    confirmRate,
    reportRate,
    totalSessions,
    topBehavioralFlag,
    topBehavioralSurface,
    summaryNotes,
  } = derived;

  return (
    <div className="mx-auto min-h-screen max-w-[1700px] animate-fade-in bg-[#fcfcfd] p-8">
      <div className="mb-10 flex flex-col gap-6 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <div className="mb-2 flex items-center gap-3">
            <div className="rounded-xl bg-slate-900 p-2.5 text-white shadow-2xl shadow-slate-900/20">
              <Activity size={22} />
            </div>
            <h1 className="text-3xl font-black tracking-tight text-slate-900">
              {copy.pageTitlePrefix} <span className="text-blue-600">{copy.pageTitleAccent}</span>
            </h1>
          </div>
          <p className="max-w-3xl text-sm font-medium text-slate-500">{copy.pageSubtitle}</p>
        </div>

        <div className="flex items-center gap-4">
          <div className="rounded-2xl border border-slate-200 bg-white px-5 py-2.5 shadow-sm">
            <p className="text-[10px] font-black uppercase tracking-[0.2em] text-slate-400">
              {copy.lastUpdated}
            </p>
            <p className="mt-1 text-xs font-bold text-slate-700">
              {formatTimestamp(health?.checked_at, locale, copy.unknown)}
            </p>
          </div>
          <button
            onClick={loadTelemetry}
            className={actionButtonStyles({ variant: "primary", className: "rounded-2xl" })}
          >
            <RefreshCcw size={14} />
            {copy.refresh}
          </button>
        </div>
      </div>

      <SectionCard
        title={copy.operatorSummary.title}
        subtitle={copy.operatorSummary.subtitle}
        actions={
          <div
            className={`rounded-2xl border px-4 py-2 text-[10px] font-black uppercase tracking-[0.2em] ${
              breakerActive
                ? "border-amber-100 bg-amber-50 text-amber-700"
                : "border-emerald-100 bg-emerald-50 text-emerald-700"
            }`}
          >
            {replaceTemplate(copy.operatorSummary.breakerStatus, {
              state: breakerActive ? copy.operatorSummary.breakerActive : copy.operatorSummary.breakerCalm,
            })}
          </div>
        }
      >
        <div className="grid grid-cols-1 gap-3 xl:grid-cols-2">
          {summaryNotes.map((note, index) => {
            const Icon = note.icon;
            return (
              <InsightPill key={`${note.text}-${index}`} tone={note.tone}>
                <div className="flex items-start gap-3">
                  <Icon size={16} className="mt-0.5 shrink-0" />
                  <span>{note.text}</span>
                </div>
              </InsightPill>
            );
          })}
        </div>
      </SectionCard>

      <div className="my-10 grid grid-cols-1 gap-6 md:grid-cols-2 xl:grid-cols-4">
        <TelemetryMetricCard
          title={copy.metrics.queueDepth.title}
          value={health?.cluster_observability?.total_queue_depth ?? 0}
          subtitle={replaceTemplate(copy.metrics.queueDepth.subtitle, {
            status: health?.status || copy.unknown,
          })}
          icon={<Layers3 size={18} className="text-blue-600" />}
          tone="blue"
        />
        <TelemetryMetricCard
          title={copy.metrics.visibleWorkers.title}
          value={health?.components?.celery?.worker_count ?? 0}
          subtitle={runtimeIdentity?.instance_id || copy.metrics.visibleWorkers.runtimeUnknown}
          icon={<BrainCircuit size={18} className="text-emerald-600" />}
          tone="green"
        />
        <TelemetryMetricCard
          title={copy.metrics.finnEvents.title}
          value={analytics?.event_count ?? 0}
          subtitle={replaceTemplate(copy.metrics.finnEvents.subtitle, {
            decisionReviews: analytics?.decision_review_usage_count ?? 0,
            priorityRuns: analytics?.priority_engine_usage_count ?? 0,
          })}
          icon={<CheckCircle2 size={18} className="text-slate-700" />}
          tone="slate"
        />
        <TelemetryMetricCard
          title={copy.metrics.behavioralBrake.title}
          value={analytics?.behavioral_intervention_seen_count ?? 0}
          subtitle={replaceTemplate(copy.metrics.behavioralBrake.subtitle, {
            acknowledgements: analytics?.behavioral_intervention_ack_count ?? 0,
          })}
          icon={<ShieldCheck size={18} className="text-amber-600" />}
          tone="amber"
        />
        <TelemetryMetricCard
          title={copy.metrics.newSessions.title}
          value={firstSessionSummary?.sessions_seen ?? 0}
          subtitle={replaceTemplate(copy.metrics.newSessions.subtitle, {
            multipleSessions: repeatedUserSignal?.users_with_multiple_sessions ?? 0,
          })}
          icon={<UserPlus size={18} className="text-amber-600" />}
          tone="amber"
        />
      </div>

      <div className="mb-10 grid grid-cols-1 gap-6 xl:grid-cols-2">
        <SectionCard title={copy.behavioralFlags.title} subtitle={copy.behavioralFlags.subtitle}>
          <div className="space-y-3">
            {(analytics?.top_behavioral_flags || []).length ? (
              analytics.top_behavioral_flags.map((item) => (
                <div key={item.flag} className="rounded-2xl border border-slate-100 bg-slate-50 px-4 py-4">
                  <div className="flex items-center justify-between gap-4">
                    <div>
                      <p className="text-sm font-semibold text-slate-800">
                        {toSentenceCase(item.flag, copy.unknown)}
                      </p>
                      <p className="mt-1 text-xs font-medium text-slate-500">
                        {topBehavioralFlag?.flag === item.flag && topBehavioralSurface?.surface
                          ? replaceTemplate(copy.behavioralFlags.mostVisibleOn, {
                              surface: topBehavioralSurface.surface,
                            })
                          : copy.behavioralFlags.recurringHint}
                      </p>
                    </div>
                    <span className="text-xs font-black uppercase tracking-[0.2em] text-amber-600">
                      {item.count}x
                    </span>
                  </div>
                </div>
              ))
            ) : (
              <div className="rounded-2xl border border-dashed border-slate-200 bg-slate-50 px-4 py-5 text-sm font-semibold text-slate-500">
                {copy.behavioralFlags.empty}
              </div>
            )}
          </div>
        </SectionCard>

        <SectionCard title={copy.behavioralSurfaces.title} subtitle={copy.behavioralSurfaces.subtitle}>
          <div className="space-y-3">
            {(analytics?.top_behavioral_surfaces || []).length ? (
              analytics.top_behavioral_surfaces.map((item) => (
                <div key={item.surface} className="rounded-2xl border border-slate-100 bg-slate-50 px-4 py-4">
                  <div className="flex items-center justify-between gap-4">
                    <div>
                      <p className="text-sm font-semibold text-slate-800">
                        {toSentenceCase(item.surface, copy.unknown)}
                      </p>
                      <p className="mt-1 text-xs font-medium text-slate-500">
                        {copy.behavioralSurfaces.hint}
                      </p>
                    </div>
                    <span className="text-xs font-black uppercase tracking-[0.2em] text-blue-600">
                      {item.count}x
                    </span>
                  </div>
                </div>
              ))
            ) : (
              <div className="rounded-2xl border border-dashed border-slate-200 bg-slate-50 px-4 py-5 text-sm font-semibold text-slate-500">
                {copy.behavioralSurfaces.empty}
              </div>
            )}
          </div>
        </SectionCard>
      </div>

      <div className="mb-10 grid grid-cols-1 gap-6 xl:grid-cols-[1.15fr_1fr]">
        <SectionCard title={copy.queueOverview.title} subtitle={copy.queueOverview.subtitle}>
          <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
            {queueDepths.map(([queueName, depth]) => (
              <div key={queueName} className="rounded-2xl border border-slate-100 bg-slate-50 px-4 py-4">
                <p className="text-[10px] font-black uppercase tracking-[0.2em] text-slate-400">{queueName}</p>
                <div className="mt-2 flex items-end justify-between gap-4">
                  <span
                    className={`text-2xl font-black tracking-tight ${
                      Number(depth) > 0 ? "text-amber-600" : "text-slate-900"
                    }`}
                  >
                    {depth}
                  </span>
                  <span className="text-xs font-semibold text-slate-500">
                    {replaceTemplate(copy.queueOverview.workers, {
                      count: health?.components?.celery?.workers_by_queue?.[queueName]?.length || 0,
                    })}
                  </span>
                </div>
              </div>
            ))}
          </div>
        </SectionCard>

        <SectionCard title={copy.firstSessionFunnel.title} subtitle={copy.firstSessionFunnel.subtitle}>
          <div className="grid grid-cols-1 gap-4">
            <FunnelRow
              label={copy.firstSessionFunnel.rows.dashboardReached.label}
              value={firstSessionSummary.sessions_reaching_dashboard ?? 0}
              total={totalSessions}
              helpText={copy.firstSessionFunnel.rows.dashboardReached.help}
              tone="blue"
            />
            <FunnelRow
              label={copy.firstSessionFunnel.rows.reportReached.label}
              value={firstSessionSummary.sessions_reaching_report ?? 0}
              total={totalSessions}
              helpText={copy.firstSessionFunnel.rows.reportReached.help}
              tone="green"
            />
            <FunnelRow
              label={copy.firstSessionFunnel.rows.promptSent.label}
              value={firstSessionSummary.sessions_with_prompt ?? 0}
              total={totalSessions}
              helpText={replaceTemplate(copy.firstSessionFunnel.rows.promptSent.help, { promptRate })}
              tone="amber"
            />
            <FunnelRow
              label={copy.firstSessionFunnel.rows.confirmReached.label}
              value={firstSessionSummary.sessions_with_confirm ?? 0}
              total={totalSessions}
              helpText={replaceTemplate(copy.firstSessionFunnel.rows.confirmReached.help, { confirmRate })}
              tone="blue"
            />
          </div>
          <div className="mt-5 flex flex-wrap items-center gap-3 text-sm font-semibold text-slate-700">
            <span>
              {replaceTemplate(copy.firstSessionFunnel.footer.sessionsSeen, {
                count: onboardingFunnel.sessions_seen ?? 0,
              })}
            </span>
            <ArrowRight size={14} className="text-slate-300" />
            <span>
              {replaceTemplate(copy.firstSessionFunnel.footer.stepClicked, {
                count: onboardingFunnel.step_clicked ?? 0,
              })}
            </span>
            <ArrowRight size={14} className="text-slate-300" />
            <span>
              {replaceTemplate(copy.firstSessionFunnel.footer.stepCompleted, {
                count: onboardingFunnel.step_completed ?? 0,
              })}
            </span>
            <ArrowRight size={14} className="text-slate-300" />
            <span>
              {replaceTemplate(copy.firstSessionFunnel.footer.dashboardActivated, {
                count: onboardingFunnel.dashboard_activated ?? 0,
              })}
            </span>
          </div>
        </SectionCard>
      </div>

      <div className="grid grid-cols-1 gap-6 xl:grid-cols-2">
        <SimpleList
          title={copy.topPrompts.title}
          subtitle={copy.topPrompts.subtitle}
          items={analytics?.top_prompts || []}
          emptyText={copy.topPrompts.empty}
          renderItem={(item, index) => (
            <div key={`${item.prompt}-${index}`} className="rounded-2xl border border-slate-100 bg-slate-50 px-4 py-4">
              <div className="flex items-start justify-between gap-4">
                <p className="text-sm font-semibold text-slate-800">{item.prompt}</p>
                <span className="text-xs font-black uppercase tracking-[0.2em] text-blue-600">{item.count}x</span>
              </div>
            </div>
          )}
        />

        <SimpleList
          title={copy.topScreens.title}
          subtitle={copy.topScreens.subtitle}
          items={analytics?.top_screens || []}
          emptyText={copy.topScreens.empty}
          renderItem={(item, index) => (
            <div key={`${item.page}-${index}`} className="rounded-2xl border border-slate-100 bg-slate-50 px-4 py-4">
              <div className="flex items-center justify-between gap-4">
                <div>
                  <p className="text-sm font-semibold text-slate-800">{item.page}</p>
                  <p className="text-[10px] font-black uppercase tracking-[0.2em] text-slate-400">
                    {copy.topScreens.label}
                  </p>
                </div>
                <span className="text-xs font-black uppercase tracking-[0.2em] text-blue-600">{item.count}x</span>
              </div>
            </div>
          )}
        />

        <SimpleList
          title={copy.firstLandings.title}
          subtitle={copy.firstLandings.subtitle}
          items={analytics?.top_first_screens || []}
          emptyText={copy.firstLandings.empty}
          renderItem={(item, index) => (
            <div key={`${item.page}-${index}`} className="rounded-2xl border border-slate-100 bg-slate-50 px-4 py-4">
              <div className="flex items-center justify-between gap-4">
                <div>
                  <p className="text-sm font-semibold text-slate-800">{item.page}</p>
                  <p className="text-[10px] font-black uppercase tracking-[0.2em] text-slate-400">
                    {copy.firstLandings.label}
                  </p>
                </div>
                <span className="text-xs font-black uppercase tracking-[0.2em] text-blue-600">{item.count}x</span>
              </div>
            </div>
          )}
        />

        <SectionCard title={copy.confirmCtaOverview.title} subtitle={copy.confirmCtaOverview.subtitle}>
          <div className="grid grid-cols-3 gap-4">
            {[
              [copy.confirmCtaOverview.stats.opened, confirmFunnel.opened ?? 0],
              [copy.confirmCtaOverview.stats.confirmed, confirmFunnel.confirmed ?? 0],
              [copy.confirmCtaOverview.stats.canceled, confirmFunnel.canceled ?? 0],
            ].map(([label, value]) => (
              <div key={label} className="rounded-2xl border border-slate-100 bg-slate-50 px-4 py-4 text-center">
                <p className="text-[10px] font-black uppercase tracking-[0.2em] text-slate-400">{label}</p>
                <p className="mt-2 text-2xl font-black tracking-tight text-slate-900">{value}</p>
              </div>
            ))}
          </div>

          <div className="mt-5 grid grid-cols-2 gap-4">
            <div className="rounded-2xl border border-slate-100 bg-slate-50 px-4 py-4">
              <div className="flex items-center gap-2 text-[10px] font-black uppercase tracking-[0.2em] text-slate-400">
                <BrainCircuit size={14} />
                {copy.confirmCtaOverview.decisionReview}
              </div>
              <p className="mt-2 text-2xl font-black tracking-tight text-slate-900">
                {analytics?.decision_review_usage_count ?? 0}
              </p>
            </div>
            <div className="rounded-2xl border border-slate-100 bg-slate-50 px-4 py-4">
              <div className="flex items-center gap-2 text-[10px] font-black uppercase tracking-[0.2em] text-slate-400">
                <Clock3 size={14} />
                {copy.confirmCtaOverview.priorityEngine}
              </div>
              <p className="mt-2 text-2xl font-black tracking-tight text-slate-900">
                {analytics?.priority_engine_usage_count ?? 0}
              </p>
            </div>
          </div>

          <div className="mt-5 grid grid-cols-1 gap-3">
            {(analytics?.top_cta_actions || []).length ? (
              analytics.top_cta_actions.map((item, index) => (
                <div key={`${item.action}-${index}`} className="rounded-2xl border border-slate-100 bg-slate-50 px-4 py-4">
                  <div className="flex items-center justify-between gap-4">
                    <div>
                      <p className="text-sm font-semibold text-slate-800">{item.action}</p>
                      <p className="text-[10px] font-black uppercase tracking-[0.2em] text-slate-400">
                        {copy.confirmCtaOverview.ctaAction}
                      </p>
                    </div>
                    <span className="text-xs font-black uppercase tracking-[0.2em] text-blue-600">{item.count}x</span>
                  </div>
                </div>
              ))
            ) : (
              <div className="rounded-2xl border border-dashed border-slate-200 bg-slate-50 px-4 py-5 text-sm font-semibold text-slate-500">
                {copy.confirmCtaOverview.empty}
              </div>
            )}
          </div>
        </SectionCard>
      </div>

      <div className="mt-6">
        <SimpleList
          title={latestEventCopy.title}
          subtitle={latestEventCopy.subtitle}
          items={latestEvents.slice(0, 6)}
          emptyText={latestEventCopy.empty}
          renderItem={(event, index) => (
            <LatestEventCard
              key={`${event.timestamp}-${index}`}
              event={event}
              copy={latestEventCopy}
              locale={locale}
            />
          )}
        />
      </div>
    </div>
  );
}
