"use client";

import CardWrapper from "@/components/ui/CardWrapper";
import CardLoader from "@/components/ui/CardLoader";
import { Clock } from "lucide-react";

export default function BotHistoryTable({
  history = [],
  loading = false,
}) {
  return (
    <CardWrapper
      title="Bot History"
      icon={<Clock className="icon icon-muted" />}
    >
      {/* ===================== */}
      {/* LOADING STATE */}
      {/* ===================== */}
      {loading && (
        <CardLoader text="Geschiedenis laden…" />
      )}

      {/* ===================== */}
      {/* EMPTY STATE */}
      {/* ===================== */}
      {!loading && history.length === 0 && (
        <p className="text-sm text-[var(--text-muted)]">
          Er zijn nog geen bot-acties uitgevoerd.
        </p>
      )}

      {/* ===================== */}
      {/* TABLE */}
      {/* ===================== */}
      {!loading && history.length > 0 && (
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-[var(--text-muted)] border-b border-[var(--border)]">
              <th className="py-2">Date</th>
              <th>Action</th>
              <th>Qty</th>
              <th>Price</th>
              <th>Amount</th>
              <th>Confidence</th>
              <th>Status</th>
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
                  ? `${Number(h.qty).toFixed(6)} ${h.symbol || "BTC"}`
                  : "—";

              const price =
                h.price != null
                  ? `€${h.price}`
                  : "—";

              const amount =
                h.amount_eur != null
                  ? `€${h.amount_eur}`
                  : h.amount != null
                  ? `€${h.amount}`
                  : "€0";

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
                        ? new Date(h.created_at).toLocaleString("nl-NL")
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
