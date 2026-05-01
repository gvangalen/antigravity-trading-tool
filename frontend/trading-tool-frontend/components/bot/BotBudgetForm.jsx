"use client";

import { useEffect, useState } from "react";
import { Layers } from "lucide-react";
import { TradingSlider } from "@/components/ui/Slider";

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

export default function BotBudgetForm({ initialBudget, onChange }) {

  const [form, setForm] = useState({
    total_eur: 0,
    daily_limit_eur: 0,
    max_order_eur: 0,
    max_asset_exposure_pct: 100,
  });

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

  return (
    <div className="space-y-8 p-1">
      <div className="p-4 rounded-xl bg-blue-50 border border-blue-100 flex items-start gap-4 shadow-sm">
        <div className="p-2 rounded-lg bg-card text-blue-500 shadow-sm shrink-0">
          <Layers size={20} strokeWidth={2.5} />
        </div>
        <p className="text-xs font-bold text-blue-700/80 leading-relaxed italic">
          This budget configuration acts as a hard safety ceiling. The bot will automatically scale or block trades that exceed these limits.
        </p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        {/* Total budget */}
        <div className="space-y-2">
          <label className="text-[10px] font-black text-secondary uppercase tracking-widest pl-1">
            Global Limit (€)
          </label>
          <input
            type="number"
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
            Daily Cap (€)
          </label>
          <input
            type="number"
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
            Order MAX (€)
          </label>
          <input
            type="number"
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
          <label className="text-[10px] font-black text-secondary uppercase tracking-[0.2em]">Asset Exposure Sensor</label>
          <div className="text-xs font-black text-[var(--primary)] font-mono bg-blue-50 px-2 py-0.5 rounded-md">
            {form.max_asset_exposure_pct}% MAX
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
          Maximum allocation of total bot capital per single asset node.
        </div>
      </div>
    </div>
  );
}
