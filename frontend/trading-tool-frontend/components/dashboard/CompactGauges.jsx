"use client";

import { useScoresData } from "@/hooks/useScoresData";
import { Globe2, LineChart, DollarSign, Settings2, Sliders, Save, X, Sparkles } from "lucide-react";
import { useTranslation } from "@/app/providers/I18nProvider";
import { GaugeSkeleton } from "./DashboardSkeleton";
import { useState, useEffect } from "react";

const getStructureLabel = (domain, score, labels) => {
  if (domain === 'macro') {
    if (score >= 75) return labels.expansion;
    if (score >= 50) return labels.recovery;
    if (score >= 35) return labels.stagflationRisk;
    return labels.contraction;
  }
  if (domain === 'technical') {
    if (score >= 75) return labels.continuation;
    if (score >= 55) return labels.recovery;
    if (score >= 40) return labels.consolidation;
    return labels.contraction;
  }
  if (domain === 'market') {
    if (score >= 75) return labels.highConviction;
    if (score >= 50) return labels.capitalInflow;
    if (score >= 35) return labels.liquidityDivergence;
    return labels.riskAversion;
  }
  if (domain === 'setup') {
    if (score >= 75) return labels.premiumAlignment;
    if (score >= 50) return labels.favorableRiskReward;
    if (score >= 35) return labels.suboptimal;
    return labels.drawdownRisk;
  }
  return labels.stableStructure;
};

/**
 * 📏 CompactGauges — Minimalist Status Bar (V2.1)
 * Replaces large Gauge cards with a slim horizontal strip.
 */
export default function CompactGauges({ symbol = "BTC", snapshot = null }) {
  const { t } = useTranslation();
  const fallbackSnapshot = useScoresData(symbol, { includeHistory: false });
  const { macro, technical, market, setup, master, loading, saveWeights } = snapshot || fallbackSnapshot;
  const [isEditing, setIsEditing] = useState(false);
  const [localWeights, setLocalWeights] = useState({
     macro: 0.25,
     market: 0.25,
     technical: 0.25,
     setup: 0.25
  });

  useEffect(() => {
    if (master.weights) {
      setLocalWeights(master.weights);
    }
  }, [master.weights]);

  const handleWeightChange = (key, val) => {
     const newValue = parseFloat(val);
     const oldValue = localWeights[key];
     const delta = newValue - oldValue;
     
     const keys = Object.keys(localWeights);
     const otherKeys = keys.filter(k => k !== key);
     
     if (otherKeys.length === 0) return;

     const newWeights = { ...localWeights, [key]: newValue };
     
     const currentOthersSum = otherKeys.reduce((sum, k) => sum + localWeights[k], 0);
     
     if (currentOthersSum > 0) {
        otherKeys.forEach(k => {
           const share = localWeights[k] / currentOthersSum;
           let adjusted = localWeights[k] - (delta * share);
           newWeights[k] = Math.max(0, Math.min(1, adjusted));
        });
     } else {
        otherKeys.forEach(k => {
           newWeights[k] = Math.max(0, (1 - newValue) / otherKeys.length);
        });
     }

     const finalSum = Object.values(newWeights).reduce((a, b) => a + b, 0);
     if (finalSum > 0) {
        const factor = 1.0 / finalSum;
        Object.keys(newWeights).forEach(k => {
           newWeights[k] = newWeights[k] * factor;
        });
     }

     setLocalWeights(newWeights);
  };

  const onSave = async () => {
     await saveWeights(localWeights);
     setIsEditing(false);
  };

  const structureLabels = t.dashboard.gauges.structure;

  const items = [
    { id: 'macro', title: t.dashboard.gauges.macro, icon: <Globe2 size={14} />, score: macro.score, weight: localWeights.macro, structure: getStructureLabel('macro', macro.score, structureLabels) },
    { id: 'technical', title: t.dashboard.gauges.technical, icon: <LineChart size={14} />, score: technical.score, weight: localWeights.technical, structure: getStructureLabel('technical', technical.score, structureLabels) },
    { id: 'market', title: t.dashboard.gauges.market, icon: <DollarSign size={14} />, score: market.score, weight: localWeights.market, structure: getStructureLabel('market', market.score, structureLabels) },
    { id: 'setup', title: t.dashboard.gauges.setup, icon: <Settings2 size={14} />, score: setup.score, weight: localWeights.setup, structure: getStructureLabel('setup', setup.score, structureLabels) },
  ];

  if (loading && !isEditing) {
     return (
       <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 w-full">
         {[1, 2, 3, 4].map(i => (
           <GaugeSkeleton key={i} />
         ))}
       </div>
     );
  }

  const totalWeight = Object.values(localWeights).reduce((a, b) => a + b, 0);
  const isBalanced = Math.abs(totalWeight - 1.0) < 0.01 || Math.abs(totalWeight - 100) < 1;

  return (
    <div className="space-y-4 w-full">
      <div className="flex items-center justify-between px-2">
         <div className="flex items-center gap-2">
            <div className="w-1 h-4 bg-blue-600 rounded-full" />
            <h3 className="text-[11px] font-black uppercase tracking-[0.2em] text-secondary">{t.dashboard.system_status}</h3>
         </div>
         <button 
            onClick={() => setIsEditing(!isEditing)}
            className={`flex items-center gap-2 px-3 py-1.5 rounded-lg text-[10px] font-bold uppercase tracking-wider transition-all ${isEditing ? 'bg-rose-500 text-white' : 'bg-slate-100 dark:bg-slate-900 text-secondary hover:bg-slate-200'}`}
         >
            {isEditing ? <X size={12} /> : <Sliders size={12} />}
            {isEditing ? t.dashboard.gauges.cancelTune : t.dashboard.gauges.tune}
         </button>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 w-full">
        {items.map((item, idx) => {
          const score = Math.round(item.score || 0);
          
          let colorClass = "text-secondary dark:text-slate-500";
          let bgClass = "bg-[var(--color-border-subtle)] dark:bg-slate-900";
          let borderClass = "border-slate-100 dark:border-slate-800";

          if (score >= 75) {
            colorClass = "text-emerald-600 dark:text-emerald-400";
            bgClass = "bg-emerald-50 dark:bg-emerald-950/30";
            borderClass = "border-emerald-100 dark:border-emerald-900/50";
          } else if (score >= 50) {
            colorClass = "text-blue-600 dark:text-blue-400";
            bgClass = "bg-blue-50 dark:bg-blue-950/30";
            borderClass = "border-blue-100 dark:border-blue-900/50";
          } else if (score < 40) {
            colorClass = "text-rose-500 dark:text-rose-400";
            bgClass = "bg-rose-50 dark:bg-rose-950/30";
            borderClass = "border-rose-100 dark:border-rose-900/50";
          }

          return (
            <div key={idx} className="space-y-2">
               <div className={`group relative overflow-visible px-3 sm:px-4 py-3 rounded-xl border ${borderClass} ${bgClass} shadow-sm transition-all hover:shadow-md ${isEditing ? 'ring-2 ring-blue-500/20 border-blue-500/40' : ''}`}>
                  <button 
                    onClick={(e) => {
                      e.stopPropagation();
                      if (typeof window !== "undefined") {
                        window.dispatchEvent(new CustomEvent('finn-action-trigger', {
                          detail: { metric: item.id === 'macro' ? 'structural_cycle' : item.id === 'setup' ? 'setup_quality' : 'transition_risk', symbol, timeframe: '1W' }
                        }));
                      }
                    }}
                    aria-label={t.dashboard.gauges.askFinn.replace("{title}", item.title)}
                    className="absolute -top-5 right-2 z-10 hidden lg:inline-flex items-center justify-center h-10 w-10 rounded-xl bg-blue-50 dark:bg-blue-900/60 text-blue-600 dark:text-blue-300 border border-blue-200 dark:border-blue-800 shadow-sm transition-all opacity-0 translate-y-1 group-hover:opacity-100 group-hover:translate-y-0 focus-visible:opacity-100 focus-visible:translate-y-0 hover:scale-105 active:scale-95"
                  >
                    <Sparkles size={16} />
                  </button>

                  <div className="grid grid-cols-[auto_minmax(0,1fr)_auto] items-center gap-2 sm:gap-3 w-full">
                    <div className={`shrink-0 p-2 rounded-lg bg-card dark:bg-slate-800 shadow-sm ${colorClass} border border-slate-50 dark:border-slate-700`}>
                       {item.icon}
                    </div>

                    <div className="flex flex-col min-w-0 text-left">
                      <span className="text-[10px] sm:text-[11px] font-black uppercase tracking-wider text-secondary dark:text-slate-500 leading-none">
                         {item.title}
                      </span>
                      <span className="mt-1 text-[9px] sm:text-[10px] font-bold tracking-[0.01em] text-[var(--primary)] dark:text-blue-400 leading-tight whitespace-nowrap">
                         {item.structure}
                      </span>
                    </div>

                    <div className="flex items-center justify-end shrink-0 min-w-[3.25rem] sm:min-w-[3.5rem]">
                    <span className={`text-xs sm:text-sm font-black font-mono ${colorClass}`}>
                       {score}%
                    </span>
                    </div>
                  </div>
               </div>

               {isEditing && (
                  <div className="px-2 space-y-1 animate-in slide-in-from-top-2 duration-300">
                     <div className="flex justify-between text-[9px] font-bold text-secondary uppercase tracking-widest px-1">
                        <span>{t.dashboard.gauges.weight}</span>
                        <span>{Math.round(item.weight * 100)}%</span>
                     </div>
                     <input 
                        type="range" 
                        min="0" 
                        max="1" 
                        step="0.05" 
                        value={item.weight}
                        onChange={(e) => handleWeightChange(item.id, e.target.value)}
                        className="w-full h-1.5 bg-slate-200 dark:bg-slate-800 rounded-lg appearance-none cursor-pointer accent-blue-600"
                     />
                  </div>
               )}

               {!isEditing && item.weight !== undefined && (
                  <div className="px-3 flex items-center gap-2">
                     <div className="h-0.5 flex-1 bg-slate-100 dark:bg-slate-800/50 rounded-full overflow-hidden">
                        <div 
                           className="h-full bg-blue-500/40" 
                           style={{ width: `${item.weight * 100}%` }}
                        />
                     </div>
                     <span className="text-[8px] font-black text-secondary/40 uppercase tracking-tighter whitespace-nowrap">
                        W: {Math.round(item.weight * 100)}%
                     </span>
                  </div>
               )}
            </div>
          );
        })}
      </div>


      {isEditing && (
         <div className="flex items-center justify-between bg-blue-50 dark:bg-blue-900/20 border border-blue-100 dark:border-blue-800/50 p-4 rounded-2xl animate-in fade-in zoom-in duration-300">
                  <div className="flex items-center gap-3">
               <div className={`w-10 h-10 rounded-full flex items-center justify-center border-2 ${isBalanced ? 'border-emerald-500 text-emerald-500 bg-emerald-500/10' : 'border-amber-500 text-amber-500 bg-amber-500/10'}`}>
                  <span className="text-xs font-black">{Math.round(totalWeight * 100)}%</span>
               </div>
               <div>
                  <div className="text-[10px] font-black uppercase tracking-widest text-secondary">{t.dashboard.gauges.configurationStatus}</div>
                  <div className="text-[11px] font-bold text-foreground">
                     {isBalanced ? t.dashboard.gauges.balanced : t.dashboard.gauges.unbalanced}
                  </div>
               </div>
            </div>
            <button 
               onClick={onSave}
               disabled={loading}
               className="flex items-center gap-2 px-6 py-2.5 bg-blue-600 hover:bg-blue-700 text-white rounded-xl text-[11px] font-black uppercase tracking-[0.2em] shadow-lg shadow-blue-500/20 active:scale-95 transition-all disabled:opacity-50"
            >
               <Save size={14} />
               {t.dashboard.gauges.applyChanges}
            </button>
         </div>
      )}
    </div>
  );
}
