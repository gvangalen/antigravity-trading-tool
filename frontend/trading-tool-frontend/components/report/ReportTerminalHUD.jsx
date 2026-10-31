"use client";

import { Calendar, Info } from "lucide-react";
import { useAuth } from "@/components/auth/AuthProvider";
import { HUDSkeleton } from "@/components/dashboard/DashboardSkeleton";
import { useTranslation } from "@/app/providers/I18nProvider";
import { formatDateTime } from "@/lib/i18n";
import { parseUtcMoment, scoreSourceSnapshot } from "@/lib/report/reportSourceSnapshot.mjs";
import { reportV2PeriodLabel } from "@/lib/report/reportV2Presentation.mjs";

export default function ReportTerminalHUD({ report, type = "daily", loading = false }) {
  const { user } = useAuth();
  const { t, locale } = useTranslation();
  const reportT = t.pages.report;

  if (loading) {
    return <HUDSkeleton />;
  }

  if (!report) return null;

  const { report_date, generated_at } = report;
  const sourceSnapshot = scoreSourceSnapshot(report);
  const formatUtc = (value) => {
    const moment = parseUtcMoment(value);
    return moment ? `${formatDateTime(moment, locale, {
      day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit', timeZone: 'UTC',
    })} UTC` : null;
  };

  return (
    <div className="card relative mb-12 min-w-0 overflow-hidden p-4 animate-fade-in sm:p-10">
      <div className="relative z-10 flex min-w-0 flex-col justify-between gap-6 lg:flex-row lg:items-center lg:gap-10">
        
        <div className="min-w-0 border-l-4 border-blue-600 pl-4 sm:pl-8">
           <div className="text-[10px] font-black text-blue-600 uppercase tracking-[0.3em] mb-2 flex items-center gap-2">
              <span className="w-2 h-2 rounded-full bg-blue-600 animate-pulse" />
              {reportT.hudEyebrow}
           </div>
           <h1 className="break-words text-2xl font-black uppercase leading-tight tracking-tighter text-foreground sm:text-4xl sm:leading-none">
             {reportT.types[type] || reportT.hudDefaultTitle}
           </h1>
           <div className="flex items-center gap-3 mt-4 text-slate-400">
             <Calendar size={14} className="text-blue-600/40" />
             <span className="text-sm font-bold tracking-tight uppercase">
               {reportT.hudPeriod}: <span className="text-foreground">{reportV2PeriodLabel(report, locale)}</span>
             </span>
           </div>
        </div>


      </div>

      <p className="mt-5 text-sm text-slate-600 dark:text-slate-300">
        {sourceSnapshot ? reportT.hudSnapshotTitle : reportT.hudGeneratedTitle}: {formatUtc(sourceSnapshot?.observed_at) || formatUtc(generated_at) || reportT.hudSourceUnknown}. {sourceSnapshot ? reportT.hudSnapshotExplanation : reportT.hudLegacyExplanation}
      </p>

      <footer className="mt-10 flex min-w-0 flex-col items-start gap-3 border-t-2 border-slate-50 pt-6 text-[9px] font-black uppercase tracking-widest text-slate-400 sm:flex-row sm:items-center sm:justify-between">
         <div className="flex min-w-0 items-start gap-2 break-words">
            <Info size={12} className="text-blue-600" />
            {reportT.hudValidated}
         </div>
         <div className="flex min-w-0 flex-wrap items-center gap-2 break-words sm:gap-4">
            <span className="min-w-0 break-words">{reportT.hudUser}: {user?.name || reportT.hudSystem}</span>
            <span className="hidden h-1 w-1 shrink-0 rounded-full bg-slate-300 sm:block" />
            <span className="min-w-0 break-words">{reportT.hudGeneratedTitle}: {formatUtc(generated_at) || "—"}</span>
         </div>
      </footer>
    </div>
  );
}
