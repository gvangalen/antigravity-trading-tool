"use client";

import { useEffect, useRef, useState } from "react";
import { normalizeTradingViewInterval } from "../../../../shared/tradingViewConfig";

const TRADINGVIEW_MODULE_URL = "https://widgets.tradingview-widget.com/w/en/tv-advanced-chart.js";
let widgetModulePromise;

function loadWidgetModule() {
  if (customElements.get("tv-advanced-chart")) return Promise.resolve();
  if (!widgetModulePromise) {
    widgetModulePromise = new Promise((resolve, reject) => {
      const script = document.createElement("script");
      script.type = "module";
      script.src = TRADINGVIEW_MODULE_URL;
      script.onload = () => customElements.whenDefined("tv-advanced-chart").then(resolve, reject);
      script.onerror = () => reject(new Error("TradingView widget unavailable"));
      document.head.appendChild(script);
    }).catch((error) => {
      widgetModulePromise = undefined;
      throw error;
    });
  }
  return widgetModulePromise;
}

export default function TradingViewChart({
  symbol = "BINANCE:BTCUSDT",
  interval = "D",
  theme = "light",
  height = 500,
  indicators = [],
  chartFallbackLabel = "",
  onIntervalChange = () => {},
}) {
  const lastReportedIntervalRef = useRef(normalizeTradingViewInterval(interval));
  const widgetContainerRef = useRef(null);
  const [widgetUnavailable, setWidgetUnavailable] = useState(false);
  const normalizedInterval = normalizeTradingViewInterval(interval);
  const studiesKey = JSON.stringify(indicators);

  useEffect(() => {
    if (normalizedInterval === lastReportedIntervalRef.current) return;
    lastReportedIntervalRef.current = normalizedInterval;
    onIntervalChange(normalizedInterval);
  }, [normalizedInterval, onIntervalChange]);

  useEffect(() => {
    const container = widgetContainerRef.current;
    if (!container) return;
    let cancelled = false;
    setWidgetUnavailable(false);
    container.replaceChildren();

    loadWidgetModule().then(() => {
      if (cancelled || !container.isConnected) return;
      const chart = document.createElement("tv-advanced-chart");
      chart.setAttribute("symbol", symbol);
      chart.setAttribute("interval", normalizedInterval === "D" || normalizedInterval === "W" || normalizedInterval === "M" ? `1${normalizedInterval}` : normalizedInterval);
      chart.setAttribute("timezone", "Etc/UTC");
      chart.setAttribute("chart-type", "candles");
      chart.setAttribute("theme", theme);
      chart.setAttribute("hide-snapshot-button", "true");
      chart.setAttribute("studies", studiesKey);
      chart.style.display = "block";
      chart.style.width = "100%";
      chart.style.height = "100%";
      container.replaceChildren(chart);
    }).catch(() => {
      if (!cancelled) setWidgetUnavailable(true);
    });

    return () => {
      cancelled = true;
      container.replaceChildren();
    };
  }, [normalizedInterval, studiesKey, symbol, theme]);

  return (
    <div className="relative overflow-hidden rounded-xl border bg-card" style={{ height }}>
      <div ref={widgetContainerRef} className="h-full w-full" />
      {widgetUnavailable && chartFallbackLabel ? (
        <p role="status" className="absolute bottom-3 left-3 right-3 rounded-lg bg-white/95 px-3 py-2 text-xs text-slate-700 shadow-sm">
          {chartFallbackLabel}
        </p>
      ) : null}
    </div>
  );
}
