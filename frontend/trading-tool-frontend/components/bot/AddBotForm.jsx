"use client";

import {
  forwardRef,
  useCallback,
  useEffect,
  useImperativeHandle,
  useMemo,
  useRef,
  useState,
} from "react";
import {
  CalendarDays,
  CheckCircle2,
  ChevronDown,
  ChevronUp,
  CircleDollarSign,
  FlaskConical,
  Lock,
  RadioTower,
  Rocket,
  Scale,
  Shield,
  ShoppingCart,
  Sparkles,
} from "lucide-react";
import { useTranslation } from "@/app/providers/I18nProvider";
import { useModal } from "@/components/modal/ModalProvider";
import { actionButtonStyles } from "@/components/ui/actionButtonStyles";
import {
  getBotRiskAcknowledgement,
  getBotSaveErrorMessage,
} from "@/lib/bot/riskAcknowledgement.mjs";
import { formatDcaSchedule } from "@/lib/bot/dcaSchedule.mjs";
import { dcaBotPlan, dcaBotBudgetCheck, dcaPurchaseCapacity } from "@/lib/bot/dcaBotPlan.mjs";
import SystemConnectivity from "@/components/dashboard/SystemConnectivity";
import { marketPairLabel } from "@/lib/marketPairLabel.mjs";

const RISK_PROFILE_ICONS = {
  conservative: Shield,
  balanced: Scale,
  aggressive: Rocket,
};

/**
 * AddBotForm — Tradamind 2.5 (FINAL)
 */
const AddBotForm = forwardRef(function AddBotForm({
  initialData = null,
  initialValues = null,
  strategies = [],
  setups = [],
  onChange,
  onSubmit,
  onSaved,
  onCancel,
  hideActions = true,
  submitLabel = "",
  submitBusyLabel = "",
  cancelLabel = "",
  successMessage = "",
  saveFailedMessage = "",
  guidedMode = false,
  guidedSymbol = "",
}, ref) {
  const { t, locale } = useTranslation();
  const copy = t?.botPage?.form || {};
  const pageCopy = t?.botPage || {};
  const riskCopy = pageCopy.budgetForm || {};
  const { showSnackbar } = useModal();
  const formRef = useRef(null);

  const sourceData = initialData ?? initialValues;
  const isEdit = Boolean(sourceData?.id ?? sourceData?.bot_id);

  const [form, setForm] = useState({
    id: undefined,
    bot_id: undefined,
    name: "",
    strategy_id: null,
    mode: "manual",
    is_live: false,
    risk_profile: "balanced",
    base_currency: "EUR",
    budget_total_eur: "",
    paper_initial_cash_eur: 0,
    budget_daily_limit_eur: 0,
    budget_min_order_eur: 0,
    budget_max_order_eur: 0,
    max_asset_exposure_pct: 100,
  });
  const [loading, setLoading] = useState(false);
  const [submitError, setSubmitError] = useState("");
  const [riskAcknowledgement, setRiskAcknowledgement] = useState(null);
  const [showAdvancedBudget, setShowAdvancedBudget] = useState(false);
  const [exchangeChoice, setExchangeChoice] = useState("later");
  const [exchangeConnected, setExchangeConnected] = useState(false);

  const deferredLiveCreate = form.is_live && !isEdit && (exchangeChoice === "later" || !exchangeConnected);
  const willBeActive = isEdit ? sourceData?.is_active !== false : !deferredLiveCreate;
  const requiresExplicitBudget = willBeActive && (form.is_live || form.mode !== "manual");

  /* =====================================================
     INIT / PREFILL
  ===================================================== */
  useEffect(() => {
    if (!sourceData) return;

    setForm({
      id: sourceData.id,
      bot_id: sourceData.bot_id,
      name: sourceData.name ?? "",
      strategy_id:
        typeof sourceData.strategy_id === "number"
          ? sourceData.strategy_id
          : sourceData.strategy?.id ?? null,
      mode: sourceData.mode ?? "manual",
      is_live: sourceData.is_live ?? false,
      risk_profile: sourceData.risk_profile ?? "balanced",
      base_currency: sourceData.base_currency ?? "EUR",
      budget_total_eur: sourceData.budget_total_eur ?? sourceData.budget?.total_eur ?? "",
      paper_initial_cash_eur: sourceData.paper_initial_cash_eur ?? 0,
      budget_daily_limit_eur: sourceData.budget_daily_limit_eur ?? sourceData.budget?.daily_limit_eur ?? 0,
      budget_min_order_eur: sourceData.budget_min_order_eur ?? sourceData.budget?.min_order_eur ?? 0,
      budget_max_order_eur: sourceData.budget_max_order_eur ?? sourceData.budget?.max_order_eur ?? 0,
      max_asset_exposure_pct: sourceData.max_asset_exposure_pct ?? sourceData.budget?.max_asset_exposure_pct ?? 100,
    });
  }, [sourceData]);

  /* =====================================================
     LIVE SYNC NAAR PARENT
  ===================================================== */
  useEffect(() => {
    onChange?.(form);
  }, [form, onChange]);

  /* =====================================================
     DERIVED
  ===================================================== */
  const selectedStrategy = useMemo(() => {
    return (
      strategies.find((s) => s.id === form.strategy_id) ??
      sourceData?.strategy ??
      null
    );
  }, [strategies, form.strategy_id, sourceData]);
  const selectedSetup = useMemo(() => (
    setups.find((setup) => Number(setup.id) === Number(selectedStrategy?.setup_id))
    || selectedStrategy?.setup
    || null
  ), [selectedStrategy, setups]);
  const dcaPlan = useMemo(() => dcaBotPlan(selectedStrategy, selectedSetup), [selectedStrategy, selectedSetup]);
  const isDcaSetup = String(selectedSetup?.setup_type || selectedSetup?.type || "").toLowerCase() === "dca";
  const selectedStrategyId = selectedStrategy?.id;
  const lastPrefilledStrategy = useRef(null);

  useEffect(() => {
    if (isEdit || !dcaPlan || !selectedStrategyId || lastPrefilledStrategy.current === selectedStrategyId) return;
    lastPrefilledStrategy.current = selectedStrategyId;
    setForm((current) => ({
      ...current,
      mode: "",
      budget_daily_limit_eur: dcaPlan.maximum,
      budget_min_order_eur: dcaPlan.minimum,
      budget_max_order_eur: dcaPlan.maximum,
    }));
  }, [dcaPlan, isEdit, selectedStrategyId]);

  useEffect(() => {
    if (!guidedMode || showAdvancedBudget || dcaPlan) return;
    const spendPerCycle = Number(form.budget_daily_limit_eur || 0);
    if (!Number.isFinite(spendPerCycle) || spendPerCycle <= 0) return;
    if (Number(form.budget_min_order_eur || 0) === spendPerCycle
        && Number(form.budget_max_order_eur || 0) === spendPerCycle) return;
    setForm((current) => ({
      ...current,
      budget_min_order_eur: spendPerCycle,
      budget_max_order_eur: spendPerCycle,
    }));
  }, [dcaPlan, form.budget_daily_limit_eur, form.budget_max_order_eur,
    form.budget_min_order_eur, guidedMode, showAdvancedBudget]);

  const riskProfiles = [
    {
      value: "conservative",
      icon: RISK_PROFILE_ICONS.conservative,
      label: copy.riskConservativeLabel,
      description: copy.riskConservativeDescription,
    },
    {
      value: "balanced",
      icon: RISK_PROFILE_ICONS.balanced,
      label: copy.riskBalancedLabel,
      description: copy.riskBalancedDescription,
    },
    {
      value: "aggressive",
      icon: RISK_PROFILE_ICONS.aggressive,
      label: copy.riskAggressiveLabel,
      description: copy.riskAggressiveDescription,
    },
  ];

  const selectedRisk =
    riskProfiles.find((r) => r.value === form.risk_profile) ??
    riskProfiles[1];
  const SelectedRiskIcon = selectedRisk.icon;

  const onboardingCopy = pageCopy.onboardingGuide || {};
  const strategyTimeframe = String(selectedStrategy?.timeframe || "").toUpperCase();
  const dcaSchedule = formatDcaSchedule(selectedSetup, copy);
  const dcaCapacity = dcaPurchaseCapacity(dcaPlan, form.budget_total_eur);
  const formatEuro = (value) => new Intl.NumberFormat(locale, { style: "currency", currency: "EUR" }).format(value);
  const cadenceSpendLabel = copy.dailyLimitLabel || "Daily spending limit";
  const cadenceSpendHelp = copy.dailyLimitHelp || "The most this bot may spend in one calendar day.";

  const getStrategyType = (s) => {
    const type = String(s?.strategy_type || s?.type || "manual").toLowerCase();
    return copy.strategyTypes?.[type] || (type === "manual" ? copy.modeManual : type);
  };

  const validateForm = useCallback(() => {
    if (formRef.current && !formRef.current.reportValidity()) {
      return {
        ok: false,
        message: pageCopy.createValidation || "Vul naam en strategie in voordat je opslaat.",
      };
    }

    if (!String(form.name || "").trim() || !form.strategy_id) {
      return {
        ok: false,
        message: pageCopy.createValidation || "Vul naam en strategie in voordat je opslaat.",
      };
    }

    if (dcaPlan && !form.mode) {
      return { ok: false, message: copy.dcaChooseMode || "Kies of deze DCA-bot handmatig of automatisch uitvoert." };
    }
    if (isDcaSetup && !dcaPlan) {
      return { ok: false, message: copy.dcaMissingAmount || "Deze DCA-strategie heeft geen bevestigd aankoopbedrag." };
    }

    const numericFields = [
      "budget_total_eur",
      "paper_initial_cash_eur",
      "budget_daily_limit_eur",
      "budget_min_order_eur",
      "budget_max_order_eur",
      "max_asset_exposure_pct",
    ];

    for (const field of numericFields) {
      const value = Number(form[field]);
      if (!Number.isFinite(value) || value < 0) {
        return {
          ok: false,
          message: copy.numericValidation || "Gebruik alleen geldige positieve waarden.",
        };
      }
    }

    if (Number(form.max_asset_exposure_pct) > 100) {
      return {
        ok: false,
        message: copy.assetExposureValidation || "Assetblootstelling mag maximaal 100% zijn.",
      };
    }

    const totalBudget = Number(form.budget_total_eur || 0);
    const dailyLimit = Number(form.budget_daily_limit_eur || 0);
    const minOrder = Number(form.budget_min_order_eur || 0);
    const maxOrder = Number(form.budget_max_order_eur || 0);

    if (requiresExplicitBudget) {
      if (![totalBudget, dailyLimit, minOrder, maxOrder].every((value) => value > 0)) {
        return {
          ok: false,
          message: copy.guidedBudgetRequired || "Vul voor live of automatische bots alle budgetvelden in met geldige startwaarden.",
        };
      }
    }

    const dcaBudgetError = dcaBotBudgetCheck(dcaPlan, form, {
      automatic: Boolean(form.mode && form.mode !== "manual"),
      paper: !form.is_live && form.mode === "auto", create: !isEdit,
    });
    if (dcaBudgetError) {
      return { ok: false, message: copy.dcaBudgetErrors?.[dcaBudgetError] || "De botlimieten moeten het geplande DCA-bedrag toelaten." };
    }

    if (dailyLimit > totalBudget) {
      return {
        ok: false,
        message: copy.dailyLimitValidation || "Daglimiet mag niet hoger zijn dan het totale budget.",
      };
    }

    if (minOrder > maxOrder) {
      return {
        ok: false,
        message: copy.minOrderValidation || "Minimale order mag niet hoger zijn dan de maximale order.",
      };
    }

    if (maxOrder > totalBudget) {
      return {
        ok: false,
        message: copy.maxOrderValidation || "Maximale order mag niet hoger zijn dan het totale budget.",
      };
    }

    return { ok: true };
  }, [
    copy.assetExposureValidation,
    copy.dailyLimitValidation,
    copy.guidedBudgetRequired,
    copy.maxOrderValidation,
    copy.minOrderValidation,
    copy.numericValidation,
    copy.dcaChooseMode,
    copy.dcaBudgetErrors,
    dcaPlan,
    form,
    isEdit,
    isDcaSetup,
    pageCopy.createValidation,
    requiresExplicitBudget,
  ]);

  const submitForm = useCallback(async (riskAcknowledged = false) => {
    if (loading) {
      return { ok: false, reason: "busy" };
    }

    const validation = validateForm();
    if (!validation.ok) {
      setSubmitError(validation.message);
      return { ok: false, reason: "validation" };
    }

    if (typeof onSubmit !== "function") {
      return { ok: false, reason: "missing_submit" };
    }

    const payload = {
      ...form,
      ...(dcaSchedule ? { cadence: selectedSetup.dca_frequency } : {}),
      name: String(form.name || "").trim(),
      strategy_id: Number(form.strategy_id),
      budget_total_eur: Number(form.budget_total_eur || 0),
      paper_initial_cash_eur: Number(form.paper_initial_cash_eur || 0),
      budget_daily_limit_eur: Number(form.budget_daily_limit_eur || 0),
      budget_min_order_eur: Number(form.budget_min_order_eur || 0),
      budget_max_order_eur: Number(form.budget_max_order_eur || 0),
      max_asset_exposure_pct: Number(form.max_asset_exposure_pct || 0),
      ...(!isEdit ? { is_active: form.is_live ? !deferredLiveCreate : true } : {}),
      ...(riskAcknowledged ? { risk_acknowledged: true } : {}),
    };

    setSubmitError("");
    setRiskAcknowledgement(null);
    setLoading(true);

    try {
      const savedBot = await onSubmit(payload);
      if (successMessage) {
        showSnackbar(successMessage, "success");
      }
      onSaved?.(savedBot ?? payload);
      return { ok: true, data: savedBot ?? payload };
    } catch (error) {
      console.error(error);
      const acknowledgement = getBotRiskAcknowledgement(error);
      const message = getBotSaveErrorMessage(
        error,
        saveFailedMessage || copy.saveFailed || "Opslaan van de bot mislukt."
      );
      if (acknowledgement) {
        setRiskAcknowledgement(acknowledgement);
      }
      setSubmitError(message);
      showSnackbar(message, acknowledgement ? "info" : "danger");
      return { ok: false, reason: "api", error };
    } finally {
      setLoading(false);
    }
  }, [
    copy.saveFailed,
    dcaSchedule,
    deferredLiveCreate,
    form,
    guidedMode,
    isEdit,
    loading,
    onSaved,
    onSubmit,
    saveFailedMessage,
    selectedSetup,
    showSnackbar,
    successMessage,
    validateForm,
  ]);

  useImperativeHandle(ref, () => ({
    submit: submitForm,
    isSubmitting: () => loading,
  }), [loading, submitForm]);

  const handleSubmit = async (event) => {
    event.preventDefault();
    await submitForm();
  };

  return (
    <form ref={formRef} onSubmit={handleSubmit} autoComplete="off" className="space-y-6">
      {guidedMode ? (
        <div className="space-y-4 rounded-[28px] border border-blue-100 bg-blue-50/60 p-5">
          <div className="flex items-center gap-2 text-[10px] font-black uppercase tracking-[0.2em] text-blue-600">
            <Sparkles size={14} />
            {onboardingCopy.drawerEyebrow || "Automation · guided creation"}
          </div>

          <div>
            <h2 className="text-2xl font-black tracking-tight text-slate-900">
              {onboardingCopy.drawerTitle || "Create one safe starter bot"}
            </h2>
            <p className="mt-2 text-sm font-semibold leading-relaxed text-slate-600">
              {(onboardingCopy.drawerBody || "Use the saved strategy for {symbol}, start in paper mode or paused mode, and save one bot to complete onboarding.").replace("{symbol}", guidedSymbol || selectedStrategy?.symbol || "this asset")}
            </p>
          </div>

          <div className="grid gap-3 md:grid-cols-3">
            <div className="rounded-2xl border border-white/80 bg-white px-4 py-3">
              <div className="text-[10px] font-black uppercase tracking-[0.18em] text-slate-400">
                {onboardingCopy.drawerStepOneEyebrow || "Step 1"}
              </div>
              <div className="mt-2 text-sm font-black text-slate-900">
                {onboardingCopy.drawerStepOneTitle || "Use your saved strategy"}
              </div>
              <div className="mt-1 text-xs font-semibold leading-relaxed text-slate-500">
                {selectedStrategy?.name || onboardingCopy.pendingLabel || "Pending"}
              </div>
            </div>

            <div className="rounded-2xl border border-white/80 bg-white px-4 py-3">
              <div className="text-[10px] font-black uppercase tracking-[0.18em] text-slate-400">
                {onboardingCopy.drawerStepTwoEyebrow || "Step 2"}
              </div>
              <div className="mt-2 text-sm font-black text-slate-900">
                {onboardingCopy.drawerStepTwoTitle || "Keep the first mode safe"}
              </div>
              <div className="mt-1 text-xs font-semibold leading-relaxed text-slate-500">
                {onboardingCopy.drawerStepTwoBody || "Paper mode and manual execution are enough for onboarding."}
              </div>
            </div>

            <div className="rounded-2xl border border-white/80 bg-white px-4 py-3">
              <div className="text-[10px] font-black uppercase tracking-[0.18em] text-slate-400">
                {onboardingCopy.drawerStepThreeEyebrow || "Step 3"}
              </div>
              <div className="mt-2 text-sm font-black text-slate-900">
                {onboardingCopy.drawerStepThreeTitle || "Save and continue"}
              </div>
              <div className="mt-1 text-xs font-semibold leading-relaxed text-slate-500">
                {onboardingCopy.drawerStepThreeBody || "After saving, you return to the onboarding flow and review the final automation step."}
              </div>
            </div>
          </div>
        </div>
      ) : null}

      {/* ================= BOT NAME ================= */}
      <div className="space-y-1.5">
          <label className="text-[10px] font-black text-slate-400 uppercase tracking-widest ml-1">
          {copy.nameLabel}
        </label>
        <input
          name="name"
          className="w-full bg-card border-2 border-slate-100 dark:border-slate-800 rounded-2xl px-5 py-4 text-sm font-bold text-foreground focus:border-blue-600 transition-all outline-none placeholder:text-slate-300"
          placeholder={copy.namePlaceholder}
          value={form.name}
          required
          onChange={(e) =>
            setForm((s) => ({ ...s, name: e.target.value }))
          }
        />
      </div>

      {/* ================= STRATEGY ================= */}
      <div className="space-y-1.5">
        <label className="text-[10px] font-black text-slate-400 uppercase tracking-widest ml-1">
          {copy.strategyLabel}
        </label>

        {isEdit || (guidedMode && selectedStrategy) ? (
          <div className="w-full bg-slate-50 dark:bg-slate-900 border-2 border-slate-100 dark:border-slate-800 rounded-2xl px-5 py-4 text-sm font-bold text-muted cursor-not-allowed flex items-center justify-between">
            <span>{selectedStrategy ? `${selectedStrategy.name} · ${marketPairLabel(selectedStrategy)}` : "—"}</span>
            <div className="inline-flex items-center gap-1 text-[9px] bg-slate-200 dark:bg-slate-700 px-2 py-0.5 rounded-md uppercase tracking-tighter">
              <Lock size={10} />
              {copy.lockedLabel}
            </div>
          </div>
        ) : (
          <div className="relative">
            <select
              name="strategy_id"
              className="w-full bg-card border-2 border-slate-100 dark:border-slate-800 rounded-2xl px-5 py-4 text-sm font-bold text-foreground appearance-none focus:border-blue-600 outline-none cursor-pointer"
              value={form.strategy_id ?? ""}
              required
              onChange={(e) =>
                setForm((s) => ({
                  ...s,
                  strategy_id: e.target.value
                    ? Number(e.target.value)
                    : null,
                }))
              }
            >
              <option value="">{copy.strategyPlaceholder}</option>
              {strategies.map((s) => (
                <option key={s.id} value={s.id}>
                  {`${s.name} · ${marketPairLabel(s)} · ${s.timeframe}`}
                </option>
              ))}
            </select>
            <div className="absolute right-5 top-1/2 -translate-y-1/2 pointer-events-none opacity-40">
               ▼
            </div>
          </div>
        )}
      </div>

      {/* ================= STRATEGY PREVIEW ================= */}
      {selectedStrategy && (
        <div className="rounded-2xl bg-blue-50/30 dark:bg-blue-900/10 border-2 border-blue-600/10 p-5 space-y-3">
          <div className="flex items-center justify-between">
             <div className="text-[9px] font-black text-blue-600 dark:text-blue-400 uppercase tracking-[0.2em]">{copy.strategyParameters}</div>
             <div className="text-[9px] font-black text-white uppercase bg-blue-600 px-2 py-0.5 rounded-md shadow-sm shadow-blue-600/20">{getStrategyType(selectedStrategy)}</div>
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <div className="text-[8px] font-black text-blue-400 uppercase">{copy.assetNode}</div>
              <div className="text-sm font-black text-foreground dark:text-slate-100 font-mono tracking-tighter">{selectedStrategy.symbol}</div>
            </div>
            <div>
              <div className="text-[8px] font-black text-blue-400 uppercase">{copy.timeHorizon}</div>
              <div className="text-sm font-black text-foreground dark:text-slate-100 font-mono tracking-tighter">{selectedStrategy.timeframe}</div>
            </div>
          </div>

          {selectedStrategy.description && (
            <div className="text-[11px] font-medium text-slate-500 italic border-t border-blue-100/50 pt-3 leading-relaxed">
              "{selectedStrategy.description}"
            </div>
          )}
          {dcaSchedule ? (
            <p className="text-xs font-semibold text-slate-600">
              {(copy.dcaScheduleNote || "Saved DCA schedule: {schedule}. {timeframe} is the chart timeframe, not a daily purchase schedule.")
                .replace("{schedule}", dcaSchedule)
                .replace("{timeframe}", strategyTimeframe || selectedSetup?.timeframe || "—")}
            </p>
          ) : null}
          {dcaPlan ? (
            <p className="text-xs font-semibold text-slate-700">
              {(copy.dcaPlanAmount || "Planned purchase: {amount} per scheduled moment.")
                .replace("{amount}", dcaPlan.variable
                  ? `${formatEuro(dcaPlan.minimum)}–${formatEuro(dcaPlan.maximum)}`
                  : formatEuro(dcaPlan.base))}
            </p>
          ) : null}
          {isDcaSetup && !dcaPlan ? (
            <p className="text-xs font-semibold text-amber-700">{copy.dcaMissingAmount || "Deze DCA-strategie heeft geen bevestigd aankoopbedrag."}</p>
          ) : null}
        </div>
      )}

      {guidedMode ? (
        <div className="rounded-2xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm font-semibold text-emerald-800">
          <div className="flex items-center gap-2 text-[10px] font-black uppercase tracking-[0.18em] text-emerald-700">
            <CheckCircle2 size={12} />
            {onboardingCopy.drawerHintEyebrow || "Onboarding goal"}
          </div>
          <p className="mt-2">
            {onboardingCopy.drawerHintBody || "You only need one saved bot here. You can refine budget, automation mode, and extra settings after onboarding."}
          </p>
        </div>
      ) : null}

      {guidedMode ? (
        <div className="grid gap-3 md:grid-cols-3">
          <div className="rounded-2xl border border-slate-200 bg-slate-50 px-4 py-4">
            <div className="flex items-center gap-2 text-[10px] font-black uppercase tracking-[0.18em] text-slate-500">
              <CalendarDays size={12} />
              {dcaSchedule ? copy.dcaScheduleCardLabel : copy.cadenceCardLabel}
            </div>
            <div className="mt-2 text-sm font-black text-slate-900">
              {dcaSchedule || (copy.cadenceCardValue || "{timeframe} strategy").replace("{timeframe}", strategyTimeframe || "—")}
            </div>
            <p className="mt-1 text-xs font-semibold leading-relaxed text-slate-500">
              {dcaSchedule ? copy.dcaScheduleCardHelp : copy.cadenceCardHelp}
            </p>
          </div>

          <div className="rounded-2xl border border-slate-200 bg-slate-50 px-4 py-4">
            <div className="flex items-center gap-2 text-[10px] font-black uppercase tracking-[0.18em] text-slate-500">
              <CircleDollarSign size={12} />
              {copy.budgetCardLabel}
            </div>
            <div className="mt-2 text-sm font-black text-slate-900">
              {copy.budgetCardValue}
            </div>
            <p className="mt-1 text-xs font-semibold leading-relaxed text-slate-500">
              {copy.budgetCardHelp}
            </p>
          </div>

          <div className="rounded-2xl border border-slate-200 bg-slate-50 px-4 py-4">
            <div className="flex items-center gap-2 text-[10px] font-black uppercase tracking-[0.18em] text-slate-500">
              <ShoppingCart size={12} />
              {copy.orderCardLabel}
            </div>
            <div className="mt-2 text-sm font-black text-slate-900">
              {copy.orderCardValue}
            </div>
            <p className="mt-1 text-xs font-semibold leading-relaxed text-slate-500">
              {copy.orderCardHelp}
            </p>
          </div>
        </div>
      ) : null}

      {/* ================= EXECUTION TYPE & RISK ================= */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div className="space-y-1.5">
            <label className="text-[10px] font-black text-slate-400 uppercase tracking-widest ml-1">
            {copy.environmentLabel}
          </label>
          <div className="flex bg-slate-100 dark:bg-slate-900 p-1 rounded-2xl border-2 border-slate-100 dark:border-slate-800">
             <button 
                type="button"
                onClick={() => setForm(s => ({ ...s, is_live: false }))}
                className={`flex-1 py-3 rounded-xl text-[10px] font-black uppercase tracking-widest transition-all ${!form.is_live ? 'bg-white dark:bg-slate-800 text-blue-600 shadow-sm' : 'text-slate-400 hover:text-slate-600'}`}
             >
                <span className="inline-flex items-center gap-2">
                  <FlaskConical size={12} />
                  {copy.paperTrading}
                </span>
             </button>
             <button 
                type="button"
                onClick={() => setForm(s => ({ ...s, is_live: true }))}
                className={`flex-1 py-3 rounded-xl text-[10px] font-black uppercase tracking-widest transition-all ${form.is_live ? 'bg-white dark:bg-slate-800 text-emerald-600 shadow-sm' : 'text-slate-400 hover:text-emerald-600'}`}
             >
                <span className="inline-flex items-center gap-2">
                  <RadioTower size={12} />
                  {copy.liveExchange}
                </span>
             </button>
          </div>
        </div>

        <div className="space-y-1.5">
            <label className="text-[10px] font-black text-slate-400 uppercase tracking-widest ml-1">
            {copy.modeLabel}
          </label>
          <div className="relative">
            <select
              className="w-full bg-card border-2 border-slate-100 dark:border-slate-800 rounded-2xl px-5 py-4 text-sm font-bold text-foreground appearance-none focus:border-blue-600 outline-none"
              value={form.mode}
              onChange={(e) =>
                setForm((s) => ({ ...s, mode: e.target.value }))
              }
            >
              {dcaPlan && !isEdit ? <option value="">{copy.dcaModePlaceholder || "Kies uitvoering"}</option> : null}
              <option value="manual">{copy.modeManual}</option>
              <option value="semi-auto">{copy.modeSemiAuto}</option>
              <option value="auto">{copy.modeAuto}</option>
            </select>
            <div className="absolute right-5 top-1/2 -translate-y-1/2 pointer-events-none opacity-40">
               ▼
            </div>
          </div>
          {dcaPlan && !isEdit ? (
            <p className="px-1 text-xs font-semibold text-slate-600">
              {copy.dcaModeHelp || "Handmatig maakt een voorstel; automatisch plaatst na de geplande veiligheidscheck zelf een order."}
            </p>
          ) : null}
        </div>
      </div>

      {form.is_live ? (
        <div className="space-y-2">
          <p className="text-xs font-medium leading-relaxed text-slate-600 dark:text-slate-300">
            {copy.liveExchangeConnectionHelp}
          </p>
          {!isEdit ? (
            <div className="grid grid-cols-1 gap-2 sm:grid-cols-2" role="group" aria-label={copy.exchangeTimingLabel}>
              <button type="button" aria-pressed={exchangeChoice === "later"}
                onClick={() => setExchangeChoice("later")}
                className={`rounded-xl border p-3 text-left text-sm font-bold ${exchangeChoice === "later" ? "border-blue-600 bg-blue-50 text-blue-800" : "border-slate-200 text-slate-600"}`}>
                {copy.exchangeLater}
              </button>
              <button type="button" aria-pressed={exchangeChoice === "now"}
                onClick={() => setExchangeChoice("now")}
                className={`rounded-xl border p-3 text-left text-sm font-bold ${exchangeChoice === "now" ? "border-blue-600 bg-blue-50 text-blue-800" : "border-slate-200 text-slate-600"}`}>
                {copy.exchangeNow}
              </button>
            </div>
          ) : null}
          {exchangeChoice === "later" && !isEdit ? (
            <p className="text-xs font-semibold text-amber-700 dark:text-amber-300">{copy.exchangeLaterHelp}</p>
          ) : null}
          {(exchangeChoice === "now" || isEdit) ? (
            <SystemConnectivity variant="inline" onConnectionChanged={() => setSubmitError("")}
              onConnectionStatusChange={setExchangeConnected} />
          ) : null}
          {exchangeChoice === "now" && !exchangeConnected && !isEdit ? (
            <p className="text-xs font-semibold text-amber-700 dark:text-amber-300">{copy.exchangeNotConnectedHelp}</p>
          ) : null}
          {exchangeChoice === "now" && exchangeConnected && !isEdit ? (
            <p className="text-xs font-semibold text-red-700 dark:text-red-300">{copy.exchangeConnectedLiveHelp}</p>
          ) : null}
        </div>
      ) : null}
 
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div className="space-y-1.5">
            <label className="text-[10px] font-black text-slate-400 uppercase tracking-widest ml-1">
            {copy.riskLabel}
          </label>
          <div className="relative">
            <select
              className="w-full bg-card border-2 border-slate-100 dark:border-slate-800 rounded-2xl px-5 py-4 text-sm font-bold text-foreground appearance-none focus:border-blue-600 outline-none"
              value={form.risk_profile}
              onChange={(e) =>
                setForm((s) => ({
                  ...s,
                  risk_profile: e.target.value,
                }))
              }
            >
              {riskProfiles.map((r) => (
                <option key={r.value} value={r.value}>
                  {r.label}
                </option>
              ))}
            </select>
            <div className="absolute right-5 top-1/2 -translate-y-1/2 pointer-events-none opacity-40">
               ▼
            </div>
          </div>
          <p className="px-1 text-xs text-slate-500">{copy.riskProfileScope}</p>
        </div>

        <div className="space-y-1.5">
          <label className="text-[10px] font-black text-slate-400 uppercase tracking-widest ml-1">
            {copy.baseCurrencyLabel}
          </label>
          <div className="relative">
            <select
              className="w-full bg-card border-2 border-slate-100 dark:border-slate-800 rounded-2xl px-5 py-4 text-sm font-bold text-foreground appearance-none focus:border-blue-600 outline-none"
              value={form.base_currency}
              onChange={(e) =>
                setForm((s) => ({
                  ...s,
                  base_currency: e.target.value,
                }))
              }
            >
              <option value="EUR">{copy.currencyEuro}</option>
              <option value="USD">{copy.currencyUsd}</option>
            </select>
            <div className="absolute right-5 top-1/2 -translate-y-1/2 pointer-events-none opacity-40">
               ▼
            </div>
          </div>
        </div>
      </div>

      {(guidedMode || requiresExplicitBudget || dcaPlan) && (
        guidedMode ? (
          <div className="space-y-4 rounded-[28px] border border-slate-200 bg-white p-5">
            <div className="grid gap-4 md:grid-cols-2">
              {[
                ["budget_total_eur", copy.totalBudgetLabel, copy.totalBudgetHelp],
                ["budget_daily_limit_eur", cadenceSpendLabel, cadenceSpendHelp],
              ].map(([key, label, helpText]) => (
                <div key={key} className="space-y-1.5">
                  <label className="text-[10px] font-black text-slate-400 uppercase tracking-widest ml-1">
                    {label}
                  </label>
                  <input
                    type="number"
                    min="0"
                    step="0.01"
                    name={key}
                    className="w-full bg-card border-2 border-slate-100 dark:border-slate-800 rounded-2xl px-4 py-3 text-sm font-bold text-foreground focus:border-blue-600 transition-all outline-none"
                    value={form[key]}
                    onChange={(e) => {
                      const value = Number(e.target.value);
                      setForm((s) => {
                        if (key !== "budget_daily_limit_eur" || showAdvancedBudget || dcaPlan) {
                          return { ...s, [key]: value };
                        }

                        return {
                          ...s,
                          budget_daily_limit_eur: value,
                          budget_min_order_eur: value,
                          budget_max_order_eur: value,
                        };
                      });
                    }}
                  />
                  <p className="px-1 text-[11px] font-semibold leading-relaxed text-slate-500">
                    {helpText}
                  </p>
                </div>
              ))}
            </div>

            {dcaSchedule ? (
              <div className="rounded-2xl border border-blue-100 bg-blue-50 px-4 py-3 text-sm font-semibold text-blue-800">
                {copy.dcaBudgetExample || "This daily limit does not change the saved DCA schedule or planned amount. It must allow at least that amount for a purchase."}
              </div>
            ) : null}

            <button
              type="button"
              onClick={() => setShowAdvancedBudget((current) => !current)}
              className="inline-flex items-center gap-2 rounded-2xl border border-slate-200 px-4 py-2 text-[10px] font-black uppercase tracking-[0.18em] text-slate-600 transition hover:border-blue-200 hover:text-blue-700"
            >
              {showAdvancedBudget
                ? copy.hideAdvancedBudget || "Hide advanced budget controls"
                : copy.showAdvancedBudget || "Custom order limits"}
              {showAdvancedBudget ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
            </button>

            {showAdvancedBudget ? (
              <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                {[
                  ["budget_daily_limit_eur", copy.dailyLimitLabel, copy.dailyLimitHelp],
                  ["budget_min_order_eur", copy.minOrderLabel, copy.minOrderHelp],
                  ["budget_max_order_eur", copy.maxOrderLabel, copy.maxOrderHelp],
                ].map(([key, label, helpText]) => (
                  <div key={key} className="space-y-1.5">
                    <label className="text-[10px] font-black text-slate-400 uppercase tracking-widest ml-1">
                      {label}
                    </label>
                    <input
                      type="number"
                      min="0"
                      step="0.01"
                      name={key}
                      className="w-full bg-card border-2 border-slate-100 dark:border-slate-800 rounded-2xl px-4 py-3 text-sm font-bold text-foreground focus:border-blue-600 transition-all outline-none"
                      value={form[key]}
                      onChange={(e) => setForm((s) => ({ ...s, [key]: Number(e.target.value) }))}
                    />
                    <p className="px-1 text-[11px] font-semibold leading-relaxed text-slate-500">
                      {helpText}
                    </p>
                  </div>
                ))}
              </div>
            ) : null}
          </div>
        ) : (
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            {[
              ["budget_total_eur", copy.totalBudgetLabel, copy.totalBudgetHelp],
              ["budget_daily_limit_eur", copy.dailyLimitLabel, copy.dailyLimitHelp],
              ["budget_min_order_eur", copy.minOrderLabel, copy.minOrderHelp],
              ["budget_max_order_eur", copy.maxOrderLabel, copy.maxOrderHelp],
            ].map(([key, label, helpText]) => (
              <div key={key} className="space-y-1.5">
                <label className="text-[10px] font-black text-slate-400 uppercase tracking-widest ml-1">
                  {label}
                </label>
                <input
                  type="number"
                  min="0"
                  step="0.01"
                  name={key}
                  className="w-full bg-card border-2 border-slate-100 dark:border-slate-800 rounded-2xl px-4 py-3 text-sm font-bold text-foreground focus:border-blue-600 transition-all outline-none"
                  value={form[key]}
                  onChange={(e) => setForm((s) => ({ ...s, [key]: Number(e.target.value) }))}
                />
                <p className="px-1 text-[11px] font-semibold leading-relaxed text-slate-500">
                  {helpText}
                </p>
              </div>
            ))}
          </div>
        )
      )}

      <p className="rounded-lg bg-amber-50 px-3 py-2 text-xs font-semibold text-amber-900 dark:bg-amber-950/30 dark:text-amber-200">{pageCopy.focus?.zeroLimitMeaning}</p>

      {!form.is_live && (
        <div className="space-y-1.5 rounded-2xl border border-blue-100 bg-blue-50/50 p-4">
          <label className="text-[10px] font-black text-blue-700 uppercase tracking-widest" htmlFor="paper_initial_cash_eur">
            {copy.paperInitialCashLabel}
          </label>
          <input
            id="paper_initial_cash_eur"
            type="number"
            min="0"
            step="0.01"
            name="paper_initial_cash_eur"
            disabled={isEdit && Number(sourceData?.paper_initial_cash_eur || 0) > 0}
            className="w-full bg-card border-2 border-blue-100 rounded-2xl px-4 py-3 text-sm font-bold text-foreground focus:border-blue-600 outline-none disabled:opacity-60"
            value={form.paper_initial_cash_eur}
            onChange={(e) => setForm((current) => ({ ...current, paper_initial_cash_eur: Number(e.target.value) }))}
          />
          <p className="text-[11px] font-semibold leading-relaxed text-slate-600">
            {copy.paperInitialCashHelp}
          </p>
        </div>
      )}

      {dcaPlan ? (
        <div className="rounded-2xl border border-blue-200 bg-blue-50 p-4 text-sm text-blue-950" aria-live="polite">
          <p className="font-black">{copy.dcaReviewTitle || "DCA-plan en botgrenzen"}</p>
          <p className="mt-2">
            {dcaSchedule}: {dcaPlan.variable
              ? `${formatEuro(dcaPlan.minimum)}–${formatEuro(dcaPlan.maximum)}`
              : formatEuro(dcaPlan.base)} · {form.mode === "auto" ? copy.modeAuto : form.mode === "semi-auto" ? copy.modeSemiAuto : form.mode === "manual" ? copy.modeManual : (copy.dcaModeUnchosen || "uitvoering nog niet gekozen")}
          </p>
          <p className="mt-1">
            {(form.is_live
              ? copy.dcaReviewLiveBudget || "Totale botlimiet {total}. Beschikbaar exchangesaldo wordt pas bij uitvoering gecontroleerd."
              : copy.dcaReviewBudget || "Paper-startkas {cash}; totale botlimiet {total}. De limiet is geen kassaldo.")
              .replace("{cash}", formatEuro(Number(form.paper_initial_cash_eur || 0)))
              .replace("{total}", form.budget_total_eur === "" ? (copy.dcaBudgetUnchosen || "nog niet gekozen") : formatEuro(Number(form.budget_total_eur)))}
          </p>
          {dcaCapacity !== null ? (
            <p className="mt-1 font-semibold">
              {(copy.dcaReviewCapacity || "Bij het hoogste planbedrag dekt de limiet {count} aankoopmomenten.")
                .replace("{count}", String(dcaCapacity))}
            </p>
          ) : null}
          {form.mode === "auto" && !form.is_live ? (
            <p className="mt-2 text-xs font-semibold">
              {copy.dcaPaperAutoNote || "Automatische Paper-uitvoering vereist voldoende Paper-kas en een actuele koers; bij een blokkade wordt geen order geplaatst."}
            </p>
          ) : null}
        </div>
      ) : null}

      {/* PROFILE DESCRIPTION */}
      <div className="p-4 rounded-xl bg-slate-50 dark:bg-slate-900/50 border-2 border-slate-100 dark:border-slate-800 flex items-center gap-4 transition-all hover:bg-slate-100">
         <div className="w-10 h-10 rounded-xl bg-card border border-slate-100 shadow-sm flex items-center justify-center text-lg">
            <SelectedRiskIcon size={18} className="text-slate-700" />
         </div>
         <div className="text-[11px] font-bold text-slate-500 leading-relaxed italic">
            {selectedRisk.description}
         </div>
      </div>

      {submitError ? (
        <div className="rounded-2xl border border-red-200 bg-red-50 px-4 py-3 text-sm font-semibold text-red-700">
          {submitError}
        </div>
      ) : null}

      {riskAcknowledgement ? (
        <div className="rounded-2xl border border-amber-300 bg-amber-50 px-4 py-4 text-sm text-amber-950">
          <p className="font-black">{riskCopy.riskAcknowledgementTitle || "Bevestig de risicowijziging"}</p>
          <p className="mt-1 font-medium leading-relaxed">
            {riskAcknowledgement.message || riskCopy.riskAcknowledgementBody || "Deze wijziging verhoogt risico of automatisering. Bevestig alleen als je dit bewust wilt opslaan."}
          </p>
          <div className="mt-4 flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
            <button
              type="button"
              disabled={loading}
              onClick={() => setRiskAcknowledgement(null)}
              className={actionButtonStyles({ variant: "secondary" })}
            >
              {riskCopy.riskAcknowledgementCancel || "Wijziging aanpassen"}
            </button>
            <button
              type="button"
              disabled={loading}
              onClick={() => submitForm(true)}
              className={actionButtonStyles({ variant: "primary" })}
            >
              {riskCopy.riskAcknowledgementConfirm || "Ik begrijp dit en sla op"}
            </button>
          </div>
        </div>
      ) : null}

      {!hideActions ? (
        <div className="flex flex-col-reverse gap-3 border-t border-slate-100 pt-6 sm:flex-row sm:justify-end">
          <button
            type="button"
            onClick={onCancel}
            disabled={loading}
            className={actionButtonStyles({ variant: "secondary" })}
          >
            {cancelLabel || "Annuleren"}
          </button>
          <button
            type="submit"
            disabled={loading}
            className={actionButtonStyles({ variant: "primary" })}
          >
            {loading ? (
              <>
                <span className="h-4 w-4 animate-spin rounded-full border-2 border-white/30 border-t-white" />
                {submitBusyLabel || submitLabel || "Opslaan..."}
              </>
            ) : (
              submitLabel || "Opslaan"
            )}
          </button>
        </div>
      ) : null}
    </form>
  );
});

export default AddBotForm;
