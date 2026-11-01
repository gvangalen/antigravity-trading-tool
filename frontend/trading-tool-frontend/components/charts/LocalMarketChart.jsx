"use client";

import { useEffect, useRef, useState } from "react";
import { CandlestickSeries, ColorType, HistogramSeries, createChart } from "lightweight-charts";
import { apiGet } from "@/lib/api/apiClient";

function validCandles(rows) {
  const byTime = new Map();
  for (const row of Array.isArray(rows) ? rows : []) {
    const time = Math.floor(Date.parse(row.time) / 1000);
    const open = Number(row.open);
    const high = Number(row.high);
    const low = Number(row.low);
    const close = Number(row.close);
    if (![time, open, high, low, close].every(Number.isFinite) ||
        open <= 0 || close <= 0 || low <= 0 ||
        high < Math.max(open, close, low) || low > Math.min(open, close)) continue;
    byTime.set(time, { time, open, high, low, close,
      volume: Number.isFinite(Number(row.volume)) ? Math.max(0, Number(row.volume)) : null });
  }
  return [...byTime.values()].sort((a, b) => a.time - b.time);
}

export default function LocalMarketChart({ symbol, interval, unavailableLabel, backupLabel }) {
  const containerRef = useRef(null);
  const [payload, setPayload] = useState(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let active = true;
    setPayload(null);
    setFailed(false);
    const params = new URLSearchParams({ tradingview_symbol: symbol, interval });
    apiGet(`/api/assets/chart-candles?${params}`)
      .then((data) => { if (active) setPayload(data); })
      .catch(() => { if (active) setFailed(true); });
    return () => { active = false; };
  }, [symbol, interval]);

  useEffect(() => {
    const container = containerRef.current;
    const candles = validCandles(payload?.candles);
    if (!container || candles.length < 2) return;
    const chart = createChart(container, {
      autoSize: true,
      layout: { background: { type: ColorType.Solid, color: "#ffffff" }, textColor: "#475569" },
      grid: { vertLines: { color: "#f1f5f9" }, horzLines: { color: "#f1f5f9" } },
      rightPriceScale: { borderColor: "#e2e8f0" },
      timeScale: { borderColor: "#e2e8f0", timeVisible: ["15", "60", "240"].includes(interval) },
    });
    const price = chart.addSeries(CandlestickSeries, {
      upColor: "#10b981", downColor: "#ef4444", borderVisible: false,
      wickUpColor: "#10b981", wickDownColor: "#ef4444",
    });
    price.setData(candles.map(({ volume, ...candle }) => candle));
    if (candles.some((candle) => candle.volume !== null)) {
      const volume = chart.addSeries(HistogramSeries, {
        priceScaleId: "", priceFormat: { type: "volume" },
      });
      volume.priceScale().applyOptions({ scaleMargins: { top: 0.8, bottom: 0 } });
      volume.setData(candles.filter((candle) => candle.volume !== null).map((candle) => ({
        time: candle.time, value: candle.volume,
        color: candle.close >= candle.open ? "#10b98155" : "#ef444455",
      })));
    }
    chart.timeScale().fitContent();
    return () => chart.remove();
  }, [payload, interval]);

  const candles = validCandles(payload?.candles);
  return (
    <div className="relative h-full w-full bg-white">
      <div ref={containerRef} className="h-full w-full" />
      {candles.length >= 2 ? (
        <p role="status" className="absolute bottom-2 left-2 rounded bg-white/90 px-2 py-1 text-xs text-slate-600">
          {backupLabel} · {payload.source} · {symbol}
        </p>
      ) : (
        <p role="status" className="absolute inset-0 flex items-center justify-center px-4 text-center text-sm text-slate-600">
          {failed || payload ? unavailableLabel : backupLabel}
        </p>
      )}
    </div>
  );
}
