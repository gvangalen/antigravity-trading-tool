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
import { useModal } from "@/components/modal/ModalProvider";
import { fetchAuth } from "@/lib/api/auth";

import { Wallet, TrendingUp } from "lucide-react";
import CurveEditor from "@/components/decision/CurveEditor";
import { useTranslation } from "@/app/providers/I18nProvider";
import { getSetupId } from "@/lib/setup/activeSetup";

const StrategyForm = forwardRef(function StrategyForm({
  onSubmit,
  setups = [],
  strategy = null, // The strategy object being edited
  isEdit = false,
  hideSubmit = false,
}, ref) {
  const { t } = useTranslation();
  const copy = t?.strategies?.form || {};
  const { showSnackbar } = useModal();
  const formRef = useRef(null);

  const [error, setError] = useState("");
  const [curves, setCurves] = useState([]);
  const [saving, setSaving] = useState(false);

  /* ================= LOAD CURVES ================= */

  useEffect(() => {
    loadCurves();
  }, []);

  async function loadCurves() {
    try {
      const res = await fetchAuth("/api/curves/execution");
      setCurves(res || []);
    } catch (e) {
      console.error("Failed to load curves", e);
    }
  }

  /* ================= FORM STATE ================= */

  const [form, setForm] = useState({
    name: strategy?.name || "",

    setup_id: strategy?.setup_id || "",
    symbol: strategy?.symbol || "",
    timeframe: strategy?.timeframe || "",

    entry: strategy?.entry || "",
    targetsText: Array.isArray(strategy?.targets)
      ? strategy.targets.map(t => typeof t === 'object' ? t.price : t).join(", ")
      : "",
    stop_loss: strategy?.stop_loss || "",

    base_amount:
      strategy?.base_amount ||
      strategy?.amount ||
      "",

    execution_mode: strategy?.execution_mode || "fixed",

    decision_curve: strategy?.decision_curve || null,

    curve_name:
      strategy?.decision_curve_name ||
      strategy?.decision_curve?.name ||
      "",

    selected_curve_id:
      strategy?.decision_curve_id || (strategy?.execution_mode === 'custom' ? 'existing' : "new"),

    is_active: strategy?.is_active ?? true,
  });

  // Sync form when strategy changes
  useEffect(() => {
    if (strategy) {
      setForm({
        name: strategy.name || "",
        setup_id: strategy.setup_id || "",
        symbol: strategy.symbol || "",
        timeframe: strategy.timeframe || "",
        entry: strategy.entry || "",
        targetsText: Array.isArray(strategy.targets)
          ? strategy.targets.map(t => typeof t === 'object' ? t.price : t).join(", ")
          : "",
        stop_loss: strategy.stop_loss || "",
        base_amount: strategy.base_amount || strategy.amount || "",
        execution_mode: strategy.execution_mode || "fixed",
        decision_curve: strategy.decision_curve || null,
        curve_name: strategy.decision_curve_name || strategy.decision_curve?.name || "",
        selected_curve_id: strategy.decision_curve_id || (strategy.execution_mode === 'custom' ? 'existing' : "new"),
        is_active: strategy.is_active ?? true,
      });
    }
  }, [strategy]);

  /* ================= FILTER SETUPS ================= */

  const availableSetups = useMemo(() => {
    return setups.filter((s) => {
      const type = String(s.setup_type || "").toLowerCase();
      return type === "dca" || type === "trade";
    });
  }, [setups]);

  /* ================= SELECTED SETUP ================= */

  const selectedSetup = useMemo(() => {
    return availableSetups.find(
      (s) => String(getSetupId(s)) === String(form.setup_id)
    );
  }, [form.setup_id, availableSetups]);

  const setupType = String(
    selectedSetup?.setup_type ||
    strategy?.setup_type ||
    strategy?.setup?.setup_type ||
    ""
  ).toLowerCase();
  
  const isDca = setupType === "dca";
  const isTrade = setupType === "trade";

  /* ================= HANDLERS ================= */

  const handleChange = (e) => {
    const { name, value } = e.target;

    if (name === "setup_id") {
      const selected = availableSetups.find(
        (s) => String(getSetupId(s)) === value
      );

      setForm((p) => ({
        ...p,
        setup_id: value,
        symbol: selected?.symbol || "",
        timeframe: selected?.timeframe || "",
      }));
      return;
    }

    if (name === "execution_mode") {
      if (value === "fixed") {
        setForm((p) => ({
          ...p,
          execution_mode: "fixed",
          decision_curve: null,
          curve_name: "",
          selected_curve_id: "",
        }));
      } else {
        setForm((p) => ({
          ...p,
          execution_mode: "custom",
          selected_curve_id: "new",
        }));
      }
      return;
    }

    if (name === "selected_curve_id") {
    if (value === "new") {
      setForm((p) => ({
        ...p,
        selected_curve_id: "new",
        decision_curve: null,
        curve_name: "",
      }));
    } else {
      const selected = curves.find(
        (c) => String(c.id) === value
      );
  
      setForm((p) => ({
        ...p,
        selected_curve_id: value,
        decision_curve: selected?.curve || null,
        curve_name: selected?.name ?? "",
      }));
    }
    return;
  }

    setForm((p) => ({ ...p, [name]: value }));
  };

  /* ================= VALIDATION ================= */

  const isValid =
    form.name.trim() !== "" &&
    form.setup_id &&
    setupType !== "" &&
    Number(form.base_amount) > 0 &&
    (
      form.execution_mode === "fixed" ||
      (form.decision_curve &&
        form.decision_curve.points?.length >= 2 &&
        form.curve_name.trim() !== "")
    ) &&
    (
      isDca ||
      (
        isTrade &&
        form.entry !== "" &&
        form.targetsText !== "" &&
        form.stop_loss !== ""
      )
    );

  // Debugging
  useEffect(() => {
    if (isEdit) {
      console.log("Form Validation Check:", {
        isValid,
        name: form.name,
        setup_id: form.setup_id,
        setupType,
        base_amount: form.base_amount,
        execution_mode: form.execution_mode,
        hasCurve: !!form.decision_curve,
        curveName: form.curve_name,
        isTrade,
        entry: form.entry,
        targets: form.targetsText,
        stopLoss: form.stop_loss
      });
    }
  }, [isValid, form, isEdit, setupType, isTrade]);
  /* ================= SUBMIT ================= */

  const submitForm = useCallback(async () => {
    if (saving) {
      return { ok: false, reason: "busy" };
    }

    if (formRef.current && !formRef.current.reportValidity()) {
      return { ok: false, reason: "validation" };
    }

    if (!isValid) {
      setError(copy.validationError);
      return { ok: false, reason: "validation" };
    }

    setError("");
    setSaving(true);

    const targets = form.targetsText
      .split(",")
      .map((t) => parseFloat(t.trim()))
      .filter((n) => !Number.isNaN(n));

    const payload = {
      name: form.name.trim(),
      setup_id: Number(form.setup_id),
      symbol: form.symbol.trim() || undefined,
      timeframe: form.timeframe.trim() || undefined,
      base_amount: Number(form.base_amount),
      execution_mode: form.execution_mode,
      setup_type: setupType,
      decision_curve:
        form.execution_mode === "fixed"
          ? null
          : {
              ...form.decision_curve,
              name: form.curve_name.trim(),
            },
      decision_curve_name:
        form.execution_mode === "fixed"
          ? null
          : form.curve_name.trim(),
      decision_curve_id:
        form.selected_curve_id !== "new" && form.selected_curve_id !== "existing"
          ? Number(form.selected_curve_id)
          : null,
      is_active: form.is_active,
    };

    if (isTrade) {
      payload.entry = form.entry !== "" ? Number(form.entry) : null;
      payload.targets = targets;
      payload.stop_loss = form.stop_loss !== "" ? Number(form.stop_loss) : null;
    }

    try {
      await onSubmit(payload);
      showSnackbar(copy.savedSuccess, "success");
      return { ok: true, data: payload };
    } catch (err) {
      console.error(err);
      setError(copy.saveFailed);
      return { ok: false, reason: "api", error: err };
    } finally {
      setSaving(false);
    }
  }, [copy.saveFailed, copy.savedSuccess, copy.validationError, form, isTrade, isValid, onSubmit, saving, setupType, showSnackbar]);

  useImperativeHandle(ref, () => ({
    submit: submitForm,
    isSubmitting: () => saving,
  }), [saving, submitForm]);

  const handleSubmit = async (e) => {
    e.preventDefault();
    await submitForm();
  };

  /* ================= UI ================= */

  return (
    <form ref={formRef} onSubmit={handleSubmit} className="space-y-6">
      {!isEdit && (
        <h2 className="text-xl font-bold flex items-center gap-2">
          {isDca ? (
            <Wallet className="w-5 h-5 text-blue-600" />
          ) : (
            <TrendingUp className="w-5 h-5 text-blue-600" />
          )}
          {copy.newTitle}
        </h2>
      )}

      <input
        name="name"
        value={form.name}
        onChange={handleChange}
        placeholder={copy.namePlaceholder}
        className="input"
      />

      <select
        name="setup_id"
        value={form.setup_id}
        onChange={handleChange}
        className="input"
      >
        <option value="">{copy.setupPlaceholder}</option>
        {availableSetups.map((s) => (
          <option key={getSetupId(s)} value={getSetupId(s) ?? ""}>
            {s.name} ({s.symbol})
          </option>
        ))}
      </select>

      <div className="grid gap-4 sm:grid-cols-2">
        <label className="block space-y-2">
          <span className="text-sm font-semibold">{copy.assetLabel || "Asset"}</span>
          <input
            name="symbol"
            value={form.symbol}
            onChange={handleChange}
            placeholder={copy.assetPlaceholder || "BTC"}
            className="input"
          />
        </label>
        <label className="block space-y-2">
          <span className="text-sm font-semibold">{copy.timeframeLabel || "Timeframe"}</span>
          <input
            name="timeframe"
            value={form.timeframe}
            onChange={handleChange}
            placeholder={copy.timeframePlaceholder || "4H"}
            className="input"
          />
        </label>
      </div>

      {/* BREAKOUT */}
      {isTrade && (
        <>
          <input
            name="entry"
            type="number"
            value={form.entry}
            onChange={handleChange}
            placeholder={copy.entryPlaceholder}
            className="input"
          />
          <input
            name="targetsText"
            value={form.targetsText}
            onChange={handleChange}
            placeholder={copy.targetsPlaceholder}
            className="input"
          />
          <input
            name="stop_loss"
            type="number"
            value={form.stop_loss}
            onChange={handleChange}
            placeholder={copy.stopLossPlaceholder}
            className="input"
          />
        </>
      )}

      {/* AMOUNT */}
      <input
        type="number"
        name="base_amount"
        value={form.base_amount}
        onChange={handleChange}
        placeholder={copy.amountPlaceholder}
        className="input"
      />

      {/* EXECUTION LOGIC */}
      <div className="space-y-3">
        <label className="text-sm font-semibold">{copy.executionLabel}</label>

        <label className="flex gap-3 p-3 border rounded-xl cursor-pointer">
          <input
            type="radio"
            name="execution_mode"
            value="fixed"
            checked={form.execution_mode === "fixed"}
            onChange={handleChange}
          />
          <div>{copy.fixedAmount}</div>
        </label>

        <label className="flex gap-3 p-3 border rounded-xl cursor-pointer">
          <input
            type="radio"
            name="execution_mode"
            value="custom"
            checked={form.execution_mode === "custom"}
            onChange={handleChange}
          />
          <div>{copy.curveBased}</div>
        </label>
      </div>

      {/* CURVE */}
      {form.execution_mode === "custom" && (
        <>
          <select
            name="selected_curve_id"
            value={form.selected_curve_id}
            onChange={handleChange}
            className="input"
          >
            <option value="new">{copy.newCurve}</option>
            {curves.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name}
              </option>
            ))}
          </select>

          {(form.selected_curve_id === "new" || form.selected_curve_id === "existing") && (
            <>
              <input
                name="curve_name"
                value={form.curve_name}
                onChange={handleChange}
                placeholder={copy.curveNamePlaceholder}
                className="input"
              />
              <CurveEditor
                value={form.decision_curve}
                onChange={(curve) =>
                  setForm((p) => ({ ...p, decision_curve: curve }))
                }
              />
            </>
          )}
        </>
      )}

      {error && <p className="text-red-500">{error}</p>}

      {!hideSubmit && (
        <button disabled={!isValid || saving} className="btn-primary w-full py-3 text-sm font-black uppercase tracking-widest disabled:cursor-not-allowed disabled:opacity-60">
          {saving ? copy.saveButton : isEdit ? copy.updateButton : copy.saveButton}
        </button>
      )}
    </form>
  );
});

export default StrategyForm;
