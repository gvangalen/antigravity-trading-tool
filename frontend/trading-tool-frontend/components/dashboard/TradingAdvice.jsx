'use client';

import { Info, Rocket } from 'lucide-react';
import { useTranslation } from '@/app/providers/I18nProvider';

export default function TradingAdvice() {
  const { t } = useTranslation();
  const copy = t?.dashboard?.tradingAdvice || {};

  return (
    <div className="rounded-2xl border-2 border-slate-100 dark:border-slate-800 bg-white dark:bg-slate-950/40 p-6 shadow-sm transition-all overflow-hidden relative">
      <div className="flex items-center gap-2 mb-4">
        <Rocket size={18} className="text-blue-600" />
        <h3 className="text-sm font-black uppercase tracking-widest text-slate-900 dark:text-slate-100">
          {copy.title}
        </h3>
      </div>

      <div className="rounded-2xl border border-blue-100 bg-blue-50/70 dark:border-blue-900/40 dark:bg-blue-950/20 p-4">
        <div className="flex items-start gap-3">
          <Info size={16} className="mt-0.5 text-blue-600 dark:text-blue-400" />
          <div className="space-y-2">
            <p className="text-sm font-bold text-slate-900 dark:text-slate-100">
              {copy.emptyTitle}
            </p>
            <p className="text-xs font-medium leading-relaxed text-slate-600 dark:text-slate-300">
              {copy.emptyBody}
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
