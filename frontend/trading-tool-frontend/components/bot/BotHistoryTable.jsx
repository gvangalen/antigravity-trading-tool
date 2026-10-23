"use client";

import CardLoader from "@/components/ui/CardLoader";
import { useTranslation } from "@/app/providers/I18nProvider";
import { formatCurrency, formatDateTime, formatNumber } from "@/lib/i18n";

export default function BotHistoryTable({
  history = [],
  loading = false,
  emptyMessage,
}) {
  const { t, locale } = useTranslation();
  const copy = t?.botPage?.history || {};
  const focusCopy = t?.botPage?.focus || {};
  const riskCodes = focusCopy.riskCodes || {};
  const localizeReason = (value) => value === "Scheduled DCA amount selected from the confirmed plan"
    ? focusCopy.scheduledDcaReason : value;
  const confidenceLabels = t?.botPage?.agentCard?.confidenceLabels || {};

  return (
    <>
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
          {emptyMessage || copy.empty}
        </p>
      )}

      {/* ===================== */}
      {/* TABLE */}
      {/* ===================== */}
      {!loading && history.length > 0 && (
        <table className="w-full min-w-[760px] text-sm">
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
              const safety = h.safety_check || {};
              const blocked = safety.state === "blocked" || Boolean(guardrailResult.blocked_by);
              const status = h.is_trade ? h.status || "executed" : h.execution_failure ? "failed_execution" : blocked ? "blocked" : ["reduced", "no_proposal", "waiting_market"].includes(safety.state) ? safety.state : h.status || "planned";
              let statusClass = "text-[var(--text-muted)]";

              if (["executed", "filled"].includes(status)) statusClass = "icon-success";
              else if (status === "blocked" || status === "failed" || status === "failed_execution") statusClass = "icon-danger";
              else if (["skipped", "partial", "reduced"].includes(status)) statusClass = "icon-warning";

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

              const hasProposal = Number(safety.proposed_amount_eur ?? guardrailResult.original_amount_eur ?? h.amount_eur) > 0;
              const amount = h.is_trade
                ? formatCurrency(Number(h.amount_eur ?? h.amount ?? 0), locale)
                : !hasProposal ? "—"
                  : ["blocked", "reduced"].includes(safety.state)
                    ? `${formatCurrency(Number(safety.proposed_amount_eur), locale)} → ${formatCurrency(Number(safety.checked_amount_eur ?? safety.allowed_amount_eur ?? 0), locale)}`
                    : formatCurrency(Number(safety.allowed_amount_eur ?? h.amount_eur ?? 0), locale);
              const guardrailExplanations = Array.isArray(safety.explanations) ? safety.explanations
                : Array.isArray(guardrailResult.explanations) ? guardrailResult.explanations : [];
              const reason = h.execution_failure || (guardrailExplanations.length > 0
                ? guardrailExplanations.map((item) => {
                    const label = riskCodes[item.code] || item.message;
                    const hasAmounts = Number.isFinite(Number(item.from_amount_eur)) && Number.isFinite(Number(item.to_amount_eur));
                    return hasAmounts ? `${label}: ${formatCurrency(Number(item.from_amount_eur), locale)} → ${formatCurrency(Number(item.to_amount_eur), locale)}` : label;
                  }).join(" · ")
                : riskCodes[safety.reason_code] || riskCodes[guardrailResult.blocked_by] || (h.is_trade ? copy.tradeExecutedReason : null)
                  || localizeReason(h.reasons?.find((item) => typeof item === "string" && item.trim() && !["{}", "[]", "null"].includes(item.trim())))
                  || guardrailResult.reason
                  || (status === "executed" ? copy.executedDecisionReason : copy.reasonNotRecorded));
              const dateValue = h.is_trade ? h.created_at : safety.checked_at || h.decision_ts || h.created_at || h.date;
              const dateLabel = dateValue
                ? formatDateTime(dateValue, locale, { day: "2-digit", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" })
                : "—";
              const action = String(h.action || h.side || "").toLowerCase();
              const actionLabel = h.is_trade
                ? (action === "buy" ? focusCopy.buy : action === "sell" ? focusCopy.sell : null) || h.action || h.side || "—"
                : focusCopy.actions?.[action] || h.action || h.side || "—";
              const statusLabel = !h.is_trade && status === "executed" ? copy.decisionExecuted
                : focusCopy.tradeStatuses?.[status] || focusCopy.states?.[status] || copy.statuses?.[status] || status;
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
                    {h.decision_basis === "saved_setup_score_band"
                      ? copy.scoreBandBasis
                      : confidenceLabels[confidence] || h.confidence || "—"}
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
    </>
  );
}
