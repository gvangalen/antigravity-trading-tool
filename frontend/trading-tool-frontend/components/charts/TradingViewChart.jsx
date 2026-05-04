"use client";

import { useEffect, useRef } from "react";

export default function TradingViewChart({
  symbol = "BINANCE:BTCUSDT",
  interval = "D",
  theme = "light",
  height = 500,
  indicators = [], // New prop for indicator sync
}) {
  const containerRef = useRef(null);
  const chartId = useRef(`tv-chart-${Math.random().toString(36).substr(2, 9)}`);

  useEffect(() => {
    let isMounted = true;
    let timeoutId;
    
    const initChart = () => {
      if (!containerRef.current || !isMounted) return;
      
      // Clear previous widget
      containerRef.current.innerHTML = "";

      const script = document.createElement("script");
      script.src = "https://s3.tradingview.com/external-embedding/embed-widget-advanced-chart.js";
      script.async = true;
      script.id = `script-${chartId.current}`;

      const config = {
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
        studies: indicators,
      };

      script.innerHTML = JSON.stringify(config);
      containerRef.current.appendChild(script);
    };

    // Small delay to ensure DOM is ready and prevent 'null' querySelector errors
    timeoutId = setTimeout(initChart, 200);

    return () => {
      isMounted = false;
      clearTimeout(timeoutId);
      if (containerRef.current) {
        containerRef.current.innerHTML = "";
      }
    };
  }, [symbol, interval, indicators, theme]);

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
