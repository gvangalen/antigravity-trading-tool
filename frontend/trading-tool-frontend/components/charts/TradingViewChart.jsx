"use client";

import { useEffect, useRef, useState } from "react";
import { normalizeTradingViewInterval } from "../../../../shared/tradingViewConfig";
import LocalMarketChart from "./LocalMarketChart";

const TRADINGVIEW_MODULE_URL = "https://widgets.tradingview-widget.com/w/en/tv-advanced-chart.js";
let widgetModulePromise;

function loadWidgetModule() {
  if (customElements.get("tv-advanced-chart")) return Promise.resolve();
  if (!widgetModulePromise) {
    widgetModulePromise = new Promise((resolve, reject) => {
      const script = document.createElement("script");
      const timeout = window.setTimeout(() => reject(new Error("TradingView module timeout")), 15000);
      script.type = "module";
      script.src = TRADINGVIEW_MODULE_URL;
      script.onload = () => customElements.whenDefined("tv-advanced-chart").then(() => {
        window.clearTimeout(timeout);
        resolve();
      }, reject);
      script.onerror = () => {
        window.clearTimeout(timeout);
        reject(new Error("TradingView widget unavailable"));
      };
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
  chartBackupLabel = "",
  onIntervalChange = () => {},
}) {
  const lastReportedIntervalRef = useRef(normalizeTradingViewInterval(interval));
  const widgetContainerRef = useRef(null);
  const [backupVisible, setBackupVisible] = useState(false);
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
    let attempt = 0;
    let readyTimeout;
    setBackupVisible(false);
    container.replaceChildren();

    const mountChart = () => {
      if (cancelled || !container.isConnected) return;
      attempt += 1;
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
      const retryOrReport = () => {
        window.clearTimeout(readyTimeout);
        chart.removeEventListener("tv-widget-ready", onReady);
        chart.removeEventListener("tv-widget-error", retryOrReport);
        if (cancelled || !container.isConnected || container.firstChild !== chart) return;
        if (attempt < 2) {
          setBackupVisible(true);
          mountChart();
        }
        else {
          container.replaceChildren();
          setBackupVisible(true);
        }
      };
      const onReady = () => {
        window.clearTimeout(readyTimeout);
        if (!cancelled && container.firstChild === chart) setBackupVisible(false);
      };
      chart.addEventListener("tv-widget-ready", onReady, { once: true });
      chart.addEventListener("tv-widget-error", retryOrReport, { once: true });
      // The element being defined does not mean its chart data has loaded.
      readyTimeout = window.setTimeout(retryOrReport, 12000);
      container.replaceChildren(chart);
    };

    loadWidgetModule().then(mountChart).catch(() => {
      if (!cancelled) setBackupVisible(true);
    });

    return () => {
      cancelled = true;
      window.clearTimeout(readyTimeout);
      container.replaceChildren();
    };
  }, [normalizedInterval, studiesKey, symbol, theme]);

  return (
    <div className="relative overflow-hidden rounded-xl border bg-card" style={{ height }}>
      <div ref={widgetContainerRef} className={`absolute inset-0 ${backupVisible ? "opacity-0 pointer-events-none" : "opacity-100"}`} />
      {backupVisible ? (
        <LocalMarketChart
          symbol={symbol}
          interval={normalizedInterval}
          unavailableLabel={chartFallbackLabel}
          backupLabel={chartBackupLabel}
        />
      ) : null}
    </div>
  );
}
