"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { assistantChat } from "@/lib/api/ai";
import { trackAssistantEvent } from "@/lib/api/assistantAnalytics";
import {
  AlertCircle,
  ArrowRight,
  Brain,
  CheckCircle2,
  RefreshCw,
  Shield,
  ShieldAlert,
  ShieldCheck,
  Target,
  X,
  XCircle,
} from "lucide-react";
import { useTranslation } from "@/app/providers/I18nProvider";
import { formatNumber, getIntlLocale } from "@/lib/i18n";

const fmt = (value, locale, digits = 2) => {
  const num = Number(value);
  if (!Number.isFinite(num)) return "—";
  return num.toLocaleString(getIntlLocale(locale), {
    minimumFractionDigits: 0,
    maximumFractionDigits: digits,
  });
};

const titleCase = (value) =>
  String(value || "")
    .replaceAll("_", " ")
    .trim()
    .replace(/\b\w/g, (char) => char.toUpperCase());

const badgeTone = (status) => {
  if (status === "blocked") return "bg-rose-100 text-rose-700 border-rose-200";
  if (status === "live") return "bg-blue-100 text-blue-700 border-blue-200";
  if (status === "paper") return "bg-slate-100 text-slate-600 border-slate-200";
  return "bg-emerald-100 text-emerald-700 border-emerald-200";
};

const detailValue = (value, labels = {}) => {
  if (value === null || value === undefined || value === "") return "—";
  if (typeof value === "boolean") return value ? labels.booleanTrue : labels.booleanFalse;
  return String(value);
};

const humanizeBehaviorLabel = (flag, fallbackLabel = "", labels = {}) =>
  fallbackLabel || labels[String(flag || "").trim()] || String(flag || "").replaceAll("_", " ");

const extractBehavioralFriction = (preview = {}, review = null, adherence = null, behaviorLabels = {}) => {
  const direct =
    preview?.pending_behavioral_memory_friction ||
    preview?.memory_friction ||
    preview?.behavioral_memory_friction ||
    review?.pending_behavioral_memory_friction ||
    adherence?.pending_behavioral_memory_friction ||
    null;
  if (direct && typeof direct === "object") return direct;
  const alignment =
    review?.profile_habit_alignment?.primary_alignment ||
    adherence?.profile_habit_alignment?.primary_alignment ||
    preview?.profile_habit_alignment?.primary_alignment ||
    null;
  if (alignment) {
      return {
        source: "profile_habit_alignment",
        message: alignment.behavioral_cost || alignment.summary,
        safe_alternative: alignment.recommended_rule,
        label: humanizeBehaviorLabel(alignment.flag, alignment.label, behaviorLabels),
      };
  }
  return null;
};

function DetailRow({ label, value, emphasis = false, labels }) {
  return (
    <div className="flex items-center justify-between gap-4 rounded-xl border border-slate-100 bg-white px-3 py-2.5 dark:border-slate-800 dark:bg-slate-950/40">
      <span className="text-[10px] font-black uppercase tracking-widest text-slate-400 dark:text-slate-500">
        {label}
      </span>
      <span className={`text-right text-[11px] font-black ${emphasis ? "text-slate-900 dark:text-white" : "text-slate-700 dark:text-slate-200"}`}>
        {detailValue(value, labels)}
      </span>
    </div>
  );
}

function GuardrailList({ title, items = [], blocked = false, copy, locale }) {
  if (!Array.isArray(items) || items.length === 0) return null;

  return (
    <div className="rounded-2xl border border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-950/35 overflow-hidden">
      <div className="flex items-center justify-between gap-3 border-b border-slate-100 bg-slate-50 px-4 py-3 dark:border-slate-800 dark:bg-slate-900/70">
        <span className="text-[10px] font-black uppercase tracking-widest text-slate-500 dark:text-slate-400">
          {title}
        </span>
        <span className={`rounded-full border px-2 py-0.5 text-[8px] font-black uppercase tracking-widest ${blocked ? "border-rose-200 bg-rose-100 text-rose-700" : "border-emerald-200 bg-emerald-100 text-emerald-700"}`}>
          {blocked ? copy.actionRequired : copy.green}
        </span>
      </div>
      <div className="space-y-2 px-4 py-4">
        {items.map((item, index) => {
          const ok = item?.ok !== false;
          const code = item?.code || item?.type || `check-${index + 1}`;
          const primaryValue =
            item?.message ||
            item?.reason ||
            item?.summary ||
            item?.status ||
            item?.symbol ||
            (Number.isFinite(Number(item?.projected_pct)) ? `${fmt(item.projected_pct, locale)}%` : null) ||
            (Number.isFinite(Number(item?.limit_eur)) ? `${copy.limitPrefix} ${fmt(item.limit_eur, locale)}` : null);
          return (
            <div key={`${code}-${index}`} className="rounded-xl border border-slate-100 bg-slate-50/70 px-3 py-3 dark:border-slate-800 dark:bg-slate-900/60">
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <div className="text-[10px] font-black uppercase tracking-widest text-slate-700 dark:text-slate-200">
                    {titleCase(code)}
                  </div>
                  {primaryValue && (
                    <p className="mt-1 text-[11px] font-semibold leading-relaxed text-slate-600 dark:text-slate-300">
                      {primaryValue}
                    </p>
                  )}
                </div>
                <span className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[8px] font-black uppercase tracking-widest ${ok ? "bg-emerald-100 text-emerald-700" : "bg-rose-100 text-rose-700"}`}>
                  {ok ? <CheckCircle2 size={12} /> : <XCircle size={12} />}
                  {ok ? copy.ok : copy.blocked}
                </span>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

export default function OrderPreviewModal({
  preview,
  onConfirm,
  onAcknowledgeSetupBlock,
  onCancel,
  onRefresh,
  loading = false,
  currencySymbol = "€",
  botName = "Bot",
}) {
  const { t, locale } = useTranslation();
  const copy = t?.botPage?.orderPreview || {};
  const behaviorLabels = copy.behaviorLabels || {};
  const detailLabels = { booleanTrue: copy.booleanTrue, booleanFalse: copy.booleanFalse };
  const [seconds, setSeconds] = useState(10);
  const [liveIntentConfirmed, setLiveIntentConfirmed] = useState(false);
  const [finnReview, setFinnReview] = useState(null);
  const [finnAdherence, setFinnAdherence] = useState(null);
  const [finnLoading, setFinnLoading] = useState(false);
  const [finnError, setFinnError] = useState("");
  const telemetryKeyRef = useRef("");
  const ackTelemetryKeyRef = useRef("");

  useEffect(() => {
    if (loading) {
      setSeconds(10);
      return;
    }

    const timer = setInterval(() => {
      setSeconds((prev) => {
        if (prev <= 1) {
          onRefresh?.();
          return 10;
        }
        return prev - 1;
      });
    }, 1000);

    return () => clearInterval(timer);
  }, [onRefresh, loading]);

  useEffect(() => {
    setLiveIntentConfirmed(false);
  }, [preview?.trace_id, preview?.code, preview?.price, preview?.quantity]);

  useEffect(() => {
    let cancelled = false;

    async function loadFinnGovernance() {
      if (!preview?.symbol || !preview?.bot_id) {
        setFinnReview(null);
        setFinnAdherence(null);
        setFinnError("");
        return;
      }

      setFinnLoading(true);
      setFinnError("");
      try {
        const context = {
          page: "/bot",
          page_type: "Bots",
          symbol: preview.symbol,
          bot_id: preview.bot_id,
          strategy_id: preview.strategy_id || null,
          setup_id: preview.setup_id || null,
        };
        const orderSummary = `${preview.side === "buy" ? copy.buy : copy.sell} ${preview.symbol} ${copy.orderSummaryFor} ${fmt(preview.notional_eur ?? preview.gross_eur ?? 0, locale)} ${currencySymbol}`;
        const response = await assistantChat(
          `${copy.reviewPrompt.replace("{order}", orderSummary)} ${copy.planCheckPrompt.replace("{order}", orderSummary)}`,
          context,
          []
        );
        if (cancelled) return;
        const analysis = response?.analysis || response?.state?.analysis || null;
        setFinnReview(analysis);
        setFinnAdherence(analysis);
      } catch (error) {
        if (cancelled) return;
        console.error("Finn governance preview failed:", error);
        setFinnError(copy.finnLoadError);
      } finally {
        if (!cancelled) setFinnLoading(false);
      }
    }

    loadFinnGovernance();
    return () => {
      cancelled = true;
    };
  }, [copy.buy, copy.finnLoadError, copy.orderSummaryFor, copy.sell, currencySymbol, locale, preview?.bot_id, preview?.strategy_id, preview?.setup_id, preview?.symbol, preview?.side, preview?.notional_eur, preview?.gross_eur]);

  const isLive = Boolean(preview?.is_live);
  const isLivePreflight = preview?.mode === "manual_order_preflight" || isLive;
  const isBlocked = Boolean(preview?.blocked || preview?.ok === false);
  const requiresSetupBlockAck = preview?.code === "LIVE_SETUP_BLOCK_ACK_REQUIRED";
  const isBuy = preview?.side === "buy";
  const orderAmount = preview?.gross_eur ?? preview?.notional_eur ?? (Number(preview?.quantity || 0) * Number(preview?.price || 0));
  const feeRate = Number(preview?.fee_rate);
  const guardrailChecks = Array.isArray(preview?.live_order_guardrails?.checks) ? preview.live_order_guardrails.checks : [];
  const hasLiveGuardrails = guardrailChecks.length > 0;
  const decisionFreshness = preview?.decision_freshness || {};
  const livePreflight = preview?.live_preflight || {};
  const liveMarketPrice = preview?.live_market_price || {};
  const readinessStatus = isBlocked ? "blocked" : isLive ? "live" : "paper";
  const consequenceSummary = useMemo(() => {
    const rows = [
      { id: "path", label: copy.pathLabel, value: isLive ? copy.liveManualOrder : copy.paperPreview },
      { id: "bot", label: copy.botLabel, value: botName },
      { id: "asset", label: copy.assetLabel, value: preview?.symbol },
      { id: "side", label: copy.sideLabel, value: isBuy ? copy.buy : copy.sell },
      { id: "price", label: copy.priceLabel, value: `${currencySymbol} ${fmt(preview?.price, locale)}` },
      { id: "quantity", label: copy.quantityLabel, value: `${fmt(preview?.quantity, locale, 8)} ${preview?.symbol || ""}`.trim() },
      { id: "orderValue", label: copy.orderValueLabel, value: `${currencySymbol} ${fmt(orderAmount, locale)}` },
    ];
    if (!isLive && Number.isFinite(feeRate)) {
      rows.push({ id: "fee", label: copy.feeLabel, value: `${formatNumber(feeRate * 100, locale, { minimumFractionDigits: 0, maximumFractionDigits: 2 })}%` });
    }
    if (isLive) {
      rows.push({ id: "exchangeEffect", label: copy.exchangeEffectLabel, value: isBlocked ? copy.noOrderPossible : copy.confirmPlacesLiveOrder });
    } else {
      rows.push({ id: "exchangeEffect", label: copy.exchangeEffectLabel, value: copy.paperConfirmEffect });
    }
    return rows;
  }, [botName, copy.assetLabel, copy.botLabel, copy.buy, copy.confirmPlacesLiveOrder, copy.exchangeEffectLabel, copy.feeLabel, copy.liveManualOrder, copy.noOrderPossible, copy.orderValueLabel, copy.paperConfirmEffect, copy.paperPreview, copy.pathLabel, copy.priceLabel, copy.quantityLabel, copy.sell, copy.sideLabel, currencySymbol, feeRate, isBlocked, isBuy, isLive, locale, orderAmount, preview?.price, preview?.quantity, preview?.symbol]);

  const liveContextRows = [
    livePreflight?.token ? [copy.preflightTokenLabel, copy.valid] : null,
    Number.isFinite(Number(livePreflight?.age_minutes)) ? [copy.preflightAgeLabel, `${livePreflight.age_minutes} ${copy.minutesShort}`] : null,
    decisionFreshness?.status ? [copy.decisionContextLabel, decisionFreshness.status] : null,
    Number.isFinite(Number(liveMarketPrice?.age_seconds)) ? [copy.marketPriceAgeLabel, `${liveMarketPrice.age_seconds} ${copy.secondsShort}`] : null,
    liveMarketPrice?.market_timestamp ? [copy.marketTimestampLabel, liveMarketPrice.market_timestamp] : null,
  ].filter(Boolean);
  const behavioralFriction = extractBehavioralFriction(preview, finnReview, finnAdherence, behaviorLabels);

  useEffect(() => {
    if (!behavioralFriction?.message) return;
    const nextKey = [
      preview?.trace_id || preview?.bot_id || preview?.symbol || "preflight",
      behavioralFriction?.label || behavioralFriction?.source || "friction",
      behavioralFriction?.message || "",
    ].join(":");
    if (telemetryKeyRef.current === nextKey) return;
    telemetryKeyRef.current = nextKey;
    trackAssistantEvent({
      event_name: "behavioral_intervention_seen",
      page: "/bot",
      surface: isLive ? "live_preflight" : "order_preview",
      asset: preview?.symbol || null,
      flow_type: "behavioral_intervention",
      action_type: isLive ? "preflight_friction_visible" : "preview_friction_visible",
      decision_id: preview?.decision_id || null,
      bot_id: preview?.bot_id || null,
      trace_id: preview?.trace_id || null,
      next_best_action: behavioralFriction?.safe_alternative || null,
      metadata: {
        behavior_flag:
          finnReview?.profile_habit_alignment?.primary_alignment?.flag ||
          finnAdherence?.profile_habit_alignment?.primary_alignment?.flag ||
          preview?.profile_habit_alignment?.primary_alignment?.flag ||
          null,
        behavior_label: behavioralFriction?.label || null,
        source: behavioralFriction?.source || null,
      },
    });
  }, [behavioralFriction, finnAdherence?.profile_habit_alignment, finnReview?.profile_habit_alignment, isLive, preview?.bot_id, preview?.decision_id, preview?.symbol, preview?.trace_id, preview?.profile_habit_alignment]);

  useEffect(() => {
    if (!liveIntentConfirmed || !behavioralFriction?.message || !isLive) return;
    const nextKey = `${preview?.trace_id || preview?.bot_id || "live"}:${behavioralFriction?.label || behavioralFriction?.source || "ack"}`;
    if (ackTelemetryKeyRef.current === nextKey) return;
    ackTelemetryKeyRef.current = nextKey;
    trackAssistantEvent({
      event_name: "behavioral_intervention_acknowledged",
      page: "/bot",
      surface: "live_preflight",
      asset: preview?.symbol || null,
      flow_type: "behavioral_intervention",
      action_type: "live_behavioral_ack",
      decision_id: preview?.decision_id || null,
      bot_id: preview?.bot_id || null,
      trace_id: preview?.trace_id || null,
      next_best_action: behavioralFriction?.safe_alternative || null,
      metadata: {
        behavior_flag:
          finnReview?.profile_habit_alignment?.primary_alignment?.flag ||
          finnAdherence?.profile_habit_alignment?.primary_alignment?.flag ||
          preview?.profile_habit_alignment?.primary_alignment?.flag ||
          null,
        behavior_label: behavioralFriction?.label || null,
        source: behavioralFriction?.source || null,
      },
    });
  }, [behavioralFriction, finnAdherence?.profile_habit_alignment, finnReview?.profile_habit_alignment, isLive, liveIntentConfirmed, preview?.bot_id, preview?.decision_id, preview?.symbol, preview?.trace_id, preview?.profile_habit_alignment]);

  const canConfirm = !loading && !isBlocked && (!isLive || liveIntentConfirmed);
  const primaryButtonLabel = loading
    ? copy.busy
    : isLive
      ? copy.placeLiveOrder
      : copy.confirmOrder;

  if (!preview) return null;

  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center bg-slate-950/65 p-4 backdrop-blur-sm animate-in fade-in duration-200">
      <div className="flex max-h-[90vh] w-full max-w-3xl flex-col overflow-hidden rounded-[2rem] border border-slate-200 bg-slate-50 shadow-2xl dark:border-slate-800 dark:bg-[#06101f] animate-in zoom-in-95 duration-200">
        <div className="flex items-start justify-between gap-4 border-b border-slate-200 bg-white px-6 py-5 dark:border-slate-800 dark:bg-slate-950/70">
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <span className={`inline-flex items-center gap-1 rounded-full border px-2.5 py-1 text-[9px] font-black uppercase tracking-widest ${badgeTone(readinessStatus)}`}>
                {isBlocked ? <ShieldAlert size={12} /> : isLive ? <ShieldCheck size={12} /> : <Shield size={12} />}
                {isBlocked ? (preview?.code || copy.blocked) : isLive ? copy.livePreflight : copy.orderPreview}
              </span>
              {isLivePreflight && !isBlocked && (
                <span className="inline-flex items-center gap-1 rounded-full border border-emerald-200 bg-emerald-100 px-2.5 py-1 text-[9px] font-black uppercase tracking-widest text-emerald-700">
                  <CheckCircle2 size={12} />
                  {copy.noOrderPlaced}
                </span>
              )}
            </div>
            <h3 className="mt-3 text-2xl font-black tracking-tight text-slate-950 dark:text-white">
              {isBlocked ? copy.executionBlocked : isLive ? copy.liveExecutionCheck : copy.orderPreview}
            </h3>
            <p className="mt-2 max-w-2xl text-sm font-semibold leading-relaxed text-slate-600 dark:text-slate-300">
              {preview?.message || (isLive ? copy.livePreflightDescription : copy.previewDescription)}
            </p>
          </div>
          <button
            onClick={onCancel}
            className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full border border-slate-200 bg-white text-slate-500 transition hover:bg-slate-100 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-300 dark:hover:bg-slate-800"
          >
            <X size={18} />
          </button>
        </div>

        <div className="overflow-y-auto px-6 py-6">
          <div className="grid gap-6 lg:grid-cols-[1.25fr_0.95fr]">
            <div className="space-y-6">
              <div className="rounded-[1.5rem] border border-slate-200 bg-white p-5 dark:border-slate-800 dark:bg-slate-950/45">
                <div className="flex items-start justify-between gap-4">
                  <div className="flex items-center gap-3">
                    <div className={`flex h-12 w-12 items-center justify-center rounded-2xl text-white shadow-sm ${isBuy ? "bg-blue-600" : "bg-rose-600"}`}>
                      {isBuy ? <RefreshCw className="animate-spin-slow" size={22} /> : <ArrowRight size={22} />}
                    </div>
                    <div>
                      <div className={`text-[11px] font-black uppercase tracking-widest ${isBuy ? "text-blue-600" : "text-rose-600"}`}>
                    {isBuy ? copy.buy : copy.sell}
                      </div>
                      <div className="mt-1 text-lg font-black tracking-tight text-slate-950 dark:text-white">
                        {preview?.symbol} / {currencySymbol === "€" ? "EUR" : "USD"}
                      </div>
                      <div className="mt-1 text-[11px] font-semibold text-slate-500 dark:text-slate-400">
                        {botName}
                      </div>
                    </div>
                  </div>
                  <button
                    type="button"
                    onClick={() => onRefresh?.()}
                    disabled={loading}
                    className="inline-flex items-center gap-2 rounded-xl border border-slate-200 bg-white px-3 py-2 text-[10px] font-black uppercase tracking-widest text-slate-600 transition hover:bg-slate-100 disabled:opacity-60 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-300 dark:hover:bg-slate-800"
                  >
                    <RefreshCw size={13} className={loading ? "animate-spin" : ""} />
                    {copy.refresh}
                  </button>
                </div>

                <div className="mt-5 grid gap-2 sm:grid-cols-2">
                  {consequenceSummary.map((row) => (
                    <DetailRow key={row.id} label={row.label} value={row.value} emphasis={row.id === "orderValue" || row.id === "exchangeEffect"} labels={detailLabels} />
                  ))}
                </div>
              </div>

              <div className="rounded-[1.5rem] border border-slate-200 bg-white p-5 dark:border-slate-800 dark:bg-slate-950/45">
                <div className="flex items-center justify-between gap-3">
                  <div>
                    <div className="inline-flex items-center gap-2 text-[10px] font-black uppercase tracking-widest text-slate-500 dark:text-slate-400">
                      <Brain size={13} className="text-violet-500" />
                      {copy.finnPreflight}
                    </div>
                    <p className="mt-2 text-sm font-black leading-relaxed text-slate-900 dark:text-white">
                      {copy.finnPreflightBody}
                    </p>
                  </div>
                  {finnLoading && (
                    <span className="inline-flex items-center gap-2 rounded-full border border-slate-200 bg-slate-50 px-3 py-1 text-[9px] font-black uppercase tracking-widest text-slate-500 dark:border-slate-800 dark:bg-slate-900 dark:text-slate-400">
                      <RefreshCw size={12} className="animate-spin" />
                      {copy.loading}
                    </span>
                  )}
                </div>

                {finnError && (
                  <div className="mt-4 rounded-xl border border-amber-200 bg-amber-50 px-3 py-3 text-xs font-semibold leading-relaxed text-amber-700 dark:border-amber-900/50 dark:bg-amber-950/20 dark:text-amber-300">
                    {finnError}
                  </div>
                )}

                {finnReview && (
                  <div className={`mt-4 rounded-2xl border p-4 ${
                    finnReview.decision_status === "block"
                      ? "border-rose-200 bg-rose-50 text-rose-700 dark:border-rose-900/50 dark:bg-rose-950/20 dark:text-rose-300"
                      : finnReview.decision_status === "modify" || finnReview.decision_status === "insufficient_context"
                        ? "border-amber-200 bg-amber-50 text-amber-700 dark:border-amber-900/50 dark:bg-amber-950/20 dark:text-amber-300"
                        : "border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-900/50 dark:bg-emerald-950/20 dark:text-emerald-300"
                  }`}>
                    <div className="flex items-center justify-between gap-3">
                      <span className="inline-flex items-center gap-2 text-[10px] font-black uppercase tracking-widest">
                        <Target size={13} />
                        {copy.decisionCheck}
                      </span>
                      <span className="rounded-full bg-white/75 dark:bg-slate-950/40 px-3 py-1 text-[9px] font-black uppercase tracking-widest">
                        {finnReview.decision_status}
                      </span>
                    </div>
                    <p className="mt-3 text-sm font-semibold leading-relaxed">{finnReview.risk_summary}</p>
                    {Array.isArray(finnReview.top_blockers) && finnReview.top_blockers.length > 0 && (
                      <div className="mt-3 space-y-2">
                        {finnReview.top_blockers.slice(0, 2).map((item, index) => (
                          <div key={`review-blocker-${index}`} className="rounded-xl border border-white/60 dark:border-slate-900/50 bg-white/70 dark:bg-slate-950/35 p-3 text-xs font-semibold leading-relaxed">
                            {item}
                          </div>
                        ))}
                      </div>
                    )}
                    {behavioralFriction?.message && (
                      <div className="mt-3 rounded-xl border border-white/60 dark:border-slate-900/50 bg-white/70 dark:bg-slate-950/35 p-3">
                        <div className="text-[9px] font-black uppercase tracking-widest opacity-70">
                          {copy.behavioralBrake}{behavioralFriction?.label ? ` · ${behavioralFriction.label}` : ""}
                        </div>
                        <p className="mt-2 text-xs font-semibold leading-relaxed">{behavioralFriction.message}</p>
                        {behavioralFriction?.safe_alternative && (
                          <p className="mt-2 text-[11px] font-black leading-relaxed">{behavioralFriction.safe_alternative}</p>
                        )}
                      </div>
                    )}
                  </div>
                )}

                {finnAdherence && (
                  <div className={`mt-4 rounded-2xl border p-4 ${
                    finnAdherence.adherence_status === "in_plan"
                      ? "border-blue-200 bg-blue-50 text-blue-700 dark:border-blue-900/50 dark:bg-blue-950/20 dark:text-blue-300"
                      : finnAdherence.adherence_status === "insufficiently_justified"
                        ? "border-amber-200 bg-amber-50 text-amber-700 dark:border-amber-900/50 dark:bg-amber-950/20 dark:text-amber-300"
                        : "border-rose-200 bg-rose-50 text-rose-700 dark:border-rose-900/50 dark:bg-rose-950/20 dark:text-rose-300"
                  }`}>
                    <div className="flex items-center justify-between gap-3">
                      <span className="inline-flex items-center gap-2 text-[10px] font-black uppercase tracking-widest">
                        <ShieldCheck size={13} />
                        {copy.planAdherence}
                      </span>
                      <span className="rounded-full bg-white/75 dark:bg-slate-950/40 px-3 py-1 text-[9px] font-black uppercase tracking-widest">
                        {finnAdherence.adherence_status}
                      </span>
                    </div>
                    <p className="mt-3 text-sm font-semibold leading-relaxed">{finnAdherence.adherence_reason}</p>
                    <div className="mt-3 grid gap-3 sm:grid-cols-2">
                      {finnAdherence.threatened_rule && (
                        <div className="rounded-xl border border-white/60 dark:border-slate-900/50 bg-white/70 dark:bg-slate-950/35 p-3">
                          <div className="text-[9px] font-black uppercase tracking-widest opacity-70">{copy.threatenedRule}</div>
                          <p className="mt-2 text-xs font-semibold leading-relaxed">{finnAdherence.threatened_rule}</p>
                        </div>
                      )}
                      {finnAdherence.suggested_recovery_step && (
                        <div className="rounded-xl border border-white/60 dark:border-slate-900/50 bg-white/70 dark:bg-slate-950/35 p-3">
                          <div className="text-[9px] font-black uppercase tracking-widest opacity-70">{copy.safeNextStep}</div>
                          <p className="mt-2 text-xs font-semibold leading-relaxed">{finnAdherence.suggested_recovery_step}</p>
                        </div>
                      )}
                    </div>
                  </div>
                )}
              </div>

              {isLive && (
                <div className="rounded-[1.5rem] border border-blue-200 bg-blue-50/80 p-5 dark:border-blue-900/40 dark:bg-blue-950/20">
                  <div className="flex items-center gap-2 text-[10px] font-black uppercase tracking-widest text-blue-700 dark:text-blue-300">
                    <ShieldCheck size={13} />
                    {copy.liveExecutionContext}
                  </div>
                  <p className="mt-2 text-sm font-semibold leading-relaxed text-blue-900 dark:text-blue-100">
                    {copy.liveExecutionBody}
                  </p>
                  <div className="mt-4 grid gap-2 sm:grid-cols-2">
                    {liveContextRows.map(([label, value]) => (
                      <DetailRow key={label} label={label} value={value} labels={detailLabels} />
                    ))}
                  </div>
                </div>
              )}

              {hasLiveGuardrails && (
                <GuardrailList title={copy.liveGuardrails} items={guardrailChecks} blocked={false} copy={copy} locale={locale} />
              )}

              {preview?.bot_guardrails && (
                <div className="rounded-2xl border border-slate-200 bg-white p-4 dark:border-slate-800 dark:bg-slate-950/35">
                  <div className="flex items-center gap-2 text-[10px] font-black uppercase tracking-widest text-slate-500 dark:text-slate-400">
                    <Shield size={13} />
                    {copy.botGuardrails}
                  </div>
                  <div className="mt-3 grid gap-2 sm:grid-cols-2">
                    {Object.entries(preview.bot_guardrails)
                      .filter(([, value]) => value !== null && value !== undefined && value !== "")
                      .slice(0, 6)
                      .map(([key, value]) => (
                        <DetailRow key={key} label={titleCase(key)} value={typeof value === "number" ? fmt(value, locale) : detailValue(value, detailLabels)} labels={detailLabels} />
                      ))}
                  </div>
                </div>
              )}

              {isBlocked && (
                <div className="rounded-[1.5rem] border border-rose-200 bg-rose-50/80 p-5 dark:border-rose-900/40 dark:bg-rose-950/20">
                  <div className="flex items-center gap-2 text-[10px] font-black uppercase tracking-widest text-rose-700 dark:text-rose-300">
                    <XCircle size={13} />
                    {copy.orderBlocked}
                  </div>
                  <p className="mt-2 text-sm font-semibold leading-relaxed text-rose-900 dark:text-rose-100">
                    {preview?.safe_next_step || copy.resolveBlockerFirst}
                  </p>
                  {requiresSetupBlockAck && (
                    <button
                      type="button"
                      onClick={onAcknowledgeSetupBlock}
                      disabled={loading}
                      className="mt-4 inline-flex items-center gap-2 rounded-xl bg-rose-600 px-4 py-3 text-[10px] font-black uppercase tracking-widest text-white transition hover:bg-rose-700 disabled:opacity-60"
                    >
                      <ShieldAlert size={13} />
                      {copy.acknowledgeSetupBlock}
                    </button>
                  )}
                </div>
              )}
            </div>

            <div className="space-y-6">
              <div className="rounded-[1.5rem] border border-slate-200 bg-white p-5 dark:border-slate-800 dark:bg-slate-950/45">
                <div className="flex items-center gap-2 text-[10px] font-black uppercase tracking-widest text-slate-500 dark:text-slate-400">
                  <AlertCircle size={13} />
                  {copy.consequenceSummary}
                </div>
                <div className="mt-4 space-y-3">
                  <div className="rounded-2xl border border-slate-100 bg-slate-50 px-4 py-3 dark:border-slate-800 dark:bg-slate-900/60">
                    <div className="text-[9px] font-black uppercase tracking-widest text-slate-400 dark:text-slate-500">
                      {copy.ifYouConfirmNow}
                    </div>
                    <p className="mt-2 text-sm font-semibold leading-relaxed text-slate-800 dark:text-slate-100">
                      {isBlocked
                        ? copy.blockedConfirmBody
                        : isLive
                          ? `${copy.liveOrderPrefix} ${isBuy ? copy.buy : copy.sell} ${copy.liveOrderSuffix} ${currencySymbol} ${fmt(orderAmount, locale)}.`
                          : `${copy.paperOrderPrefix} ${isBuy ? copy.buy : copy.sell} ${copy.paperOrderSuffix} ${currencySymbol} ${fmt(orderAmount, locale)}.`}
                    </p>
                  </div>

                  <div className="rounded-2xl border border-slate-100 bg-slate-50 px-4 py-3 dark:border-slate-800 dark:bg-slate-900/60">
                    <div className="text-[9px] font-black uppercase tracking-widest text-slate-400 dark:text-slate-500">
                      {copy.finnExpectsAfter}
                    </div>
                    <p className="mt-2 text-sm font-semibold leading-relaxed text-slate-800 dark:text-slate-100">
                      {isBlocked
                        ? copy.afterBlocked
                        : isLive
                          ? copy.afterLive
                          : copy.afterPaper}
                    </p>
                  </div>

                  {preview?.trace_id && (
                    <div className="rounded-2xl border border-slate-100 bg-slate-50 px-4 py-3 dark:border-slate-800 dark:bg-slate-900/60">
                      <div className="text-[9px] font-black uppercase tracking-widest text-slate-400 dark:text-slate-500">
                        {copy.traceLabel}
                      </div>
                      <p className="mt-2 break-all font-mono text-[11px] font-bold text-slate-700 dark:text-slate-200">
                        {preview.trace_id}
                      </p>
                    </div>
                  )}
                </div>
              </div>

                {isLive && !isBlocked && (
                <div className="rounded-[1.5rem] border border-amber-200 bg-amber-50/80 p-5 dark:border-amber-900/40 dark:bg-amber-950/20">
                  <div className="flex items-center gap-2 text-[10px] font-black uppercase tracking-widest text-amber-700 dark:text-amber-300">
                    <ShieldAlert size={13} />
                    {copy.liveConfirmationFriction}
                  </div>
                  <label className="mt-4 flex cursor-pointer items-start gap-3">
                    <input
                      type="checkbox"
                      checked={liveIntentConfirmed}
                      onChange={(event) => setLiveIntentConfirmed(event.target.checked)}
                      className="mt-0.5 h-4 w-4 rounded border-slate-300 text-amber-600 focus:ring-amber-500"
                    />
                    <span className="text-sm font-semibold leading-relaxed text-amber-900 dark:text-amber-100">
                      {copy.liveConfirmationCheckbox}
                    </span>
                  </label>
                  {behavioralFriction?.safe_alternative && (
                    <div className="mt-4 rounded-xl border border-white/70 bg-white/70 px-4 py-3 text-sm font-semibold leading-relaxed text-amber-900 dark:border-slate-900/40 dark:bg-slate-950/30 dark:text-amber-100">
                      {copy.extraBehavioralBrake}: {behavioralFriction.safe_alternative}
                    </div>
                  )}
                </div>
              )}

              {!isLive && (
                <div className="flex items-center justify-center gap-3 rounded-[1.5rem] border border-slate-200 bg-white px-4 py-4 dark:border-slate-800 dark:bg-slate-950/40">
                  <div className="relative flex h-8 w-8 items-center justify-center">
                    <svg className="h-full w-full -rotate-90">
                      <circle cx="16" cy="16" r="14" stroke="currentColor" strokeWidth="3" fill="transparent" className="text-slate-200 dark:text-slate-700" />
                      <circle
                        cx="16"
                        cy="16"
                        r="14"
                        stroke="currentColor"
                        strokeWidth="3"
                        fill="transparent"
                        strokeDasharray={88}
                        strokeDashoffset={88 - (88 * seconds) / 10}
                        className="text-blue-600 transition-all duration-1000"
                      />
                    </svg>
                    <span className="absolute text-[10px] font-black text-slate-900 dark:text-white">{seconds}</span>
                  </div>
                  <span className="text-[10px] font-black uppercase tracking-widest text-slate-400 dark:text-slate-500">
                    {copy.previewRefreshing}
                  </span>
                </div>
              )}
            </div>
          </div>
        </div>

        <div className="flex flex-col gap-3 border-t border-slate-200 bg-white px-6 py-5 dark:border-slate-800 dark:bg-slate-950/70 sm:flex-row">
          <button
            onClick={onCancel}
            className="flex-1 rounded-2xl border border-slate-200 px-5 py-3 text-[11px] font-black uppercase tracking-widest text-slate-500 transition hover:bg-slate-100 dark:border-slate-700 dark:text-slate-300 dark:hover:bg-slate-800"
          >
            {copy.cancel}
          </button>
          <button
            type="button"
            onClick={() => onRefresh?.()}
            disabled={loading}
            className="rounded-2xl border border-slate-200 px-5 py-3 text-[11px] font-black uppercase tracking-widest text-slate-600 transition hover:bg-slate-100 disabled:opacity-60 dark:border-slate-700 dark:text-slate-300 dark:hover:bg-slate-800"
          >
            {copy.refreshChecks}
          </button>
          <button
            onClick={onConfirm}
            disabled={!canConfirm}
            className={`flex-[1.4] rounded-2xl px-5 py-3 text-[11px] font-black uppercase tracking-widest text-white shadow-lg transition active:scale-[0.98] ${
              canConfirm
                ? (isLive ? "bg-rose-600 shadow-rose-300/40 hover:bg-rose-700" : "bg-blue-600 shadow-blue-300/40 hover:bg-blue-700")
                : "bg-slate-300 shadow-none"
            }`}
          >
            {primaryButtonLabel}
          </button>
        </div>
      </div>
    </div>
  );
}
