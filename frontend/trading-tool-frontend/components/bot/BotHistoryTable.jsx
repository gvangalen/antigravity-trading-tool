"use client";

import CardWrapper from "@/components/ui/CardWrapper";
import CardLoader from "@/components/ui/CardLoader";
import { Clock } from "lucide-react";
import { useTranslation } from "@/app/providers/I18nProvider";
import { formatCurrency, formatDateTime, formatNumber } from "@/lib/i18n";

export default function BotHistoryTable({
  history = [],
  loading = false,
}) {
  const { t, locale } = useTranslation();
  const copy = t?.botPage?.history || {};
  const focusCopy = t?.botPage?.focus || {};
  const riskCodes = focusCopy.riskCodes || {};
  const confidenceLabels = t?.botPage?.agentCard?.confidenceLabels || {};

  return (
    <CardWrapper
      title={copy.title}
      icon={<Clock className="icon icon-muted" />}
    >
      {/* ===================== */}
      {/* LOADING STATE */}
      {/* ===================== */}
      {loading && (
        <CardLoader text={copy.loading} />
      )}

      {/* ===================== */}
      {/* EMPTY STATE */}
      {/* ===================== */}
      {!loading && history.length === 0 && (
        <p className="text-sm text-[var(--text-muted)]">
          {copy.empty}
        </p>
      )}

      {/* ===================== */}
      {/* TABLE */}
      {/* ===================== */}
      {!loading && history.length > 0 && (
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-[var(--text-muted)] border-b border-[var(--border)]">
              <th className="py-2">{copy.date}</th>
              <th>{copy.action}</th>
              <th>{copy.quantity}</th>
              <th>{copy.price}</th>
              <th>{copy.amount}</th>
              <th>{copy.confidence}</th>
              <th>{copy.status}</th>
              <th>{copy.reason}</th>
            </tr>
          </thead>

          <tbody>
            {history.map((h, i) => {
              /* =====================
                 Status styling
              ===================== */
              const guardrailResult = h.guardrails_result || {};
              const blocked = Boolean(guardrailResult.blocked_by || h.execution_failure);
              const status = blocked ? "blocked" : h.status || (h.executed ? "executed" : "planned");
              let statusClass = "text-[var(--text-muted)]";

              if (status === "executed") statusClass = "icon-success";
              else if (status === "blocked" || status === "failed" || status === "failed_execution") statusClass = "icon-danger";
              else if (status === "skipped") statusClass = "icon-warning";

              /* =====================
                 Helpers
              ===================== */
              const qty =
                h.qty != null
                  ? `${formatNumber(Number(h.qty), locale, {
                      minimumFractionDigits: 0,
                      maximumFractionDigits: 6,
                    })} ${h.symbol || "BTC"}`
                  : "—";

              const price =
                h.price != null
                  ? formatCurrency(Number(h.price), locale)
                  : "—";

              const amount =
                h.amount_eur != null
                  ? formatCurrency(Number(h.amount_eur), locale)
                  : h.amount != null
                  ? formatCurrency(Number(h.amount), locale)
                  : formatCurrency(0, locale);
              const guardrailExplanations = Array.isArray(guardrailResult.explanations)
                ? guardrailResult.explanations : [];
              const reason = h.execution_failure || (guardrailExplanations.length > 0
                ? guardrailExplanations.map((item) => {
                    const label = riskCodes[item.code] || item.message;
                    const hasAmounts = Number.isFinite(Number(item.from_amount_eur)) && Number.isFinite(Number(item.to_amount_eur));
                    return hasAmounts ? `${label}: ${formatCurrency(Number(item.from_amount_eur), locale)} → ${formatCurrency(Number(item.to_amount_eur), locale)}` : label;
                  }).join(" · ")
                : riskCodes[guardrailResult.blocked_by] || (h.is_trade ? copy.tradeExecutedReason : null)
                  || h.reasons?.find((item) => typeof item === "string" && item.trim() && !["{}", "[]", "null"].includes(item.trim()))
                  || guardrailResult.reason
                  || (status === "executed" ? copy.executedDecisionReason : copy.reasonNotRecorded));
              const dateValue = h.created_at || h.date;
              const dateLabel = dateValue
                ? formatDateTime(dateValue, locale, { day: "2-digit", month: "short", year: "numeric" })
                : "—";
              const action = String(h.action || h.side || "").toLowerCase();
              const actionLabel = h.is_trade
                ? (action === "buy" ? focusCopy.buy : action === "sell" ? focusCopy.sell : null) || h.action || h.side || "—"
                : focusCopy.actions?.[action] || h.action || h.side || "—";
              const statusLabel = focusCopy.states?.[status] || copy.statuses?.[status] || status;
              const confidence = String(h.confidence || "").toLowerCase();

              return (
                <tr
                  key={h.id || i}
                  className="
                    border-b border-[var(--border)] last:border-0
                    hover:bg-[var(--surface-2)]
                    transition
                  "
                >
                  {/* DATE */}
                  <td className="py-2">
                    {dateLabel}
                  </td>

                  {/* ACTION */}
                  <td className="font-medium capitalize">
                    {actionLabel}
                  </td>

                  {/* QTY */}
                  <td>
                    {qty}
                  </td>

                  {/* PRICE */}
                  <td>
                    {price}
                  </td>

                  {/* AMOUNT */}
                  <td>
                    {amount}
                  </td>

                  {/* CONFIDENCE */}
                  <td>
                    {confidenceLabels[confidence] || h.confidence || "—"}
                  </td>

                  {/* STATUS */}
                  <td className={`font-medium capitalize ${statusClass}`}>
                    {statusLabel}
                  </td>
                  <td className="max-w-xs py-2 text-xs text-[var(--text-muted)]">{reason}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      )}
    </CardWrapper>
  );
}
