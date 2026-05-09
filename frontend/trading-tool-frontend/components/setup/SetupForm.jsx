"use client";

import "rc-slider/assets/index.css";
import Slider from "rc-slider";

import React, { useState, useEffect } from "react";
import { Settings, BarChart3, Save, Info, Rocket, Target } from "lucide-react";

import { saveNewSetup, updateSetup } from "@/lib/api/setups";
import { useModal } from "@/components/modal/ModalProvider";

export default function SetupForm({ onSaved, mode = "new", initialData = null }) {
  const isEdit = mode === "edit";
  const { showSnackbar } = useModal();

  // ----------------------------------------------------
  // SCORE MEANING
  // ----------------------------------------------------
  const scoreLabel = (v) => {
    if (v <= 25) return "Sterk bearish / risk-off";
    if (v <= 45) return "Bearish";
    if (v <= 60) return "Neutraal";
    if (v <= 75) return "Neutraal → bullish";
    if (v <= 90) return "Bullish";
    return "Euforisch / oververhit";
  };

  const rangeText = (min, max) => `${scoreLabel(min)} → ${scoreLabel(max)}`;

  // ----------------------------------------------------
  // STATE
  // ----------------------------------------------------
  const emptyForm = {
    name: "",
    symbol: "BTC",
    setupType: "dca", // ✅ nu alleen dca of trade
    timeframe: "1W",

    dcaFrequency: "weekly",
    dcaDay: "monday",
    dcaMonthDay: 1,
  };

  const [formData, setFormData] = useState(emptyForm);
  const [macroScore, setMacroScore] = useState([30, 70]);
  const [technicalScore, setTechnicalScore] = useState([40, 80]);
  const [marketScore, setMarketScore] = useState([20, 60]);
  const [loading, setLoading] = useState(false);

  // ----------------------------------------------------
  // LOAD FOR EDIT
  // ----------------------------------------------------
  useEffect(() => {
    if (!isEdit || !initialData) return;

    setFormData({
      name: initialData.name ?? "",
      symbol: initialData.symbol ?? "BTC",
      setupType: initialData.setup_type ?? "dca",
      timeframe: initialData.timeframe ?? "1W",

      dcaFrequency: initialData.dca_frequency ?? "weekly",
      dcaDay: initialData.dca_day ?? "monday",
      dcaMonthDay: initialData.dca_month_day ?? 1,
    });

    setMacroScore([
      initialData.min_macro_score ?? 30,
      initialData.max_macro_score ?? 70,
    ]);

    setTechnicalScore([
      initialData.min_technical_score ?? 40,
      initialData.max_technical_score ?? 80,
    ]);

    setMarketScore([
      initialData.min_market_score ?? 20,
      initialData.max_market_score ?? 60,
    ]);
  }, [isEdit, initialData]);

  // ----------------------------------------------------
  // HANDLERS
  // ----------------------------------------------------
  const handleChange = (e) => {
    const { name, value } = e.target;
    setFormData((p) => ({
      ...p,
      [name]: name === "dcaMonthDay" ? Number(value) : value,
    }));
  };

  const isDca = formData.setupType === "dca";
  const isTrade = formData.setupType === "trade";

  // ----------------------------------------------------
  // SUBMIT
  // ----------------------------------------------------
  const handleSubmit = async (e) => {
    e.preventDefault();
    setLoading(true);

    const payload = {
      name: formData.name?.trim(),
      symbol: formData.symbol,
      setup_type: formData.setupType,
      timeframe: formData.timeframe,

      ...(isDca && {
        dca_frequency: formData.dcaFrequency,
        dca_day: formData.dcaFrequency === "weekly" ? formData.dcaDay : null,
        dca_month_day:
          formData.dcaFrequency === "monthly"
            ? Number(formData.dcaMonthDay || 1)
            : null,
      }),

      ...(isTrade && {
        dca_frequency: null,
        dca_day: null,
        dca_month_day: null,
      }),

      min_macro_score: macroScore[0],
      max_macro_score: macroScore[1],
      min_technical_score: technicalScore[0],
      max_technical_score: technicalScore[1],
      min_market_score: marketScore[0],
      max_market_score: marketScore[1],
    };

    try {
      if (isEdit) {
        await updateSetup(initialData.id, payload);
        showSnackbar("Setup bijgewerkt", "success");
      } else {
        await saveNewSetup(payload);
        showSnackbar("Setup opgeslagen", "success");
        setFormData(emptyForm);
        setMacroScore([30, 70]);
        setTechnicalScore([40, 80]);
        setMarketScore([20, 60]);
      }

      onSaved?.();
    } catch (err) {
      console.error(err);
      showSnackbar("Opslaan mislukt", "danger");
    } finally {
      setLoading(false);
    }
  };

  // ----------------------------------------------------
  // STYLES
  // ----------------------------------------------------
  const fieldClass =
    "p-4 rounded-2xl bg-card border-2 border-slate-100 w-full text-sm font-bold text-foreground outline-none focus:border-blue-600 transition-all";

  const sectionClass =
    "rounded-3xl p-8 bg-gradient-to-br from-white to-slate-50/50 border-2 border-slate-100 space-y-8";

  const sectionTitle = (icon, text) => (
    <h3 className="flex items-center gap-2 font-semibold text-[1.05rem]">
      {icon}
      {text}
    </h3>
  );

  const scoreBlock = (title, score, setScore, description) => (
    <div className="bg-blue-50/30 border-2 border-blue-600/10 rounded-3xl p-8 space-y-8 transition-all hover:bg-blue-50/50">
      <div className="flex justify-between items-end">
        <div>
          <div className="text-[10px] font-black text-blue-600 uppercase tracking-widest mb-1.5">{title}</div>
          <div className="text-sm font-black text-foreground tracking-tight">{description}</div>
        </div>
        <div className="text-[11px] font-black text-blue-600 bg-card px-4 py-2 rounded-xl border-2 border-blue-600/20 font-mono shadow-sm">
          [ {score[0].toString().padStart(2, '0')} — {score[1].toString().padStart(2, '0')} ]
        </div>
      </div>

      <div className="relative py-6 px-2">
        {/* 🧼 CLEAN SLATE RAIL */}
        <div className="absolute inset-x-2 top-1/2 -translate-y-1/2 h-2.5 rounded-full bg-blue-100/50 border border-blue-200/50 overflow-hidden">
           {/* Digital ticks */}
           <div className="absolute inset-0 flex justify-between px-0">
             {[0, 25, 50, 75, 100].map(tick => (
               <div key={tick} className="w-[1px] h-full bg-blue-200/50" />
             ))}
           </div>
        </div>
        
        <Slider 
          range 
          min={0} 
          max={100} 
          value={score} 
          onChange={setScore}
          trackStyle={[{ backgroundColor: '#2563eb', height: 10, borderRadius: 5, border: '2px solid #1e40af', top: '51%' }]}
          handleStyle={[
            { borderColor: '#1e40af', height: 26, width: 26, marginTop: -9, backgroundColor: '#fff', boxShadow: '0 8px 16px rgba(30, 64, 175, 0.2)', borderWidth: 4, opacity: 1 },
            { borderColor: '#1e40af', height: 26, width: 26, marginTop: -9, backgroundColor: '#fff', boxShadow: '0 8px 16px rgba(30, 64, 175, 0.2)', borderWidth: 4, opacity: 1 }
          ]}
          railStyle={{ backgroundColor: 'transparent', height: 10 }}
        />
      </div>

      <div className="flex items-center gap-3 pt-6 border-t-2 border-slate-100">
        <div className="px-2 py-1 rounded bg-blue-600 text-[9px] font-black text-white uppercase tracking-widest shadow-sm">Phase Response</div>
        <div className="text-[12px] font-black text-slate-700 tracking-tight italic leading-none">
          {rangeText(score[0], score[1])}
        </div>
      </div>
    </div>
  );

  // ----------------------------------------------------
  // RENDER
  // ----------------------------------------------------
  return (
    <form onSubmit={handleSubmit} className="space-y-8">
      {/* BASIS */}
      <div className={sectionClass}>
        {sectionTitle(<Settings size={18} />, "Basisgegevens")}

        <input
          name="name"
          placeholder="Naam van de setup"
          value={formData.name}
          onChange={handleChange}
          className={fieldClass}
          required
        />

        {/* 🧬 BLUEPRINT TYPE SELECTOR */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <button
            type="button"
            onClick={() => setFormData(p => ({ ...p, setupType: 'dca' }))}
            className={`
              flex items-start gap-4 p-5 rounded-2xl border-2 transition-all text-left
              ${formData.setupType === 'dca' 
                ? 'bg-blue-50 border-blue-600 ring-4 ring-blue-600/5' 
                : 'bg-white border-slate-100 hover:border-blue-200'}
            `}
          >
            <div className={`p-3 rounded-xl ${formData.setupType === 'dca' ? 'bg-blue-600 text-white' : 'bg-slate-50 text-slate-400'}`}>
               <Rocket size={22} />
            </div>
            <div>
               <p className="font-black text-sm uppercase tracking-tight text-slate-900">DCA Blueprint</p>
               <p className="text-[11px] font-medium text-muted mt-1 leading-relaxed">Focus on long-term accumulation and market health.</p>
            </div>
          </button>

          <button
            type="button"
            onClick={() => setFormData(p => ({ ...p, setupType: 'trade' }))}
            className={`
              flex items-start gap-4 p-5 rounded-2xl border-2 transition-all text-left
              ${formData.setupType === 'trade' 
                ? 'bg-blue-50 border-blue-600 ring-4 ring-blue-600/5' 
                : 'bg-white border-slate-100 hover:border-blue-200'}
            `}
          >
            <div className={`p-3 rounded-xl ${formData.setupType === 'trade' ? 'bg-blue-600 text-white' : 'bg-slate-50 text-slate-400'}`}>
               <Target size={22} />
            </div>
            <div>
               <p className="font-black text-sm uppercase tracking-tight text-slate-900">Trade Blueprint</p>
               <p className="text-[11px] font-medium text-muted mt-1 leading-relaxed">Focus on execution-ready setups and technical validation.</p>
            </div>
          </button>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mt-2">
          <div className="space-y-1.5 flex-1">
            <label className="text-[10px] font-black uppercase text-[var(--text-light)] ml-1">Asset Symbol</label>
            <select
              name="symbol"
              value={formData.symbol}
              onChange={handleChange}
              className={fieldClass}
            >
              <option value="BTC">BTC (Bitcoin)</option>
              <option value="ETH">ETH (Ethereum)</option>
              <option value="SOL">SOL (Solana)</option>
            </select>
          </div>

          <div className="space-y-1.5 flex-1">
            <label className="text-[10px] font-black uppercase text-[var(--text-light)] ml-1">Timeframe</label>
            <select
              name="timeframe"
              value={formData.timeframe}
              onChange={handleChange}
              className={fieldClass}
            >
              <option value="1D">1D (Daily)</option>
              <option value="4H">4H (4 Hour)</option>
              <option value="1W">1W (Weekly)</option>
            </select>
          </div>
        </div>

        {/* DCA planning */}
        {isDca && (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            <select
              name="dcaFrequency"
              value={formData.dcaFrequency}
              onChange={handleChange}
              className={fieldClass}
            >
              <option value="daily">Dagelijks</option>
              <option value="weekly">Wekelijks</option>
              <option value="monthly">Maandelijks</option>
            </select>

            {formData.dcaFrequency === "weekly" && (
              <select
                name="dcaDay"
                value={formData.dcaDay}
                onChange={handleChange}
                className={fieldClass}
              >
                <option value="monday">Maandag</option>
                <option value="tuesday">Dinsdag</option>
                <option value="wednesday">Woensdag</option>
                <option value="thursday">Donderdag</option>
                <option value="friday">Vrijdag</option>
                <option value="saturday">Zaterdag</option>
                <option value="sunday">Zondag</option>
              </select>
            )}

            {formData.dcaFrequency === "monthly" && (
              <input
                type="number"
                name="dcaMonthDay"
                min={1}
                max={28}
                value={formData.dcaMonthDay}
                onChange={handleChange}
                className={fieldClass}
                placeholder="Dag van de maand (1-28)"
              />
            )}
          </div>
        )}

        {/* Trade info */}
        {isTrade && (
          <div className="text-sm text-[var(--text-soft)]">
            Dit is een trade setup. Entry, targets en stop-loss beheer je later in de gekoppelde strategie.
          </div>
        )}
      </div>

      {/* SCORES */}
      <div className={sectionClass}>
        {sectionTitle(
          <BarChart3 size={18} />,
          "Wanneer mag deze setup actief zijn?"
        )}

        <div className="flex items-start gap-2 text-sm text-[var(--text-soft)]">
          <Info size={16} className="mt-0.5" />
          <p>
            Deze score-ranges bepalen <strong>in welke marktfase</strong> deze setup geldig is.
          </p>
        </div>

        {scoreBlock("Macro", macroScore, setMacroScore, "Macro-omgeving")}
        {scoreBlock("Technical", technicalScore, setTechnicalScore, "Trend")}
        {scoreBlock(
          "Market / Sentiment",
          marketScore,
          setMarketScore,
          "Sentiment"
        )}
      </div>

      {/* SAVE */}
      <button
        id="setup-edit-submit"
        type="submit"
        disabled={loading}
        className="w-full flex items-center justify-center gap-3 bg-blue-600 hover:bg-blue-700 text-white px-8 py-5 rounded-2xl text-[12px] font-black uppercase tracking-widest transition-all active:scale-95 border-b-4 border-blue-800 active:border-b-0"
      >
        <Save size={20} />
        {loading ? "BEZIG…" : "Blueprint Opslaan"}
      </button>
    </form>
  );
}
