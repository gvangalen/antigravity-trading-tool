"use client";

import { useEffect, useRef, useState } from "react";
import {
  buildTradingViewEmbedConfig,
  normalizeTradingViewInterval,
} from "../../../../shared/tradingViewConfig";

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
  const [studiesUnavailable, setStudiesUnavailable] = useState(false);
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
    setStudiesUnavailable(false);

    let cancelled = false;
    let attempt = 0;
    let timeout = null;
    let activeScript = null;

    const hasLoadedFrame = () => {
      const frame = container.querySelector("iframe");
      if (!frame) return false;
      try {
        const currentUrl = frame.contentWindow?.location?.href;
        return Boolean(currentUrl && currentUrl !== "about:blank");
      } catch {
        // A navigated TradingView frame is cross-origin and cannot be read.
        return true;
      }
    };

    const loadWidget = () => {
      if (cancelled || !container.isConnected) return;
      attempt += 1;
      if (activeScript) activeScript.onerror = null;
      const script = document.createElement("script");
      activeScript = script;
      script.src = "https://s3.tradingview.com/external-embedding/embed-widget-advanced-chart.js";
      script.type = "text/javascript";
      script.async = true;
      script.textContent = JSON.stringify(buildTradingViewEmbedConfig({
        interval: normalizedInterval,
        symbol,
        theme,
        indicators: JSON.parse(studiesKey),
      }));
      const widget = document.createElement("div");
      widget.className = "tradingview-widget-container__widget";
      widget.style.height = "100%";
      widget.style.width = "100%";
      container.replaceChildren(widget, script);

      const retryOrReport = () => {
        window.clearTimeout(timeout);
        if (cancelled || !container.isConnected) return;
        if (attempt < 2) {
          loadWidget();
        } else {
          container.replaceChildren();
          setStudiesUnavailable(true);
        }
      };
      script.onerror = retryOrReport;
      timeout = window.setTimeout(() => {
        // TradingView can insert an iframe that never leaves about:blank.
        // Its presence alone does not prove the chart has loaded.
        if (!hasLoadedFrame()) retryOrReport();
      }, 8000);
    };

    loadWidget();
    return () => {
      cancelled = true;
      window.clearTimeout(timeout);
      if (activeScript) activeScript.onerror = null;
      container.replaceChildren();
    };
  }, [normalizedInterval, studiesKey, symbol, theme]);

  return (
    <div
      className="relative rounded-xl border bg-card overflow-hidden"
      style={{ height }}
    >
      <div ref={widgetContainerRef} className="tradingview-widget-container h-full w-full" />
      {studiesUnavailable && chartFallbackLabel ? (
        <p role="status" className="absolute bottom-3 left-3 right-3 rounded-lg bg-white/95 px-3 py-2 text-xs text-slate-700 shadow-sm">
          {chartFallbackLabel}
        </p>
      ) : null}
    </div>
  );
}
