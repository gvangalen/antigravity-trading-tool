"use client";

import { useTranslation } from "@/app/providers/I18nProvider";
import { formatDateTime } from "@/lib/i18n";
import { parseUtcMoment, reportMarketLabel, scoreSourceSnapshot } from "@/lib/report/reportSourceSnapshot.mjs";

export default function ReportCategoryEvidence({ report, category, isPrint = false }) {
  const { t, locale } = useTranslation();
  const copy = t.pages.report;
  const assets = scoreSourceSnapshot(report)?.assets || [];
  if (!assets.length) return null;

  const label = { market: copy.hudMarket, macro: copy.hudMacro, technical: copy.hudTechnical }[category];
  const formatMoment = (value) => {
    const date = parseUtcMoment(value);
    return date ? `${formatDateTime(date, locale, {
      day: "2-digit", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit", timeZone: "UTC",
    })} UTC` : copy.hudSourceUnknown;
  };
  const sourceLabel = (name) => copy.hudIndicatorLabels?.[String(name).toLowerCase().replaceAll(/[-\s]+/g, "_")] || name;

  return (
    <details open={isPrint} className="mt-6 rounded-xl border border-slate-200 bg-slate-50/70 p-4 text-sm text-slate-600">
      <summary className="cursor-pointer font-semibold text-blue-700">{copy.hudSourceDetails} · {label}</summary>
      <div className="mt-3 space-y-2">
        {assets.map((asset, index) => {
          const score = asset.reported_scores?.[`${category}_score`];
          const status = asset.component_source_status?.[`${category}_score`];
          const kind = status === "fresh" ? "fresh"
            : ["stale_source", "stale_report"].includes(status) ? "stale"
            : ["missing_score", "missing_indicator_reading"].includes(status) ? "missing"
            : status === "score_rebuild_pending" ? "pending" : "unknown";
          const sources = asset.component_source_observed_at?.[category] || {};
          const configured = asset.configured_indicators?.[category];
          return (
            <div key={`${reportMarketLabel(asset)}-${index}`} className="border-t border-slate-200 pt-2 first:border-0 first:pt-0">
              <strong>{reportMarketLabel(asset)}</strong> · {label}: {score ?? "—"} ({copy.hudSourceStatus?.[kind] || copy.hudSourceStatus?.unknown})
              {Array.isArray(configured) && configured.length > 0 && (
                <div>{configured.map(sourceLabel).join(", ")}</div>
              )}
              {Object.entries(sources).map(([name, moment]) => (
                <div key={name}>{sourceLabel(name)} · {formatMoment(moment)}</div>
              ))}
            </div>
          );
        })}
      </div>
    </details>
  );
}
