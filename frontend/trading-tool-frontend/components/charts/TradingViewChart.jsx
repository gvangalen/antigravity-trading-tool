"use client";

import { useEffect, useRef } from "react";
import {
  buildTradingViewEmbedConfig,
  normalizeTradingViewInterval,
  parseTradingViewIntervalFromUrl,
} from "../../../../shared/tradingViewConfig";

export default function TradingViewChart({
  symbol = "BINANCE:BTCUSDT",
  interval = "D",
  theme = "light",
  height = 500,
  indicators = [], // New prop for indicator sync
  onIntervalChange = () => {},
}) {
  const containerRef = useRef(null);
  const chartId = useRef(`tv-chart-${Math.random().toString(36).substr(2, 9)}`);
  const lastReportedIntervalRef = useRef(normalizeTradingViewInterval(interval));

  useEffect(() => {
    let isMounted = true;
    let timeoutId;
    let observer;
    let pollId;

    const reportInterval = (candidateUrl) => {
      const detected = parseTradingViewIntervalFromUrl(candidateUrl || "");
      if (!detected || detected === lastReportedIntervalRef.current) return;
      lastReportedIntervalRef.current = detected;
      onIntervalChange(detected);
    };

    const inspectIframe = () => {
      const iframe = containerRef.current?.querySelector?.("iframe");
      const src = iframe?.getAttribute?.("src") || iframe?.src;
      if (src) {
        reportInterval(src);
      }
    };
    
    const initChart = () => {
      if (!containerRef.current || !isMounted) return;
      
      // Clear previous widget
      containerRef.current.innerHTML = "";

      const script = document.createElement("script");
      script.src = "https://s3.tradingview.com/external-embedding/embed-widget-advanced-chart.js";
      script.async = true;
      script.id = `script-${chartId.current}`;

      const config = buildTradingViewEmbedConfig({
        allowSymbolChange: true,
        indicators,
        interval,
        symbol,
        theme,
      });

      script.innerHTML = JSON.stringify(config);
      containerRef.current.appendChild(script);

      observer = new MutationObserver(() => {
        inspectIframe();
      });
      observer.observe(containerRef.current, {
        attributes: true,
        attributeFilter: ["src"],
        childList: true,
        subtree: true,
      });
      pollId = window.setInterval(inspectIframe, 1000);
      inspectIframe();
    };

    // Small delay to ensure DOM is ready and prevent 'null' querySelector errors
    timeoutId = setTimeout(initChart, 300);

    return () => {
      isMounted = false;
      clearTimeout(timeoutId);
      if (observer) observer.disconnect();
      if (pollId) window.clearInterval(pollId);
      if (containerRef.current) {
        containerRef.current.innerHTML = "";
      }
    };
  }, [symbol, interval, indicators, onIntervalChange, theme]);

  return (
    <div
      key={`container-${symbol}-${interval}`}
      className="rounded-xl border bg-card overflow-hidden"
      style={{ height }}
    >
      <div id={chartId.current} ref={containerRef} className="h-full w-full" />
    </div>
  );
}
