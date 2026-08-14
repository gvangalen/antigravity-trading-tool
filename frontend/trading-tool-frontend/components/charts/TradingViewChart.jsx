"use client";

import { useEffect, useMemo, useRef } from "react";
import {
  buildTradingViewWidgetUrl,
  normalizeTradingViewInterval,
} from "../../../../shared/tradingViewConfig";

export default function TradingViewChart({
  symbol = "BINANCE:BTCUSDT",
  interval = "D",
  theme = "light",
  height = 500,
  indicators = [], // New prop for indicator sync
  onIntervalChange = () => {},
}) {
  const lastReportedIntervalRef = useRef(normalizeTradingViewInterval(interval));
  const normalizedInterval = normalizeTradingViewInterval(interval);
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

  return (
    <div
      className="rounded-xl border bg-card overflow-hidden"
      style={{ height }}
    >
      <iframe
        title={`TradingView ${symbol}`}
        src={widgetUrl}
        className="h-full w-full border-0"
        allowTransparency
        loading="eager"
      />
    </div>
  );
}
