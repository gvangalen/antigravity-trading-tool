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
            </tr>
          </thead>

          <tbody>
            {history.map((h, i) => {
              /* =====================
                 Status styling
              ===================== */
              let status = h.status || (h.executed ? "executed" : "planned");
              let statusClass = "text-[var(--text-muted)]";

              if (status === "executed") statusClass = "icon-success";
              else if (status === "failed") statusClass = "icon-danger";
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
                    {h.date ||
                      (h.created_at
                        ? formatDateTime(h.created_at, locale)
                        : "—")}
                  </td>

                  {/* ACTION */}
                  <td className="font-medium capitalize">
                    {h.action || h.side || "—"}
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
                    {h.confidence || "—"}
                  </td>

                  {/* STATUS */}
                  <td className={`font-medium capitalize ${statusClass}`}>
                    {status}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      )}
    </CardWrapper>
  );
}
