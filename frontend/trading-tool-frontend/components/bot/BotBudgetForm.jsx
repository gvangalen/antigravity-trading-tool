"use client";

import {
  forwardRef,
  useCallback,
  useEffect,
  useImperativeHandle,
  useRef,
  useState,
} from "react";
import { Layers } from "lucide-react";
import { TradingSlider } from "@/components/ui/Slider";
import { useTranslation } from "@/app/providers/I18nProvider";
import { useModal } from "@/components/modal/ModalProvider";
import { actionButtonStyles } from "@/components/ui/actionButtonStyles";

/* =====================================================
   Field wrapper
===================================================== */

function Field({ label, children }) {
  return (
    <div>
      <label className="block font-medium mb-1">{label}</label>
      {children}
    </div>
  );
}

/* =====================================================
   BotBudgetForm
===================================================== */

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

const BotBudgetForm = forwardRef(function BotBudgetForm({
  initialBudget,
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
  const copy = t?.botPage?.budgetForm || {};
  const { showSnackbar } = useModal();
  const formRef = useRef(null);

  const [form, setForm] = useState({
    total_eur: 0,
    daily_limit_eur: 0,
    max_order_eur: 0,
    max_asset_exposure_pct: 100,
  });
  const [loading, setLoading] = useState(false);
  const [submitError, setSubmitError] = useState("");

  useEffect(() => {
    if (!initialBudget) return;

    setForm({
      total_eur: initialBudget.total_eur ?? 0,
      daily_limit_eur: initialBudget.daily_limit_eur ?? 0,
      max_order_eur: initialBudget.max_order_eur ?? 0,
      max_asset_exposure_pct: initialBudget.max_asset_exposure_pct ?? 100,
    });
  }, [initialBudget]);

  useEffect(() => {
    onChange?.(form);
  }, [form, onChange]);

  const validateForm = useCallback(() => {
    if (formRef.current && !formRef.current.reportValidity()) {
      return {
        ok: false,
        message: copy.validationError || "Controleer de budgetvelden en probeer opnieuw.",
      };
    }

    const numericFields = [
      "total_eur",
      "daily_limit_eur",
      "max_order_eur",
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

    if (Number(form.total_eur) > 0 && Number(form.daily_limit_eur) > Number(form.total_eur)) {
      return {
        ok: false,
        message: copy.dailyLimitValidation || "Daglimiet mag niet hoger zijn dan het totale budget.",
      };
    }

    if (Number(form.total_eur) > 0 && Number(form.max_order_eur) > Number(form.total_eur)) {
      return {
        ok: false,
        message: copy.orderMaxValidation || "Maximale order mag niet hoger zijn dan het totale budget.",
      };
    }

    return { ok: true };
  }, [
    copy.assetExposureValidation,
    copy.dailyLimitValidation,
    copy.numericValidation,
    copy.orderMaxValidation,
    copy.validationError,
    form,
  ]);

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
      total_eur: Number(form.total_eur || 0),
      daily_limit_eur: Number(form.daily_limit_eur || 0),
      max_order_eur: Number(form.max_order_eur || 0),
      max_asset_exposure_pct: Number(form.max_asset_exposure_pct || 0),
    };

    setSubmitError("");
    setLoading(true);

    try {
      const savedBudget = await onSubmit(payload);
      if (successMessage) {
        showSnackbar(successMessage, "success");
      }
      onSaved?.(savedBudget ?? payload);
      return { ok: true, data: savedBudget ?? payload };
    } catch (error) {
      console.error(error);
      const message = extractErrorMessage(
        error,
        saveFailedMessage || copy.saveFailed || "Opslaan van budget en limieten mislukt."
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
    <form ref={formRef} onSubmit={handleSubmit} className="space-y-8 p-1">
      <div className="p-4 rounded-xl bg-blue-50 border border-blue-100 flex items-start gap-4 shadow-sm">
        <div className="p-2 rounded-lg bg-card text-blue-500 shadow-sm shrink-0">
          <Layers size={20} strokeWidth={2.5} />
        </div>
        <p className="text-xs font-bold text-blue-700/80 leading-relaxed italic">
          {copy.description}
        </p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        {/* Total budget */}
        <div className="space-y-2">
          <label className="text-[10px] font-black text-secondary uppercase tracking-widest pl-1">
            {copy.globalLimit}
          </label>
          <input
            type="number"
            min="0"
            step="0.01"
            name="total_eur"
            className="w-full bg-[var(--color-border-subtle)] border border-slate-200 rounded-2xl px-5 py-4 text-sm font-black text-foreground focus:ring-2 focus:ring-[var(--primary)] outline-none transition-all"
            value={form.total_eur}
            onChange={(e) =>
              setForm((s) => ({
                ...s,
                total_eur: Number(e.target.value),
              }))
            }
          />
        </div>

        {/* Daily limit */}
        <div className="space-y-2">
          <label className="text-[10px] font-black text-secondary uppercase tracking-widest pl-1">
            {copy.dailyCap}
          </label>
          <input
            type="number"
            min="0"
            step="0.01"
            name="daily_limit_eur"
            className="w-full bg-[var(--color-border-subtle)] border border-slate-200 rounded-2xl px-5 py-4 text-sm font-black text-foreground focus:ring-2 focus:ring-[var(--primary)] outline-none transition-all"
            value={form.daily_limit_eur}
            onChange={(e) =>
              setForm((s) => ({
                ...s,
                daily_limit_eur: Number(e.target.value),
              }))
            }
          />
        </div>

        {/* Max order */}
        <div className="space-y-2">
          <label className="text-[10px] font-black text-secondary uppercase tracking-widest pl-1">
            {copy.orderMax}
          </label>
          <input
            type="number"
            min="0"
            step="0.01"
            name="max_order_eur"
            className="w-full bg-[var(--color-border-subtle)] border border-slate-200 rounded-2xl px-5 py-4 text-sm font-black text-foreground focus:ring-2 focus:ring-[var(--primary)] outline-none transition-all"
            value={form.max_order_eur}
            onChange={(e) =>
              setForm((s) => ({
                ...s,
                max_order_eur: Number(e.target.value),
              }))
            }
          />
        </div>
      </div>

      {/* Asset exposure slider */}
      <div className="space-y-4 pt-4 border-t border-slate-100">
        <div className="flex items-center justify-between">
          <label className="text-[10px] font-black text-secondary uppercase tracking-[0.2em]">{copy.assetExposure}</label>
          <div className="text-xs font-black text-[var(--primary)] font-mono bg-blue-50 px-2 py-0.5 rounded-md">
            {form.max_asset_exposure_pct}% {copy.maxSuffix}
          </div>
        </div>

        <div className="bg-[var(--color-border-subtle)] border border-slate-100 p-8 rounded-[2rem] shadow-inner">
          <TradingSlider
            value={form.max_asset_exposure_pct}
            steps={[0, 25, 50, 75, 100]}
            onChange={(value) =>
              setForm((s) => ({
                ...s,
                max_asset_exposure_pct: value,
              }))
            }
          />
        </div>

        <div className="text-[9px] font-bold text-secondary uppercase tracking-tight text-center italic">
          {copy.assetExposureDescription}
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

export default BotBudgetForm;
