"use client";

import { Calendar, Globe, Zap, Activity, Target, Info } from "lucide-react";
import { useAuth } from "@/components/auth/AuthProvider";
import { HUDSkeleton } from "@/components/dashboard/DashboardSkeleton";
import { useTranslation } from "@/app/providers/I18nProvider";
import { formatDateTime } from "@/lib/i18n";
import { parseUtcMoment, scoreSourceSnapshot } from "@/lib/report/reportSourceSnapshot.mjs";

export default function ReportTerminalHUD({ report, type = "daily", loading = false }) {
  const { user } = useAuth();
  const { t, locale } = useTranslation();
  const reportT = t.pages.report;

  if (loading) {
    return <HUDSkeleton />;
  }

  if (!report) return null;

  const {
    report_date,
    macro_score,
    technical_score,
    market_score,
    setup_score,
    generated_at
  } = report;
  const sourceSnapshot = scoreSourceSnapshot(report);
  const sourceAssets = Array.isArray(sourceSnapshot?.assets) ? sourceSnapshot.assets : [];
  const formatUtc = (value) => {
    const moment = parseUtcMoment(value);
    return moment ? `${formatDateTime(moment, locale, {
      day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit',
      timeZone: 'UTC',
    })} UTC` : null;
  };
  const categoryLabels = {
    market: reportT.hudMarket,
    macro: reportT.hudMacro,
    technical: reportT.hudTechnical,
  };
  const indicatorLabels = reportT.hudIndicatorLabels || {};
  const indicatorLabel = (name) => indicatorLabels[String(name).toLowerCase().replaceAll(/[-\s]+/g, '_')] || name;
  const sourceStatusLabel = (status) => {
    const kind = status === 'fresh' ? 'fresh'
      : ['stale_source', 'stale_report'].includes(status) ? 'stale'
      : ['missing_score', 'missing_indicator_reading'].includes(status) ? 'missing'
      : status === 'score_rebuild_pending' ? 'pending'
      : 'unknown';
    return reportT.hudSourceStatus?.[kind] || reportT.hudSourceStatus?.unknown;
  };

  const ScoreItem = ({ label, value, icon: Icon, colorClass }) => (
    <div className="flex flex-col items-center justify-center p-4 rounded-xl bg-card border border-blue-600/5 shadow-sm min-w-[120px] transition-all hover:scale-105">
      <div className={`p-1.5 rounded-lg mb-2 ${colorClass} bg-opacity-10 flex items-center justify-center`}>
         <Icon size={14} className={colorClass.replace('bg-', 'text-')} />
      </div>
      <div className="text-[9px] font-black text-secondary uppercase tracking-widest mb-1">{label}</div>
      <div className={`text-2xl font-black tracking-tighter tabular-nums ${
        value == null ? "text-secondary" : value >= 70 ? "text-green-600" : value <= 30 ? "text-red-500" : "text-foreground"
      }`}>
        {value ?? "—"}
      </div>
    </div>
  );

  return (
    <div className="card p-10 mb-12 animate-fade-in relative overflow-hidden">
      <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-10 relative z-10">
        
        <div className="border-l-4 border-blue-600 pl-8">
           <div className="text-[10px] font-black text-blue-600 uppercase tracking-[0.3em] mb-2 flex items-center gap-2">
              <span className="w-2 h-2 rounded-full bg-blue-600 animate-pulse" />
              {reportT.hudEyebrow}
           </div>
           <h1 className="text-4xl font-black text-foreground tracking-tighter uppercase leading-none">
             {reportT.types[type] || reportT.hudDefaultTitle}
           </h1>
           <div className="flex items-center gap-3 mt-4 text-slate-400">
             <Calendar size={14} className="text-blue-600/40" />
             <span className="text-sm font-bold tracking-tight uppercase">
               {reportT.hudPeriod}: <span className="text-foreground">{report_date || "—"}</span>
             </span>
           </div>
        </div>

        <div className="bg-blue-50/20 border-2 border-blue-600/5 rounded-[2rem] p-6 flex flex-wrap items-center gap-4">
          <ScoreItem label={reportT.hudMacro} value={macro_score} icon={Globe} colorClass="bg-blue-600" />
          <ScoreItem label={reportT.hudTechnical} value={technical_score} icon={Zap} colorClass="bg-amber-500" />
          <ScoreItem label={reportT.hudMarket} value={market_score} icon={Activity} colorClass="bg-indigo-600" />
          <ScoreItem label={reportT.hudSetup} value={setup_score} icon={Target} colorClass="bg-emerald-600" />
        </div>

      </div>

      <div className="relative z-10 mt-7 rounded-xl border border-slate-200 bg-slate-50/70 p-4 text-sm text-slate-600 dark:border-slate-800 dark:bg-slate-900/40 dark:text-slate-300">
        <p className="font-semibold text-slate-800 dark:text-slate-100">
          {sourceSnapshot ? reportT.hudSnapshotTitle : reportT.hudGeneratedTitle}: {formatUtc(sourceSnapshot?.observed_at) || formatUtc(generated_at) || reportT.hudSourceUnknown}
        </p>
        <p className="mt-1">{sourceSnapshot ? reportT.hudSnapshotExplanation : reportT.hudLegacyExplanation}</p>
        {sourceAssets.length > 0 ? (
          <details className="mt-3">
            <summary className="cursor-pointer font-semibold text-blue-700 dark:text-blue-300">{reportT.hudSourceDetails}</summary>
            <div className="mt-3 space-y-3">
              {sourceAssets.map((asset, index) => (
                <div key={`${asset.symbol || 'asset'}-${index}`} className="rounded-lg border border-slate-200 bg-white p-3 dark:border-slate-700 dark:bg-slate-950/40">
                  <p className="font-semibold">{asset.symbol || '—'} · {reportT.hudScoreDate}: {asset.score_report_date || reportT.hudSourceUnknown}</p>
                  {Object.entries(categoryLabels).map(([category, label]) => {
                    const sources = asset.component_source_observed_at?.[category] || {};
                    const score = asset.reported_scores?.[`${category}_score`];
                    const status = asset.component_source_status?.[`${category}_score`];
                    return (
                      <p key={category} className="mt-1">
                        {label}: {score ?? '—'} ({sourceStatusLabel(status)}) · {Object.keys(sources).length ? Object.entries(sources).map(([name, moment]) => `${indicatorLabel(name)}: ${formatUtc(moment) || reportT.hudSourceUnknown}`).join('; ') : reportT.hudSourceUnknown}
                      </p>
                    );
                  })}
                </div>
              ))}
              <p className="text-xs">{reportT.hudSetupSource}</p>
            </div>
          </details>
        ) : sourceSnapshot ? (
          <p className="mt-2 text-xs">{reportT.hudNoAssets}</p>
        ) : (
          <p className="mt-2 text-xs">{reportT.hudLegacySources}</p>
        )}
      </div>

      <footer className="mt-10 pt-6 border-t-2 border-slate-50 flex items-center justify-between text-[9px] font-black uppercase tracking-widest text-slate-400">
         <div className="flex items-center gap-2">
            <Info size={12} className="text-blue-600" />
            {reportT.hudValidated}
         </div>
         <div className="flex items-center gap-4">
            <span>{reportT.hudUser}: {user?.name || reportT.hudSystem}</span>
            <span className="w-1 h-1 rounded-full bg-slate-300" />
            <span>{reportT.hudGeneratedTitle}: {formatUtc(generated_at) || "—"}</span>
         </div>
      </footer>
    </div>
  );
}
