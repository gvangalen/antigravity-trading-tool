"use client";

import { useState, useEffect, useMemo } from "react";
import { useModal } from "@/components/modal/ModalProvider";
import { fetchAuth } from "@/lib/api/auth";

import { Wallet, TrendingUp } from "lucide-react";
import CurveEditor from "@/components/decision/CurveEditor";

export default function StrategyForm({
  onSubmit,
  setups = [],
  strategy = null, // The strategy object being edited
  isEdit = false,
  hideSubmit = false,
}) {
  const { showSnackbar } = useModal();

  const [error, setError] = useState("");
  const [curves, setCurves] = useState([]);

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
      (s) => String(s.id) === String(form.setup_id)
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
        (s) => String(s.id) === value
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

  const handleSubmit = async (e) => {
  e.preventDefault();

  if (!isValid) {
    setError("❌ Vul alle velden correct in.");
    return;
  }

  const targets = form.targetsText
    .split(",")
    .map((t) => parseFloat(t.trim()))
    .filter((n) => !Number.isNaN(n));

  const payload = {
    name: form.name.trim(),
    setup_id: Number(form.setup_id),

    base_amount: Number(form.base_amount),
    execution_mode: form.execution_mode,

    // 🔥 belangrijk voor backend consistency
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

  // 🔥 TRADE velden (fix: geen NaN)
  if (isTrade) {
    payload.entry = form.entry !== "" ? Number(form.entry) : null;
    payload.targets = targets;
    payload.stop_loss = form.stop_loss !== "" ? Number(form.stop_loss) : null;
  }

  try {
    await onSubmit(payload);
    showSnackbar("Strategie opgeslagen", "success");
  } catch (err) {
    console.error(err);
    setError("Opslaan mislukt.");
  }
};

  /* ================= UI ================= */

  return (
    <form onSubmit={handleSubmit} className="space-y-6">
      {!isEdit && (
        <h2 className="text-xl font-bold flex items-center gap-2">
          {isDca ? (
            <Wallet className="w-5 h-5 text-blue-600" />
          ) : (
            <TrendingUp className="w-5 h-5 text-blue-600" />
          )}
          Nieuwe Strategie
        </h2>
      )}

      {/* 🟢 STATUS TOGGLE (ONLY IN EDIT) */}
      {isEdit && (
        <div className="flex items-center justify-between p-4 bg-[var(--color-border-subtle)] border border-slate-100 rounded-2xl mb-6">
           <div>
              <div className="text-[10px] font-black text-secondary uppercase tracking-widest mb-1">Status</div>
              <div className="text-sm font-bold text-slate-800">{form.is_active ? "Actief" : "Gepauzeerd"}</div>
           </div>
           <button
             type="button"
             onClick={() => setForm(p => ({ ...p, is_active: !p.is_active }))}
             className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors focus:outline-none ${form.is_active ? "bg-green-500" : "bg-slate-300"}`}
           >
              <span className={`inline-block h-4 w-4 transform rounded-full bg-card transition-transform ${form.is_active ? "translate-x-6" : "translate-x-1"}`} />
           </button>
        </div>
      )}

      <input
        name="name"
        value={form.name}
        onChange={handleChange}
        placeholder="Naam"
        className="input"
      />

      <select
        name="setup_id"
        value={form.setup_id}
        onChange={handleChange}
        className="input"
      >
        <option value="">-- Kies een setup --</option>
        {availableSetups.map((s) => (
          <option key={s.id} value={s.id}>
            {s.name} ({s.symbol})
          </option>
        ))}
      </select>

      {/* BREAKOUT */}
      {isTrade && (
        <>
          <input
            name="entry"
            type="number"
            value={form.entry}
            onChange={handleChange}
            placeholder="Instap"
            className="input"
          />
          <input
            name="targetsText"
            value={form.targetsText}
            onChange={handleChange}
            placeholder="Doelen (komma gescheiden)"
            className="input"
          />
          <input
            name="stop_loss"
            type="number"
            value={form.stop_loss}
            onChange={handleChange}
            placeholder="Stop-loss"
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
        placeholder="Bedrag (€)"
        className="input"
      />

      {/* EXECUTION LOGIC */}
      <div className="space-y-3">
        <label className="text-sm font-semibold">Uitvoering</label>

        <label className="flex gap-3 p-3 border rounded-xl cursor-pointer">
          <input
            type="radio"
            name="execution_mode"
            value="fixed"
            checked={form.execution_mode === "fixed"}
            onChange={handleChange}
          />
          <div>Vast bedrag</div>
        </label>

        <label className="flex gap-3 p-3 border rounded-xl cursor-pointer">
          <input
            type="radio"
            name="execution_mode"
            value="custom"
            checked={form.execution_mode === "custom"}
            onChange={handleChange}
          />
          <div>Op basis van curve</div>
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
            <option value="new">Nieuwe curve</option>
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
                placeholder="Naam curve"
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
        <button id="strategy-edit-submit" disabled={!isValid} className="btn-primary w-full py-3 text-sm font-black uppercase tracking-widest">
          {isEdit ? "Bijwerken" : "Opslaan"}
        </button>
      )}
    </form>
  );
}
