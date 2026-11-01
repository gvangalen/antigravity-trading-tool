"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import {
  buildTradingViewEmbedConfig,
  buildTradingViewWidgetUrl,
  normalizeTradingViewInterval,
} from "../../../../shared/tradingViewConfig";

export default function TradingViewChart({
  symbol = "BINANCE:BTCUSDT",
  interval = "D",
  theme = "light",
  height = 500,
  indicators = [],
  studyFallbackLabel = "",
  chartFallbackLabel = "",
  onIntervalChange = () => {},
}) {
  const lastReportedIntervalRef = useRef(normalizeTradingViewInterval(interval));
  const widgetContainerRef = useRef(null);
  const [studiesUnavailable, setStudiesUnavailable] = useState(false);
  const normalizedInterval = normalizeTradingViewInterval(interval);
  const studiesKey = JSON.stringify(indicators);
  const widgetUrl = useMemo(
    () =>
      buildTradingViewWidgetUrl({
        interval: normalizedInterval,
        symbol,
        theme,
      }),
    [normalizedInterval, symbol, theme]
  );

  useEffect(() => {
    if (normalizedInterval === lastReportedIntervalRef.current) return;
    lastReportedIntervalRef.current = normalizedInterval;
    onIntervalChange(normalizedInterval);
  }, [normalizedInterval, onIntervalChange]);

  useEffect(() => {
    const container = widgetContainerRef.current;
    if (!container) return;
    setStudiesUnavailable(false);

    const script = document.createElement("script");
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

    // Keep the price chart available if the third-party embed cannot load.
    const showFallback = () => {
      if (!container.isConnected || container.querySelector("iframe")) return;
      const frame = document.createElement("iframe");
      frame.title = `TradingView ${symbol}`;
      frame.src = widgetUrl;
      frame.className = "h-full w-full border-0";
      container.replaceChildren(frame);
      setStudiesUnavailable(true);
    };
    script.onerror = showFallback;
    const timeout = window.setTimeout(showFallback, 12000);
    return () => {
      window.clearTimeout(timeout);
      script.onerror = null;
      container.replaceChildren();
    };
  }, [indicators.length, normalizedInterval, studiesKey, symbol, theme, widgetUrl]);

  return (
    <div
      className="relative rounded-xl border bg-card overflow-hidden"
      style={{ height }}
    >
      <div ref={widgetContainerRef} className="tradingview-widget-container h-full w-full" />
      {studiesUnavailable && (indicators.length ? studyFallbackLabel : chartFallbackLabel) ? (
        <p role="status" className="absolute bottom-3 left-3 right-3 rounded-lg bg-white/95 px-3 py-2 text-xs text-slate-700 shadow-sm">
          {indicators.length ? studyFallbackLabel : chartFallbackLabel}
        </p>
      ) : null}
    </div>
  );
}
