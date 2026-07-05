"use client";

import { useState, useEffect, useMemo, useCallback } from "react";
import { useTranslation } from "@/app/providers/I18nProvider";
import { RefreshCw, Info, Activity, Terminal, Layers, Box, Sliders } from "lucide-react";
import { useModal } from "@/components/modal/ModalProvider";
import ScoreModeBadge from "./ScoreModeBadge";

/**
 * IndicatorScoreEditor — Grip Theme PRO 3.0 (theme-driven)
 *
 * ✅ 5 vaste buckets (0–20, 20–40, 40–60, 60–80, 80–100)
 * ✅ Standard / Contrarian / Custom: visueel IDENTIEK (zelfde tabel)
 * ✅ Standard/Contrarian tonen score als badge (geen input)
 * ✅ Contrarian is exact inverse van Standard template (100 - score)
 * ✅ Custom = DB-rules (editable score + weight + save)
 * ✅ Units (%, USD, index) zichtbaar in de UI header (0–100, unit)
 *
 * UX regels:
 * - Tabel ranges blijven ALTIJD 0–100 (design), ook al clampen we scores naar 10–100
 * - Custom save doet GEEN dubbele writes: Editor stuurt 1 payload naar Panel
 *
 * Props:
 *  indicator: string
 *  category: "macro" | "market" | "technical"
 *  rules: array
 *  scoreMode: "standard" | "contrarian" | "custom"
 *  weight: number
 *  loading: boolean
 *  onSave(settings) -> Promise|void                // Standard/Contrarian only
 *  onSaveCustom(payload, weight) -> Promise|void   // Custom only (Panel regelt alles)
 */

const FIXED_BUCKETS = [
  { min: 0, max: 20 },
  { min: 20, max: 40 },
  { min: 40, max: 60 },
  { min: 60, max: 80 },
  { min: 80, max: 100 },
];

// Stable template scores for Standard mode
const STANDARD_TEMPLATE_SCORES = [10, 25, 50, 75, 100];

// Keep consistent with backend normalize_indicator_name
const NAME_ALIASES = {
  fear_and_greed_index: "fear_greed_index",
  fear_greed: "fear_greed_index",
  sandp500: "sp500",
  "s&p500": "sp500",
  "s&p_500": "sp500",
  sp_500: "sp500",
};

// Meta map for unit display (extend when needed)
const INDICATOR_META = {
  volume: { unit: "%", labelKey: "volumeRelative" },
  market_volume: { unit: "%", labelKey: "volumeRelative" },
  volume_change: { unit: "%", labelKey: "volumeChange" },
  change_24h: { unit: "%", labelKey: "change24h" },
  change_7d: { unit: "%", labelKey: "change7d" },
  fear_greed_index: { unit: "index", labelKey: "fearGreed" },
  sp500: { unit: "index", labelKey: "sp500" },
  dxy: { unit: "index", labelKey: "dxy" },
  price: { unit: "USD", labelKey: "price" },
};

function normalizeIndicatorName(name) {
  const normalized = String(name || "")
    .toLowerCase()
    .replace(/&/g, "and")
    .replace(/s&p/g, "sp")
    .replace(/\s+/g, "_")
    .replace(/-+/g, "_")
    .trim();

  return NAME_ALIASES[normalized] || normalized;
}

// Business clamp (engine) ≠ UI range (design)
const clampScore = (v) => {
  const n = Number(v);
  if (!Number.isFinite(n)) return 50;
  if (n < 10) return 10;
  if (n > 100) return 100;
  return n;
};

const getTrend = (score) => {
  const s = Number(score);
  if (s <= 20) return "veryLow";
  if (s <= 40) return "low";
  if (s <= 60) return "neutral";
  if (s <= 80) return "active";
  return "high";
};

/**
 * NOTE:
 * Deze classes moeten in global CSS staan (geen local <style>).
 * Als je ze niet hebt: voeg .score-badge + varianten toe aan global stylesheet.
 */
function getScoreBadgeClass(score) {
  const s = Number(score);
  if (s <= 20) return "score-badge score-badge-sell";
  if (s <= 60) return "score-badge score-badge-neutral";
  if (s <= 80) return "score-badge score-badge-buy";
  return "score-badge score-badge-strong-buy";
}

// Bucketize DB rules to fixed 5 buckets (keeps UI stable even if DB partial)
function bucketizeRules(rules = []) {
  const arr = Array.isArray(rules) ? rules : [];

  return FIXED_BUCKETS.map((b) => {
    const mid = (b.min + b.max) / 2;

    const match =
      arr.find((r) => Number(r?.range_min) <= mid && mid <= Number(r?.range_max)) ||
      arr.find((r) => Number(r?.range_min) === b.min && Number(r?.range_max) === b.max);

    const s = clampScore(match?.score ?? 50);

    return {
      range_min: b.min,
      range_max: b.max,
      score: s,
      trend: getTrend(s),
    };
  });
}

export default function IndicatorScoreEditor({
  indicator,
  category,
  rules = [],
  scoreMode = "standard",
  weight = 1,
  loading = false,
  onSave,
  onSaveCustom,
}) {
  const { showSnackbar } = useModal();
  const { t } = useTranslation();
  const copy = t?.legacyComponents?.indicatorScore || {};

  const normalizedIndicator = useMemo(
    () => normalizeIndicatorName(indicator),
    [indicator]
  );

  const meta = INDICATOR_META[normalizedIndicator] || null;
  const metaLabel = meta?.labelKey ? copy.indicatorLabels?.[meta.labelKey] : null;

  const [mode, setMode] = useState(scoreMode);
  const [localWeight, setLocalWeight] = useState(weight);

  // Custom-only state
  const [customRules, setCustomRules] = useState(() => bucketizeRules(rules));
  const [savingCustom, setSavingCustom] = useState(false);

  /* --------------------------------------------------
     Sync: when backend props change
  -------------------------------------------------- */
  useEffect(() => {
    setMode(scoreMode || "standard");
    setLocalWeight(typeof weight === "number" ? weight : 1);
    setCustomRules(bucketizeRules(rules));
  }, [normalizedIndicator, scoreMode, rules, weight]);

  /* --------------------------------------------------
     Auto-save for STANDARD & CONTRARIAN only
     (Mode changes are saved; custom is saved via button)
  -------------------------------------------------- */
    useEffect(() => {
    if (loading) return;
    if (!normalizedIndicator || !category) return;
    if (mode === "custom") return;

    onSave?.({
      indicator: normalizedIndicator,
      category,
      score_mode: mode,
      weight: localWeight,
      __silent: true, // ✅ voorkomt snackbar bij navigatie
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mode, loading, normalizedIndicator, category, localWeight]);

  /* --------------------------------------------------
     Template rows (standard baseline)
  -------------------------------------------------- */
  const templateRows = useMemo(() => {
    return FIXED_BUCKETS.map((b, idx) => {
      const s = clampScore(STANDARD_TEMPLATE_SCORES[idx]);
      return {
        range_min: b.min,
        range_max: b.max,
        score: s,
        trend: getTrend(s),
      };
    });
  }, []);

  /* --------------------------------------------------
     Display transform for contrarian
  -------------------------------------------------- */
  const displayScore = useCallback(
    (baseScore) => {
      const base = clampScore(baseScore);
      if (mode === "contrarian") return clampScore(100 - base);
      return base;
    },
    [mode]
  );

  const isCustom = mode === "custom";
  const rows = isCustom ? customRules : templateRows;

  /* --------------------------------------------------
     Custom edit: score only (ranges locked)
  -------------------------------------------------- */
  const updateCustomScore = useCallback((idx, value) => {
    setCustomRules((prev) => {
      const next = Array.isArray(prev) ? [...prev] : bucketizeRules([]);
      const b = FIXED_BUCKETS[idx];
      const s = clampScore(value);

      next[idx] = {
        range_min: b.min,
        range_max: b.max,
        score: s,
        trend: getTrend(s),
      };

      return next;
    });
  }, []);

  /* --------------------------------------------------
     Save custom (ONE path)
     ✅ Editor does NOT call onSave here to avoid double writes.
     ✅ Panel handles mode+weight+rules saving + success snackbar.
  -------------------------------------------------- */
  const saveCustom = useCallback(async () => {
    if (!normalizedIndicator || !category) return;
    if (savingCustom) return;

    setSavingCustom(true);

    try {
      const payload = FIXED_BUCKETS.map((b, i) => {
        const s = clampScore(customRules?.[i]?.score ?? 50);
        return {
          indicator: normalizedIndicator,
          category,
          range_min: b.min,
          range_max: b.max,
          score: s,
          trend: getTrend(s),
        };
      });

      await onSaveCustom?.(payload, localWeight);
      // ✅ Success snackbar hoort in Panel (single source)
      // Hier alleen errors tonen om dubbel snackbar te voorkomen.
    } catch (e) {
      console.error("Save custom rules failed", e);
      showSnackbar(copy.customSaveFailed, "danger");
    } finally {
      setSavingCustom(false);
    }
  }, [
    normalizedIndicator,
    category,
    savingCustom,
    customRules,
    localWeight,
    onSaveCustom,
    showSnackbar,
  ]);

  if (loading) {
    return <div className="p-6 text-sm text-[var(--text-light)]">{t?.common?.loading}</div>;
  }

  const valueLabel = meta?.unit
    ? `${copy.normalizedValueWithUnitPrefix} ${meta.unit})`
    : copy.normalizedValue;

  const modes = [
    { key: "standard", label: copy.modes?.standard },
    { key: "contrarian", label: copy.modes?.contrarian },
    { key: "custom", label: copy.modes?.custom },
  ];

  return (
    <div className="bg-card border border-slate-200 rounded-[2.5rem] p-8 shadow-sm space-y-10">
      <div className="flex items-start justify-between pb-6 border-b border-slate-100">
        <div className="flex items-center gap-4">
          <div className="w-12 h-12 rounded-2xl bg-[var(--color-border-subtle)] border border-slate-100 flex items-center justify-center text-slate-400">
            <Terminal size={24} />
          </div>
          <div>
            <div className="flex items-center gap-2 mb-1">
              <h3 className="text-xl font-black text-foreground uppercase tracking-tight">{copy.signalGenerationLogic}</h3>
              <ScoreModeBadge mode={mode} />
            </div>
            <p className="text-[10px] font-black text-secondary uppercase tracking-widest leading-none">
              {copy.indicatorLabel}: <span className="text-dim">{metaLabel || normalizedIndicator || "—"}</span>
            </p>
          </div>
        </div>

        <div className="flex flex-col items-end gap-1.5 p-3 rounded-2xl bg-[var(--color-border-subtle)] border border-slate-100">
          <div className="flex items-center gap-3">
             <div className="text-[10px] font-black text-secondary uppercase tracking-widest">{copy.weightLabel}</div>
             <div className="text-sm font-black text-foreground tabular-nums bg-card px-3 py-0.5 rounded-lg border border-slate-200 shadow-sm">
                0{Number(localWeight).toFixed(1)}
             </div>
          </div>
          <div className="text-[9px] font-black text-slate-300 uppercase tracking-widest">
             {copy.impact}: {isCustom ? copy.impactModes?.customOverride : copy.impactModes?.systemDefault}
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-10">
        <div className="space-y-8">
           <div className="space-y-3">
              <div className="text-[10px] font-black text-secondary uppercase tracking-[0.2em] pl-1">{copy.engineModeSelector}</div>
              <div className="flex bg-[var(--color-border-subtle)] p-1.5 rounded-2xl border border-slate-100 w-fit">
                {modes.map((m) => (
                  <button
                    key={m.key}
                    onClick={() => setMode(m.key)}
                    className={`px-6 py-2.5 rounded-xl text-[10px] font-black uppercase tracking-widest transition-all ${
                      mode === m.key
                        ? "bg-card text-foreground shadow-md border border-slate-100"
                        : "text-secondary hover:text-slate-600"
                    }`}
                  >
                    {m.label}
                  </button>
                ))}
              </div>
           </div>

           <div className="p-5 rounded-[2rem] bg-slate-50/50 border border-slate-100 min-h-[80px] flex items-center">
              {mode === "standard" && (
                <div className="flex items-center gap-4">
                   <div className="w-8 h-8 rounded-lg bg-blue-50 text-blue-500 flex items-center justify-center">
                      <Box size={16} />
                   </div>
                   <p className="text-[10px] font-black text-muted uppercase tracking-widest leading-relaxed">
                      {copy.engineStatus.standard}
                   </p>
                </div>
              )}
              {mode === "contrarian" && (
                <div className="flex items-center gap-4">
                   <div className="w-8 h-8 rounded-lg bg-orange-50 text-orange-500 flex items-center justify-center">
                      <RefreshCw size={16} />
                   </div>
                   <p className="text-[10px] font-black text-orange-600/70 uppercase tracking-widest leading-relaxed">
                      {copy.engineStatus.contrarian}
                   </p>
                </div>
              )}
              {mode === "custom" && (
                <div className="flex items-center gap-4">
                   <div className="w-8 h-8 rounded-lg bg-purple-50 text-purple-500 flex items-center justify-center">
                      <Layers size={16} />
                   </div>
                   <p className="text-[10px] font-black text-purple-600/70 uppercase tracking-widest leading-relaxed">
                      {copy.engineStatus.custom}
                   </p>
                </div>
              )}
           </div>

           {isCustom && (
              <div className="space-y-4 pt-4">
                   <div className="flex items-center justify-between">
                   <div className="text-[10px] font-black text-foreground uppercase tracking-widest flex items-center gap-2">
                      <Sliders size={14} className="text-secondary" /> {copy.parameterTuning}
                   </div>
                   <div className="text-[10px] font-black text-secondary uppercase tracking-widest">{copy.weightValue}: 0{Number(localWeight).toFixed(1)}</div>
                </div>
                <div className="p-6 bg-[var(--color-border-subtle)] border border-slate-100 rounded-[2rem]">
                   <input
                     type="range"
                     min="0"
                     max="3"
                     step="0.1"
                     value={localWeight}
                     onChange={(e) => setLocalWeight(Number(e.target.value))}
                     className="w-full h-1.5 bg-slate-200 rounded-full appearance-none cursor-pointer accent-blue-600"
                   />
                   <div className="flex justify-between mt-3 text-[9px] font-black text-slate-300 uppercase tracking-widest font-mono">
                      <span>{copy.lowImpact}</span>
                      <span>{copy.mid}</span>
                      <span>{copy.highImpact}</span>
                   </div>
                </div>
              </div>
           )}

           {isCustom && (
              <button
                onClick={saveCustom}
                disabled={savingCustom}
                className="w-full flex items-center justify-center gap-3 bg-[var(--primary)] text-white py-4 rounded-[1.5rem] text-xs font-black uppercase tracking-[0.2em] hover:scale-[1.02] active:scale-[0.98] transition-all shadow-xl shadow-blue-500/20"
              >
                {savingCustom ? copy.deployingLogic : copy.commitCustomManifest}
              </button>
           )}
        </div>

        <div className="space-y-4">
           <div className="text-[10px] font-black text-secondary uppercase tracking-[0.2em] pl-1">{copy.logicManifestTelemetry}</div>
           <div className="bg-slate-50/50 border border-slate-100 rounded-[2.5rem] overflow-hidden">
             <div className="grid grid-cols-12 gap-2 px-8 py-4 bg-[var(--color-border-subtle)] border-b border-slate-100">
               <div className="col-span-5 text-[10px] font-black text-secondary uppercase tracking-widest">{copy.inputRange}</div>
               <div className="col-span-4 text-[10px] font-black text-secondary uppercase tracking-widest text-center">{copy.outputSignal}</div>
               <div className="col-span-3 text-[10px] font-black text-secondary uppercase tracking-widest text-right">{t?.common?.trend}</div>
             </div>

             <div className="px-6 py-6 space-y-6">
                {FIXED_BUCKETS.map((b, idx) => {
                  const rawScore = rows?.[idx]?.score ?? 50;
                  const shownScore = displayScore(rawScore);

                  const signal = (() => {
                     if (shownScore >= 70) return { bg: "bg-green-500", color: "text-green-600" };
                     if (shownScore <= 30) return { bg: "bg-red-500", color: "text-red-600" };
                     return { bg: "bg-slate-400", color: "text-secondary" };
                  })();

                  return (
                    <div key={idx} className="grid grid-cols-12 gap-4 items-center group">
                      <div className="col-span-5">
                         <div className="text-xs font-black text-foreground font-mono tracking-tighter opacity-80">
                            [{String(b.min).padStart(2, '0')}—{String(b.max).padStart(3, '0')}] {meta?.unit || copy.unit}
                         </div>
                      </div>

                      <div className="col-span-4">
                        {isCustom ? (
                          <div className="relative group/input">
                             <input
                               type="number"
                               min="10"
                               max="100"
                               step="5"
                               value={rawScore}
                               onChange={(e) => updateCustomScore(idx, e.target.value)}
                               className="w-full bg-card border border-slate-200 rounded-xl px-2 py-1.5 text-center text-xs font-black text-foreground font-mono focus:ring-2 focus:ring-blue-500 outline-none shadow-sm transition-all"
                             />
                             <div className="mt-1.5 h-1.5 w-full bg-[var(--color-border-subtle)] rounded-full overflow-hidden border border-slate-200">
                                <div className={`h-full rounded-full transition-all duration-500 ${signal.bg}`} style={{ width: `${shownScore}%` }} />
                             </div>
                          </div>
                        ) : (
                          <div className="space-y-1.5">
                             <div className="h-4 w-full bg-[var(--color-border-subtle)] rounded-full p-0.5 border border-slate-200 overflow-hidden">
                                <div className={`h-full rounded-full transition-all duration-700 ${signal.bg}`} style={{ width: `${shownScore}%` }} />
                             </div>
                             <div className={`text-[8px] font-black uppercase tracking-widest text-center ${signal.color}`}>
                                {copy.value}: {shownScore}
                             </div>
                          </div>
                        )}
                      </div>

                      <div className="col-span-3 text-right">
                         <div className={`text-[10px] font-black uppercase tracking-widest ${signal.color}`}>
                            {copy.trends?.[getTrend(shownScore)]}
                         </div>
                      </div>
                    </div>
                  );
                })}
             </div>

             {!isCustom && (
               <div className="px-8 py-4 bg-[var(--color-border-subtle)] border-t border-slate-100 text-[9px] font-black text-slate-300 uppercase tracking-widest text-center italic">
                  {copy.readonlyMode}
               </div>
             )}
           </div>
        </div>
      </div>
    </div>
  );
}
