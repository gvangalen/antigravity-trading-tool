"use client";

import React, { useCallback, useRef, useState } from "react";
import {
  Activity,
  ArrowRight,
  BrainCircuit,
  CheckCircle2,
  Clock3,
  Layers3,
  RefreshCcw,
  ShieldCheck,
  UserPlus,
  Users,
} from "lucide-react";

import { fetchAdminTelemetry } from "@/lib/api/admin";
import { useVisibilityPolling } from "@/hooks/useVisibilityPolling";

function formatTimestamp(isoValue) {
  if (!isoValue) return "Onbekend";
  const date = new Date(isoValue);
  if (Number.isNaN(date.getTime())) return "Onbekend";
  return `${date.toLocaleDateString("nl-NL")} ${date.toLocaleTimeString("nl-NL")}`;
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
          {subtitle ? (
            <p className="mt-2 text-xs font-semibold opacity-80">{subtitle}</p>
          ) : null}
        </div>
        <div className="rounded-2xl bg-white/70 p-3 shadow-sm">{icon}</div>
      </div>
    </div>
  );
}

function SimpleList({ title, items, renderItem, emptyText }) {
  return (
    <div className="rounded-[28px] border border-slate-100 bg-white p-6 shadow-sm">
      <h3 className="text-sm font-black uppercase tracking-[0.2em] text-slate-500">{title}</h3>
      <div className="mt-4 space-y-3">
        {items?.length ? (
          items.map(renderItem)
        ) : (
          <div className="rounded-2xl border border-dashed border-slate-200 bg-slate-50 px-4 py-5 text-sm font-semibold text-slate-500">
            {emptyText}
          </div>
        )}
      </div>
    </div>
  );
}

export default function AdminTelemetryPage() {
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
      setError("Telemetry kon niet worden geladen. Controleer admin-toegang of runtime health.");
    } finally {
      setLoading(false);
      isFetchingRef.current = false;
    }
  }, []);

  useVisibilityPolling(loadTelemetry, {
    intervalMs: 15000,
    backgroundIntervalMs: 60000,
    runImmediately: true,
  });

  if (loading) {
    return (
      <div className="p-10 flex flex-col items-center justify-center min-h-[60vh]">
        <div className="w-12 h-12 border-4 border-blue-600/20 border-t-blue-600 rounded-full animate-spin mb-4" />
        <p className="text-slate-400 font-bold uppercase tracking-widest text-xs">
          Telemetry wordt verzameld...
        </p>
      </div>
    );
  }

  if (error || !telemetry) {
    return (
      <div className="p-10 text-center">
        <div className="inline-flex p-4 bg-rose-50 rounded-full text-rose-500 mb-4">
          <ShieldCheck size={32} />
        </div>
        <h1 className="text-2xl font-black text-slate-900 mb-2">Telemetry niet beschikbaar</h1>
        <p className="text-slate-500 max-w-md mx-auto">{error}</p>
      </div>
    );
  }

  const { health, analytics, openaiRuntime } = telemetry;
  const queueDepths = Object.entries(health?.components?.broker?.queue_depths || {});
  const runtimeIdentity = health?.runtime_identity || {};
  const onboardingFunnel = analytics?.onboarding_funnel || {};
  const firstSessionSummary = analytics?.first_session_summary || {};
  const confirmFunnel = analytics?.confirm_funnel || {};
  const repeatedUserSignal = analytics?.repeated_user_signal || {};
  const breakerActive = Boolean(
    openaiRuntime?.breaker_active ??
    openaiRuntime?.quota_breaker_active ??
    openaiRuntime?.quota_circuit_breaker_active
  );

  return (
    <div className="p-8 max-w-[1700px] mx-auto bg-[#fcfcfd] min-h-screen animate-fade-in">
      <div className="flex flex-col lg:flex-row lg:items-end justify-between gap-6 mb-10">
        <div>
          <div className="flex items-center gap-3 mb-2">
            <div className="p-2.5 bg-slate-900 text-white rounded-xl shadow-2xl shadow-slate-900/20">
              <Activity size={22} />
            </div>
            <h1 className="text-3xl font-black text-slate-900 tracking-tight">
              Platform <span className="text-blue-600">Telemetry</span>
            </h1>
          </div>
          <p className="text-slate-500 font-medium max-w-3xl text-sm">
            Live queue-dieptes, FINN-usage en first-session gedrag in één operator view.
          </p>
        </div>

        <div className="flex items-center gap-4">
          <div className="px-5 py-2.5 bg-white border border-slate-200 rounded-2xl shadow-sm">
            <p className="text-[10px] font-black uppercase tracking-[0.2em] text-slate-400">Laatste update</p>
            <p className="mt-1 text-xs font-bold text-slate-700">{formatTimestamp(health?.checked_at)}</p>
          </div>
          <button
            onClick={loadTelemetry}
            className="px-6 py-3 bg-blue-600 text-white rounded-2xl font-black text-[10px] uppercase tracking-widest hover:bg-blue-700 transition-all shadow-lg shadow-blue-600/20 flex items-center gap-2 active:scale-95"
          >
            <RefreshCcw size={14} />
            Ververs telemetry
          </button>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-6 mb-10">
        <TelemetryMetricCard
          title="Queue depth"
          value={health?.cluster_observability?.total_queue_depth ?? 0}
          subtitle={`Status: ${health?.status || "unknown"}`}
          icon={<Layers3 size={18} className="text-blue-600" />}
          tone="blue"
        />
        <TelemetryMetricCard
          title="Workers zichtbaar"
          value={health?.components?.celery?.worker_count ?? 0}
          subtitle={runtimeIdentity?.instance_id || "runtime onbekend"}
          icon={<BrainCircuit size={18} className="text-emerald-600" />}
          tone="green"
        />
        <TelemetryMetricCard
          title="FINN events"
          value={analytics?.event_count ?? 0}
          subtitle={`${analytics?.decision_review_usage_count ?? 0} decision reviews · ${analytics?.priority_engine_usage_count ?? 0} priority runs`}
          icon={<CheckCircle2 size={18} className="text-slate-700" />}
          tone="slate"
        />
        <TelemetryMetricCard
          title="Nieuwe sessies"
          value={firstSessionSummary?.sessions_seen ?? 0}
          subtitle={`Meerdere sessies: ${repeatedUserSignal?.users_with_multiple_sessions ?? 0}`}
          icon={<UserPlus size={18} className="text-amber-600" />}
          tone="amber"
        />
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-[1.15fr_1fr] gap-6 mb-10">
        <div className="rounded-[28px] border border-slate-100 bg-white p-6 shadow-sm">
          <div className="flex items-center justify-between gap-4">
            <div>
              <h2 className="text-sm font-black uppercase tracking-[0.2em] text-slate-500">Queue-overzicht</h2>
              <p className="mt-1 text-sm font-semibold text-slate-500">
                Zo zie je meteen of productie dichtslibt of netjes leegloopt.
              </p>
            </div>
            <div className={`px-4 py-2 rounded-2xl text-[10px] font-black uppercase tracking-[0.2em] ${breakerActive ? "bg-amber-50 text-amber-700 border border-amber-100" : "bg-emerald-50 text-emerald-700 border border-emerald-100"}`}>
              OpenAI breaker {breakerActive ? "actief" : "rustig"}
            </div>
          </div>
          <div className="mt-5 grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
            {queueDepths.map(([queueName, depth]) => (
              <div key={queueName} className="rounded-2xl border border-slate-100 bg-slate-50 px-4 py-4">
                <p className="text-[10px] font-black uppercase tracking-[0.2em] text-slate-400">{queueName}</p>
                <div className="mt-2 flex items-end justify-between gap-4">
                  <span className={`text-2xl font-black tracking-tight ${Number(depth) > 0 ? "text-amber-600" : "text-slate-900"}`}>
                    {depth}
                  </span>
                  <span className="text-xs font-semibold text-slate-500">
                    {health?.components?.celery?.workers_by_queue?.[queueName]?.length || 0} workers
                  </span>
                </div>
              </div>
            ))}
          </div>
        </div>

        <div className="rounded-[28px] border border-slate-100 bg-white p-6 shadow-sm">
          <h2 className="text-sm font-black uppercase tracking-[0.2em] text-slate-500">First-session funnel</h2>
          <p className="mt-1 text-sm font-semibold text-slate-500">
            Hier zien we waar nieuwe testers landen, wat ze afronden en of ze Finn al raken.
          </p>
          <div className="mt-5 grid grid-cols-2 gap-4">
            {[
              ["Sessies gezien", firstSessionSummary.sessions_seen ?? 0],
              ["Met prompt", firstSessionSummary.sessions_with_prompt ?? 0],
              ["Met confirm", firstSessionSummary.sessions_with_confirm ?? 0],
              ["Dashboard bereikt", firstSessionSummary.sessions_reaching_dashboard ?? 0],
              ["Report bereikt", firstSessionSummary.sessions_reaching_report ?? 0],
              ["Onboarding voltooid", onboardingFunnel.completed ?? 0],
            ].map(([label, value]) => (
              <div key={label} className="rounded-2xl border border-slate-100 bg-slate-50 px-4 py-4">
                <p className="text-[10px] font-black uppercase tracking-[0.2em] text-slate-400">{label}</p>
                <p className="mt-2 text-2xl font-black tracking-tight text-slate-900">{value}</p>
              </div>
            ))}
          </div>
          <div className="mt-5 rounded-2xl border border-slate-100 bg-slate-50 p-4">
            <div className="flex items-center gap-3 text-xs font-black uppercase tracking-[0.2em] text-slate-500">
              <Users size={14} />
              Onboarding stap-flow
            </div>
            <div className="mt-4 flex flex-wrap items-center gap-3 text-sm font-semibold text-slate-700">
              <span>{onboardingFunnel.sessions_seen ?? 0} sessies</span>
              <ArrowRight size={14} className="text-slate-300" />
              <span>{onboardingFunnel.step_clicked ?? 0} stapkliks</span>
              <ArrowRight size={14} className="text-slate-300" />
              <span>{onboardingFunnel.step_completed ?? 0} afgerond</span>
              <ArrowRight size={14} className="text-slate-300" />
              <span>{onboardingFunnel.dashboard_activated ?? 0} dashboard activaties</span>
            </div>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
        <SimpleList
          title="Top FINN prompts"
          items={analytics?.top_prompts || []}
          emptyText="Nog geen FINN prompttelemetrie in deze runtime."
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
          title="Top screens & first landings"
          items={[
            ...(analytics?.top_screens || []).slice(0, 5).map((item) => ({ ...item, kind: "screen" })),
            ...(analytics?.top_first_screens || []).slice(0, 5).map((item) => ({ ...item, kind: "first" })),
          ]}
          emptyText="Nog geen screen-telemetry in deze runtime."
          renderItem={(item, index) => (
            <div key={`${item.kind}-${item.page}-${index}`} className="rounded-2xl border border-slate-100 bg-slate-50 px-4 py-4">
              <div className="flex items-center justify-between gap-4">
                <div>
                  <p className="text-sm font-semibold text-slate-800">{item.page}</p>
                  <p className="text-[10px] font-black uppercase tracking-[0.2em] text-slate-400">
                    {item.kind === "first" ? "Eerste landing" : "Schermgebruik"}
                  </p>
                </div>
                <span className="text-xs font-black uppercase tracking-[0.2em] text-blue-600">{item.count}x</span>
              </div>
            </div>
          )}
        />

        <SimpleList
          title="CTA's & confirm funnel"
          items={analytics?.top_cta_actions || []}
          emptyText="Nog geen CTA-kliks gezien in deze runtime."
          renderItem={(item, index) => (
            <div key={`${item.action}-${index}`} className="rounded-2xl border border-slate-100 bg-slate-50 px-4 py-4">
              <div className="flex items-center justify-between gap-4">
                <div>
                  <p className="text-sm font-semibold text-slate-800">{item.action}</p>
                  <p className="text-[10px] font-black uppercase tracking-[0.2em] text-slate-400">CTA actie</p>
                </div>
                <span className="text-xs font-black uppercase tracking-[0.2em] text-blue-600">{item.count}x</span>
              </div>
            </div>
          )}
        />

        <div className="rounded-[28px] border border-slate-100 bg-white p-6 shadow-sm">
          <h3 className="text-sm font-black uppercase tracking-[0.2em] text-slate-500">Confirm & prompt readout</h3>
          <div className="mt-4 grid grid-cols-3 gap-4">
            {[
              ["Opened", confirmFunnel.opened ?? 0],
              ["Confirmed", confirmFunnel.confirmed ?? 0],
              ["Canceled", confirmFunnel.canceled ?? 0],
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
                Decision review
              </div>
              <p className="mt-2 text-2xl font-black tracking-tight text-slate-900">
                {analytics?.decision_review_usage_count ?? 0}
              </p>
            </div>
            <div className="rounded-2xl border border-slate-100 bg-slate-50 px-4 py-4">
              <div className="flex items-center gap-2 text-[10px] font-black uppercase tracking-[0.2em] text-slate-400">
                <Clock3 size={14} />
                Priority engine
              </div>
              <p className="mt-2 text-2xl font-black tracking-tight text-slate-900">
                {analytics?.priority_engine_usage_count ?? 0}
              </p>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
