"use client";

import { useEffect, useRef, useState } from "react";
import { CandlestickSeries, ColorType, HistogramSeries, LineSeries, createChart } from "lightweight-charts";
import { apiGet } from "@/lib/api/apiClient";
import { movingAverageSeries, rsiSeries } from "@/lib/charts/technicalStudies.mjs";

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

export default function LocalMarketChart({ symbol, interval, indicators = [], unavailableLabel, backupLabel }) {
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
    const studyNames = [];
    for (const study of indicators) {
      const id = typeof study === "string" ? study : study?.id;
      const requestedLength = Number(study?.inputs?.length);
      if (id === "RSI@tv-basicstudies") {
        const length = Number.isInteger(requestedLength) && requestedLength > 1 ? requestedLength : 14;
        const values = rsiSeries(candles, length);
        if (values.length) {
          const line = chart.addSeries(LineSeries, {
            color: "#7c3aed", lineWidth: 2,
            priceFormat: { type: "price", precision: 1, minMove: 0.1 },
            title: `RSI ${length}`,
          }, 1);
          line.setData(values);
          studyNames.push(`RSI ${length}`);
        }
      } else if (id === "MASimple@tv-basicstudies" || id === "MAExp@tv-basicstudies") {
        const length = Number.isInteger(requestedLength) && requestedLength > 1 ? requestedLength : 50;
        const exponential = id === "MAExp@tv-basicstudies";
        const values = movingAverageSeries(candles, length, exponential);
        if (values.length) {
          const label = `${exponential ? "EMA" : "MA"} ${length}`;
          const line = chart.addSeries(LineSeries, {
            color: exponential ? "#f59e0b" : "#2563eb", lineWidth: 2, title: label,
          });
          line.setData(values);
          studyNames.push(label);
        }
      }
    }
    chart.timeScale().fitContent();
    container.dataset.studies = studyNames.join(", ");
    return () => { delete container.dataset.studies; chart.remove(); };
  }, [payload, interval, indicators]);

  const candles = validCandles(payload?.candles);
  const rsiStudy = indicators.find((study) => (typeof study === "string" ? study : study?.id) === "RSI@tv-basicstudies");
  const requestedRsiLength = Number(rsiStudy?.inputs?.length);
  const rsiLength = Number.isInteger(requestedRsiLength) && requestedRsiLength > 1 ? requestedRsiLength : 14;
  return (
    <div className="relative h-full w-full bg-white">
      <div ref={containerRef} className="h-full w-full" />
      {candles.length >= 2 ? (
        <>
          {rsiStudy && rsiSeries(candles, rsiLength).length > 0 ? (
            <span className="absolute left-2 top-2 rounded bg-white/90 px-2 py-1 text-xs font-semibold text-violet-700">{`RSI ${rsiLength}`}</span>
          ) : null}
          <p role="status" className="absolute bottom-2 left-2 rounded bg-white/90 px-2 py-1 text-xs text-slate-600">
            {backupLabel} · {payload.source} · {symbol}
          </p>
        </>
      ) : (
        <p role="status" className="absolute inset-0 flex items-center justify-center px-4 text-center text-sm text-slate-600">
          {failed || payload ? unavailableLabel : backupLabel}
        </p>
      )}
    </div>
  );
}
