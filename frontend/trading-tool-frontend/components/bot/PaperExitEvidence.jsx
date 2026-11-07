"use client";

import { useTranslation } from "@/app/providers/I18nProvider";
import { formatDateTime, formatNumber } from "@/lib/i18n";

export default function PaperExitEvidence({ evidence, showMissing = false }) {
  const { t, locale } = useTranslation();
  const copy = t?.botPage?.history?.exitEvidence || {};
  if (!evidence || !Object.keys(evidence).length) {
    return showMissing ? <p className="mt-2 text-sm text-[var(--text-muted)]">{copy.title}: {copy.notRecorded}</p> : null;
  }
  const number = (value) => value == null ? "—" : formatNumber(Number(value), locale, { maximumFractionDigits: 6 });
  const time = (value) => value ? formatDateTime(value, locale, {
    day: "2-digit", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit", timeZoneName: "short",
  }) : copy.notRecorded;
  const sourceCurrency = evidence.execution_source_price_currency || evidence.source_price_currency || "";
  return <details className="mt-2 text-xs">
    <summary className="cursor-pointer font-semibold text-blue-700">{copy.title}</summary>
    <dl className="mt-2 space-y-1 text-[var(--text-muted)]">
      <div>{copy.trigger}: {copy.triggers?.[evidence.trigger] || evidence.trigger || "—"}</div>
      <div>{copy.savedStop}: {number(evidence.saved_stop_loss)} {evidence.source_price_currency || ""}</div>
      <div>{copy.decisionQuote}: {number(evidence.source_price)} {evidence.source_price_currency || ""} · {time(evidence.source_price_at)}</div>
      <div>{copy.executionQuote}: {evidence.execution_source_price == null ? copy.notRecorded : `${number(evidence.execution_source_price)} ${sourceCurrency} · ${time(evidence.execution_source_price_at)}`}</div>
      <div>{copy.fx}: {evidence.execution_fx_eur_per_unit == null ? copy.notRecorded : `${number(evidence.execution_fx_eur_per_unit)} · ${time(evidence.execution_fx_observed_at)}`}</div>
    </dl>
  </details>;
}
