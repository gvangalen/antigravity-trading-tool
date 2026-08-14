"use client";

import { useMemo, useState, useEffect } from "react";
import {
  ResponsiveContainer,
  AreaChart,
  Area,
  XAxis,
  YAxis,
  Tooltip,
} from "recharts";

import usePortfolioBalance from "@/hooks/usePortfolioBalance";
import { useTranslation } from "@/app/providers/I18nProvider";
import { formatCurrency, formatDate, formatDateTime, formatNumber, getIntlLocale } from "@/lib/i18n";

/* =====================================================
   RANGE CONFIG
===================================================== */
const RANGES = [
  { key: "1D", label: "1D", bucket: "1h", limit: 24 },
  { key: "1W", label: "1W", bucket: "1h", limit: 24 * 7 },
  { key: "1M", label: "1M", bucket: "1d", limit: 30 },
  { key: "1Y", label: "1Y", bucket: "1d", limit: 365 },
  { key: "ALL", label: "ALL", bucket: "1d", limit: 2000 },
];

/* =====================================================
   MODES
===================================================== */
const MODES = [
  { key: "equity", labelKey: "equity" },
  { key: "cash", labelKey: "cash" },
  { key: "btc_value", labelKey: "btcValue" },
  { key: "btc_qty", labelKey: "btcQty" },
  { key: "invested", labelKey: "invested" },
  { key: "unrealized_pnl", labelKey: "unrealizedPnl" },
];

/* =====================================================
   FORMATTERS
===================================================== */
const fmtBtc = (n) => `${Number(n || 0).toFixed(4)} BTC`;
const fmtPct = (n) => `${Number(n || 0).toFixed(1)}%`;

function shortDate(ts, rangeKey, locale) {
  const d = new Date(ts);

  if (rangeKey === "1D") {
    return formatDateTime(d, locale, {
      hour: "2-digit",
      minute: "2-digit",
    });
  }

  return formatDate(d, locale, {
    day: "2-digit",
    month: "short",
  });
}

/* =====================================================
   DELTA CALC
===================================================== */
function calcDelta(series, mode) {
  if (!Array.isArray(series) || series.length < 2) {
    return { last: 0, delta: 0, pct: null };
  }

  const first = Number(series[0]?.[mode] ?? 0);
  const last = Number(series[series.length - 1]?.[mode] ?? 0);

  const delta = last - first;

  const pct =
    first > 0 && Math.abs(first) > 1
      ? (delta / first) * 100
      : null;

  return { last, delta, pct };
}

/* =====================================================
   COMPONENT
===================================================== */

export default function PortfolioBalanceCard({
  defaultRange = "1W",
  title = null,
  is_live = null,
  fallbackSnapshot = null,
}) {
  const { t, locale } = useTranslation();
  const copy = t?.botPage?.portfolioBalance || {};
  const [range, setRange] = useState(defaultRange);
  const [mode, setMode] = useState("equity");

  const rangeConfig =
    RANGES.find((r) => r.key === range) || RANGES[1];

  const { data, loading, reload } = usePortfolioBalance({
    is_live,
    bucket: rangeConfig.bucket,
    limit: rangeConfig.limit,
  });

  const hasMeaningfulHistory = useMemo(() => {
    if (!Array.isArray(data) || data.length === 0) return false;
    return data.some((point) =>
      ["equity", "cash", "btc_value", "btc_qty", "invested", "unrealized_pnl"].some(
        (key) => Math.abs(Number(point?.[key] ?? 0)) > 0
      )
    );
  }, [data]);

  /* =====================================================
     LIVE PORTFOLIO REFRESH
  ===================================================== */

  useEffect(() => {
    const handler = () => reload();

    window.addEventListener("portfolio:updated", handler);

    return () =>
      window.removeEventListener(
        "portfolio:updated",
        handler
      );
  }, [reload]);

  /* =====================================================
     SERIES
  ===================================================== */

  const series = useMemo(() => {
    if (hasMeaningfulHistory) return data;

    const now = new Date();
    const points = [];
    const fallbackPoint = {
      equity: Number(fallbackSnapshot?.equity ?? 0),
      cash: Number(fallbackSnapshot?.cash ?? 0),
      btc_value: Number(fallbackSnapshot?.btc_value ?? 0),
      btc_qty: Number(fallbackSnapshot?.btc_qty ?? 0),
      invested: Number(fallbackSnapshot?.invested ?? 0),
      unrealized_pnl: Number(fallbackSnapshot?.unrealized_pnl ?? 0),
    };

    for (let i = rangeConfig.limit - 1; i >= 0; i--) {
      const d = new Date(now);

      if (rangeConfig.bucket === "1h") {
        d.setHours(now.getHours() - i);
      } else {
        d.setDate(now.getDate() - i);
      }

      points.push({
        ts: d.toISOString(),
        ...fallbackPoint,
      });
    }

    return points;
  }, [data, fallbackSnapshot, hasMeaningfulHistory, rangeConfig.bucket, rangeConfig.limit]);

  const { last, delta, pct } = useMemo(
    () => calcDelta(series, mode),
    [series, mode]
  );

  const isDown = delta < 0;

  /* =====================================================
     CHART DATA
  ===================================================== */

  const chartData = useMemo(() => {
    return series.map((p) => ({
      ts: p.ts,
      value: Number(p?.[mode] ?? 0),
      label: shortDate(p.ts, range, locale),
    }));
  }, [series, range, mode, locale]);

  /* =====================================================
     Y DOMAIN
  ===================================================== */

  const yDomain = useMemo(() => {
    if (!chartData.length) return ["auto", "auto"];

    const values = chartData.map((d) => d.value);

    const min = Math.min(...values);
    const max = Math.max(...values);

    if (min === max) {
      const padding =
        min === 0
          ? 100
          : Math.max(Math.abs(min) * 0.05, 1);

      return [min - padding, max + padding];
    }

    const span = max - min;
    const padding = Math.max(span * 0.1, 5);

    return [min - padding, max + padding];
  }, [chartData]);

  /* =====================================================
     COLOR LOGIC
  ===================================================== */

  const strokeColor =
    mode === "unrealized_pnl"
      ? isDown
        ? "#ef4444"
        : "#22c55e"
      : "var(--primary)";

  const gradientId = `balanceFill-${mode}`;

  const formatValue = (v) =>
    mode === "btc_qty"
      ? fmtBtc(v)
      : formatCurrency(Number(v || 0), locale, "EUR", { maximumFractionDigits: 0 });

  /* =====================================================
     UI
  ===================================================== */

  return (
    <div className="bg-card border border-[var(--color-border)] rounded-[2rem] p-8 shadow-sm w-full min-w-0 font-sans transition-colors duration-300">
      <div className="flex items-start justify-between gap-6 flex-wrap pb-6 border-b border-slate-100">

        <div className="space-y-1">
          <div className="text-[10px] font-black text-secondary uppercase tracking-widest mb-1">
            {title || copy.title}
          </div>

          <div className="text-4xl font-black tracking-tighter text-foreground font-mono">
            {formatValue(last)}
          </div>

          <div
            className={`flex items-center gap-2 text-xs font-black uppercase tracking-tight ${
              isDown
                ? "text-red-500"
                : "text-green-500"
            }`}
          >
            <div className={`px-2 py-0.5 rounded-lg border ${isDown ? 'bg-red-50 border-red-100' : 'bg-green-50 border-green-100'}`}>
              {isDown ? "↘" : "↗"}{" "}
              {pct !== null ? fmtPct(pct) : ""}
            </div>
            <span className="font-mono tabular-nums opacity-80">({formatValue(delta)})</span>
          </div>
        </div>

        {/* 🛠 INSTRUMENT CONTROLS */}
        <div className="flex flex-col gap-3 items-end">
          <div className="flex gap-1 p-1 bg-[var(--color-border-subtle)] rounded-xl border border-[var(--color-border)]">
            {RANGES.map((r) => (
              <button
                key={r.key}
                onClick={() => setRange(r.key)}
                className={`px-3 py-1 rounded-lg text-[10px] font-black tracking-widest transition-all ${
                  range === r.key 
                    ? "bg-card text-blue-600 shadow-sm border border-[var(--color-border)]" 
                    : "text-secondary hover:text-foreground"
                }`}
              >
                {r.label}
              </button>
            ))}
          </div>

          <div className="flex gap-1 p-1 bg-[var(--color-border-subtle)] rounded-xl border border-[var(--color-border)]">
            {MODES.map((m) => (
              <button
                key={m.key}
                onClick={() => setMode(m.key)}
                className={`px-3 py-1 rounded-lg text-[9px] font-black uppercase tracking-tighter transition-all ${
                  mode === m.key 
                    ? "bg-[var(--primary)] text-white shadow-md" 
                    : "text-secondary hover:text-slate-600"
                }`}
              >
                {copy.modes?.[m.labelKey] || m.key}
                
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* 🚀 TELEMETRY CHART */}
      <div className="mt-8 h-[260px] w-full min-w-0 relative">
            {loading && (
          <div className="absolute inset-0 flex items-center justify-center bg-white/50 backdrop-blur-[1px] z-10 text-[10px] font-black text-secondary uppercase tracking-[0.2em] animate-pulse">
            {copy.loading}
          </div>
        )}

        <ResponsiveContainer width="100%" height="100%">
          <AreaChart
            data={chartData}
            margin={{ left: 0, right: 0, top: 10, bottom: 0 }}
          >
            <defs>
              <linearGradient
                id={gradientId}
                x1="0"
                y1="0"
                x2="0"
                y2="1"
              >
                <stop
                  offset="0%"
                  stopColor={strokeColor}
                  stopOpacity={0.2}
                />
                <stop
                  offset="100%"
                  stopColor={strokeColor}
                  stopOpacity={0}
                />
              </linearGradient>
            </defs>

            <XAxis
              dataKey="label"
              axisLine={false}
              tickLine={false}
              tick={{ fontSize: 9, fontWeight: 900, fill: 'var(--color-text-muted)' }}
              interval="preserveStartEnd"
              dy={10}
            />

            <YAxis
              domain={yDomain}
              axisLine={false}
              tickLine={false}
              width={50}
              tick={{ fontSize: 9, fontWeight: 700, fill: 'var(--color-text-muted)', fontFamily: 'monospace' }}
              tickFormatter={(v) => formatNumber(v / 1000, locale, { maximumFractionDigits: 0 }) + "k"}
              dx={-5}
            />

            <Tooltip
              content={({ active, payload }) => {
                if (active && payload && payload.length) {
                  return (
                    <div className="bg-slate-900 border border-slate-800 p-3 rounded-xl shadow-2xl">
                      <div className="text-[8px] font-black text-muted uppercase tracking-widest mb-1">{copy.entryLog}</div>
                      <div className="text-sm font-black text-white font-mono">{formatValue(payload[0].value)}</div>
                      <div className="text-[9px] font-bold text-secondary mt-1">{payload[0].payload.label}</div>
                    </div>
                  );
                }
                return null;
              }}
            />

            <Area
              type="monotone"
              dataKey="value"
              stroke={strokeColor}
              strokeWidth={3}
              fill={`url(#${gradientId})`}
              dot={false}
              activeDot={{ r: 5, fill: strokeColor, stroke: '#fff', strokeWidth: 2 }}
            />
          </AreaChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
