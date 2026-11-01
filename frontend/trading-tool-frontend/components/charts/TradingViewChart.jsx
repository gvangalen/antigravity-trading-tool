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
      const timeout = window.setTimeout(() => reject(new Error("TradingView module timeout")), 30000);
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
    let readyTimeout;
    let retryTimeout;
    let attempt = 0;
    const backupDelay = window.setTimeout(() => {
      if (!cancelled) setBackupVisible(true);
    }, 12000);
    setBackupVisible(false);
    container.replaceChildren();

    const retry = (delay = 5000) => {
      if (cancelled || attempt >= 4) return;
      window.clearTimeout(retryTimeout);
      retryTimeout = window.setTimeout(startChart, delay);
    };

    const mountChart = () => {
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
      const showBackup = () => {
        window.clearTimeout(readyTimeout);
        if (cancelled || !container.isConnected || container.firstChild !== chart) return;
        setBackupVisible(true);
        // A slow widget can still finish; keep it mounted while the local
        // chart is visible, then remount only if it remains unavailable.
        retry(20000);
      };
      const onReady = () => {
        window.clearTimeout(readyTimeout);
        window.clearTimeout(retryTimeout);
        window.clearTimeout(backupDelay);
        chart.removeEventListener("tv-widget-error", showBackup);
        if (!cancelled && container.firstChild === chart) setBackupVisible(false);
      };
      chart.addEventListener("tv-widget-ready", onReady, { once: true });
      chart.addEventListener("tv-widget-error", showBackup, { once: true });
      // The element being defined does not mean its chart data has loaded.
      readyTimeout = window.setTimeout(showBackup, 12000);
      container.replaceChildren(chart);
    };

    const startChart = () => {
      if (cancelled || !container.isConnected) return;
      attempt += 1;
      loadWidgetModule().then(mountChart).catch(() => {
        if (!cancelled) {
          setBackupVisible(true);
          retry();
        }
      });
    };
    startChart();

    return () => {
      cancelled = true;
      window.clearTimeout(readyTimeout);
      window.clearTimeout(retryTimeout);
      window.clearTimeout(backupDelay);
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
          indicators={indicators}
          unavailableLabel={chartFallbackLabel}
          backupLabel={chartBackupLabel}
        />
      ) : null}
    </div>
  );
}
