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
import { useTranslation } from "@/app/providers/I18nProvider";
import { useModal } from "@/components/modal/ModalProvider";
import { actionButtonStyles } from "@/components/ui/actionButtonStyles";

const RISK_PROFILE_ICONS = {
  conservative: "🛡️",
  balanced: "⚖️",
  aggressive: "🚀",
};

/**
 * AddBotForm — Tradamind 2.5 (FINAL)
 */
const extractErrorMessage = (error, fallback) => {
  if (error?.body) {
    try {
      const parsed = JSON.parse(error.body);
      if (typeof parsed?.detail === "string" && parsed.detail.trim()) {
        return parsed.detail.trim();
      }
    } catch {
      // Ignore parse failure and use fallback.
    }
  }

  if (typeof error?.message === "string" && error.message.trim()) {
    return error.message.trim();
  }

  return fallback;
};

const AddBotForm = forwardRef(function AddBotForm({
  initialData = null,
  initialValues = null,
  strategies = [],
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
}, ref) {
  const { t } = useTranslation();
  const copy = t?.botPage?.form || {};
  const pageCopy = t?.botPage || {};
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
    budget_total_eur: 0,
    budget_daily_limit_eur: 0,
    budget_min_order_eur: 0,
    budget_max_order_eur: 0,
    max_asset_exposure_pct: 100,
  });
  const [loading, setLoading] = useState(false);
  const [submitError, setSubmitError] = useState("");

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
      budget_total_eur: sourceData.budget_total_eur ?? sourceData.budget?.total_eur ?? 0,
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

  const getStrategyType = (s) =>
    (s?.strategy_type || s?.type || "manual").toUpperCase();

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

    const numericFields = [
      "budget_total_eur",
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

    return { ok: true };
  }, [copy.assetExposureValidation, copy.numericValidation, form, pageCopy.createValidation]);

  const submitForm = useCallback(async () => {
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
      name: String(form.name || "").trim(),
      strategy_id: Number(form.strategy_id),
      budget_total_eur: Number(form.budget_total_eur || 0),
      budget_daily_limit_eur: Number(form.budget_daily_limit_eur || 0),
      budget_min_order_eur: Number(form.budget_min_order_eur || 0),
      budget_max_order_eur: Number(form.budget_max_order_eur || 0),
      max_asset_exposure_pct: Number(form.max_asset_exposure_pct || 0),
    };

    setSubmitError("");
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
      const message = extractErrorMessage(
        error,
        saveFailedMessage || copy.saveFailed || "Opslaan van de bot mislukt."
      );
      setSubmitError(message);
      showSnackbar(message, "danger");
      return { ok: false, reason: "api", error };
    } finally {
      setLoading(false);
    }
  }, [
    copy.saveFailed,
    form,
    loading,
    onSaved,
    onSubmit,
    saveFailedMessage,
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
    <form ref={formRef} onSubmit={handleSubmit} className="space-y-6">
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

        {isEdit ? (
          <div className="w-full bg-slate-50 dark:bg-slate-900 border-2 border-slate-100 dark:border-slate-800 rounded-2xl px-5 py-4 text-sm font-bold text-muted cursor-not-allowed flex items-center justify-between">
            <span>{selectedStrategy ? `${selectedStrategy.name} · ${selectedStrategy.symbol}` : "—"}</span>
            <div className="text-[9px] bg-slate-200 dark:bg-slate-700 px-2 py-0.5 rounded-md uppercase tracking-tighter">{copy.lockedLabel}</div>
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
                  {s.display_name || `${s.name} · ${s.symbol} · ${s.timeframe}`}
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
        </div>
      )}

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
                {copy.paperTrading}
             </button>
             <button 
                type="button"
                onClick={() => setForm(s => ({ ...s, is_live: true }))}
                className={`flex-1 py-3 rounded-xl text-[10px] font-black uppercase tracking-widest transition-all ${form.is_live ? 'bg-white dark:bg-slate-800 text-emerald-600 shadow-sm' : 'text-slate-400 hover:text-emerald-600'}`}
             >
                {copy.liveExchange}
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
              <option value="manual">{copy.modeManual}</option>
              <option value="semi-auto">{copy.modeSemiAuto}</option>
              <option value="auto">{copy.modeAuto}</option>
            </select>
            <div className="absolute right-5 top-1/2 -translate-y-1/2 pointer-events-none opacity-40">
               ▼
            </div>
          </div>
        </div>
      </div>
 
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
                  {`${r.icon} ${r.label}`}
                </option>
              ))}
            </select>
            <div className="absolute right-5 top-1/2 -translate-y-1/2 pointer-events-none opacity-40">
               ▼
            </div>
          </div>
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

      {(form.is_live || form.mode !== "manual") && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          {[
            ["budget_total_eur", copy.totalBudgetLabel],
            ["budget_daily_limit_eur", copy.dailyLimitLabel],
            ["budget_min_order_eur", copy.minOrderLabel],
            ["budget_max_order_eur", copy.maxOrderLabel],
          ].map(([key, label]) => (
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
            </div>
          ))}
        </div>
      )}

      {/* PROFILE DESCRIPTION */}
      <div className="p-4 rounded-xl bg-slate-50 dark:bg-slate-900/50 border-2 border-slate-100 dark:border-slate-800 flex items-center gap-4 transition-all hover:bg-slate-100">
         <div className="w-10 h-10 rounded-xl bg-card border border-slate-100 shadow-sm flex items-center justify-center text-lg">
            {selectedRisk.icon}
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
