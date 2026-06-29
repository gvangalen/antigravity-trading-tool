import React, { useEffect, useMemo } from "react";
import { useTranslation } from "@/app/providers/I18nProvider";
import Slider from "rc-slider";
import "rc-slider/assets/index.css";
import { 
  LineChart, 
  TrendingUp, 
  TrendingDown, 
  Plus, 
  Trash2, 
  Layers, 
  Info,
} from "lucide-react";

const DEFAULT_POINTS = [
  { x: 20, y: 1.5 },
  { x: 40, y: 1.2 },
  { x: 60, y: 1.0 },
  { x: 80, y: 0.5 },
];

export default function CurveEditor({
  value,
  onChange,
  xLabel,
  yLabel,
  disabled = false,
}) {
  const { t } = useTranslation();
  const copy = t?.legacyComponents?.curveEditor || {};
  const resolvedXLabel = xLabel || copy.defaultXLabel;
  const resolvedYLabel = yLabel || copy.defaultYLabel;

  const curve = useMemo(() => {
    if (!value || !Array.isArray(value.points)) {
      return {
        input: "market_score",
        points: DEFAULT_POINTS,
      };
    }
    return value;
  }, [value]);

  const points = curve.points;

  const updatePoint = (index, patch) => {
    const next = points.map((p, i) =>
      i === index ? { ...p, ...patch } : p
    );
    onChange({ ...curve, points: next });
  };

  const addPoint = () => {
    const lastX = points[points.length - 1]?.x ?? 60;
    const nextX = Math.min(lastX + 10, 100);
    onChange({
      ...curve,
      points: [...points, { x: nextX, y: 1.0 }],
    });
  };

  const removePoint = (index) => {
    if (points.length <= 2) return;
    onChange({
      ...curve,
      points: points.filter((_, i) => i !== index),
    });
  };

  useEffect(() => {
    const sorted = [...points].sort((a, b) => a.x - b.x);
    if (JSON.stringify(sorted) !== JSON.stringify(points)) {
      onChange({ ...curve, points: sorted });
    }
  }, [points]);

  return (
    <div className="bg-card border border-slate-200 rounded-3xl overflow-hidden shadow-xl">
      {/* 🛠️ CONSOLE HEADER */}
      <div className="bg-[var(--color-border-subtle)] px-6 py-4 border-b border-slate-200 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="bg-[var(--primary)] text-white p-1.5 rounded-lg shadow-sm shadow-[var(--primary-soft)]">
             <Layers size={16} />
          </div>
          <div>
            <h4 className="text-xs font-black text-foreground uppercase tracking-widest">
              {copy.title}
            </h4>
            <p className="text-[10px] text-secondary font-bold uppercase tracking-tight">
              {copy.subtitlePrefix} {resolvedXLabel}
            </p>
          </div>
        </div>

        {!disabled && (
          <button
            type="button"
            onClick={addPoint}
            className="flex items-center gap-1.5 text-[10px] font-black uppercase tracking-widest bg-card text-muted px-3 py-1.5 rounded-xl border border-slate-200 hover:border-[var(--primary)] hover:text-[var(--primary)] transition-all shadow-sm"
          >
            <Plus size={12} /> {copy.addPoint}
          </button>
        )}
      </div>

      <div className="p-6 space-y-8">
        {/* AXIS LABELS */}
        <div className="grid grid-cols-[80px_1fr_100px_40px] gap-6 text-[9px] font-black text-secondary uppercase tracking-[0.2em] px-2">
          <div>{resolvedXLabel}</div>
          <div className="text-center">{copy.sizingWeights}</div>
          <div className="text-right">{resolvedYLabel}</div>
          <div />
        </div>

        {/* POINTS LIST */}
        <div className="space-y-6">
          {points.map((p, i) => (
            <div
              key={i}
              className={`grid grid-cols-[80px_1fr_100px_40px] gap-6 items-center ${
                disabled ? "opacity-40" : ""
              }`}
            >
              {/* SCORE INPUT */}
              <div className="relative group">
                <input
                  type="number"
                  min={0}
                  max={100}
                  disabled={disabled}
                  value={p.x}
                  onChange={(e) => updatePoint(i, { x: Number(e.target.value) })}
                  className="w-full bg-[var(--color-border-subtle)] border border-slate-200 text-foreground font-black text-center py-2.5 rounded-xl focus:ring-2 focus:ring-[var(--primary)] focus:bg-white transition-all outline-none"
                />
                <div className="absolute -top-1.5 -left-1.5 bg-[var(--color-border-subtle)] text-[8px] font-black text-muted px-1.5 py-0.5 rounded border border-slate-200 uppercase">Score</div>
              </div>

              {/* SLIDER CONSOLE */}
              <div className="px-4">
                <Slider
                  min={0.1}
                  max={3}
                  step={0.05}
                  disabled={disabled}
                  value={p.y}
                  onChange={(v) => updatePoint(i, { y: v })}
                  trackStyle={{ backgroundColor: 'var(--primary)', height: 6 }}
                  handleStyle={{
                    borderColor: 'var(--primary)',
                    height: 20,
                    width: 20,
                    backgroundColor: '#fff',
                    opacity: 1,
                    boxShadow: '0 2px 4px rgba(0,0,0,0.1)'
                  }}
                  railStyle={{ backgroundColor: '#f1f5f9', height: 6 }}
                />
              </div>

              {/* MULTIPLIER BADGE */}
              <div className="relative">
                <input
                  type="number"
                  min={0.1}
                  step={0.05}
                  disabled={disabled}
                  value={p.y}
                  onChange={(e) => updatePoint(i, { y: Number(e.target.value) })}
                  className="w-full bg-[var(--color-border-subtle)] border border-slate-200 text-[var(--primary-dark)] font-black text-right py-2.5 px-3 rounded-xl focus:ring-2 focus:ring-[var(--primary)] focus:bg-white transition-all outline-none"
                />
                <div className="absolute -top-1.5 -right-1.5 bg-[var(--primary-soft)] text-[8px] font-black text-[var(--primary-dark)] px-1.5 py-0.5 rounded border border-[var(--primary-soft)] uppercase tracking-tighter">{copy.sizeMultiplier}</div>
              </div>

              {/* DELETE */}
              {!disabled && (
                <button
                  type="button"
                  onClick={() => removePoint(i)}
                  className="w-10 h-10 flex items-center justify-center text-slate-300 hover:text-red-500 hover:bg-red-50 rounded-xl transition-all"
                >
                  <Trash2 size={16} />
                </button>
              )}
            </div>
          ))}
        </div>

        {/* 📉 VISUALIZED SUMMARY */}
        <div className="bg-slate-50/50 rounded-2xl p-5 border border-slate-100">
           <div className="flex items-center gap-2 mb-4 text-slate-400">
              <Layers size={14} />
              <span className="text-[10px] font-black uppercase tracking-widest leading-none">{copy.mappingPreview}</span>
           </div>
           
           <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              {points.map((p, i) => (
                <div key={i} className="bg-card p-3 rounded-xl border border-slate-200 group hover:border-[var(--primary)] transition-all shadow-sm">
                   <div className="text-[9px] font-black text-secondary uppercase mb-1">Score {p.x}</div>
                   <div className="flex items-end gap-1.5">
                      <div className="text-xl font-black text-foreground leading-none">{(p.y).toFixed(2)}x</div>
                      <div className={`text-[9px] font-bold pb-0.5 ${p.y >= 1 ? "text-green-500" : "text-red-400"}`}>
                         {p.y > 1.2 ? copy.labels.aggressive : p.y > 0.8 ? copy.labels.standard : copy.labels.defensive}
                      </div>
                   </div>
                </div>
              ))}
           </div>
        </div>
      </div>

      {disabled && (
        <div className="bg-[var(--color-border-subtle)] px-6 py-3 flex items-center gap-2 border-t border-slate-100">
           <Info size={12} className="text-secondary" />
           <span className="text-[10px] font-bold text-secondary uppercase tracking-tight italic">
             {copy.fixedAmountNotice}
           </span>
        </div>
      )}
    </div>
  );
}
