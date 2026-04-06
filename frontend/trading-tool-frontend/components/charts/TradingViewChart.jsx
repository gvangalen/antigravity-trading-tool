"use client";

import { useEffect, useRef } from "react";

export default function TradingViewChart({
  symbol = "BINANCE:BTCUSDT",
  interval = "D",
  theme = "light",
  height = 500,
}) {
  const containerRef = useRef(null);
  const initializedRef = useRef(false);

  useEffect(() => {
    if (!containerRef.current) return;
    if (initializedRef.current) return; // 🔒 voorkomt dubbele injectie

    initializedRef.current = true;

    const script = document.createElement("script");
    script.src =
      "https://s3.tradingview.com/external-embedding/embed-widget-advanced-chart.js";
    script.async = true;

    script.innerHTML = JSON.stringify({
      autosize: true,
      symbol,
      interval,
      timezone: "Etc/UTC",
      theme,
      style: "1",
      locale: "en",
      hide_top_toolbar: false,
      hide_side_toolbar: true,
      allow_symbol_change: true,
      save_image: false,
      calendar: false,
      support_host: "https://www.tradingview.com",
    });

    containerRef.current.appendChild(script);
  }, []); // ⛔️ bewust GEEN dependencies

  return (
    <div
      className="rounded-xl border bg-white overflow-hidden"
      style={{ height }}
    >
      <div ref={containerRef} className="h-full w-full" />
    </div>
  );
}
