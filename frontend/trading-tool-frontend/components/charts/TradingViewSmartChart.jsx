"use client";

import React, { useEffect, useRef, useState } from "react";
import { createChart, ColorType, CandlestickSeries, createSeriesMarkers, HistogramSeries } from "lightweight-charts";
import TradingViewChart from "./TradingViewChart";
import { useMarketOHLCV } from "@/hooks/useMarketOHLCV";
import { useBotTrades } from "@/hooks/useBotTrades";
import { Bot as BotIcon, Layout, Maximize2, Settings2, BarChart3, Clock, Info } from "lucide-react";

/**
 * 🛰️ TradingViewSmartChart — PRO VERSION
 * Toggles between Analysis Mode (Legacy TV Widget) and Execution Mode (Lightweight Charts with Bots).
 */
export default function TradingViewSmartChart({
  symbol = "BINANCE:BTCUSDT",
  interval = "D",
  indicators = [],
  focusedBotId = null,
  setFocusedBotId = () => {},
  height = 500,
}) {
  const containerRef = useRef(null);
  const chartRef = useRef(null);
  const [hoveredData, setHoveredData] = useState(null);
  const { candles, loading: candlesLoading } = useMarketOHLCV();
  const { trades, loading: tradesLoading } = useBotTrades(focusedBotId);

  // If no bot is focused, we use the high-fidelity standard TradingView Widget
  if (!focusedBotId) {
    return (
      <TradingViewChart
        symbol={symbol}
        interval={interval}
        indicators={indicators}
        height={height}
      />
    );
  }

  // 🤖 BOT FOCUS MODE: Rendering with lightweight-charts for marker support
  useEffect(() => {
    if (!containerRef.current || candlesLoading || !candles.length) return;

    // 🛡️ SECURITY CHECK: Prevent "width(-1)" error in console
    if (containerRef.current.clientWidth <= 0 || containerRef.current.clientHeight <= 0) {
      // Re-run this effect when the container gets a size
      const observer = new ResizeObserver(() => {
        if (containerRef.current && containerRef.current.clientWidth > 0) {
          // This will trigger a re-render or we can just wait for the next tick
          window.dispatchEvent(new Event('resize'));
        }
      });
      observer.observe(containerRef.current);
      return () => observer.disconnect();
    }

    const chart = createChart(containerRef.current, {
      layout: {
        background: { type: ColorType.Solid, color: "#ffffff" },
        textColor: "#64748b",
        fontSize: 11,
        fontFamily: "'Inter', sans-serif",
      },
      width: containerRef.current.clientWidth,
      height: height,
      grid: {
        vertLines: { visible: false },
        horzLines: { color: "rgba(241, 245, 249, 0.8)", style: 2 },
      },
      timeScale: {
        borderColor: "#f1f5f9",
        barSpacing: 6,
        minBarSpacing: 2,
        timeVisible: true,
        secondsVisible: false,
        rightOffset: 12,
      },
      rightPriceScale: {
        borderColor: "#f1f5f9",
        autoScale: true,
        alignLabels: true,
        scaleMargins: {
          top: 0.15,
          bottom: 0.25,
        },
      },
      crosshair: {
        mode: 0, // Normal
        vertLine: {
          color: "#94a3b8",
          width: 1,
          style: 3, // Dotted
          labelBackgroundColor: "#1e293b",
        },
        horzLine: {
          color: "#94a3b8",
          width: 1,
          style: 3, // Dotted
          labelBackgroundColor: "#1e293b",
        },
      },
      watermark: {
        visible: true,
        fontSize: 48,
        horzAlign: "center",
        vertAlign: "center",
        color: "rgba(30, 41, 59, 0.05)",
        text: symbol.split(":")[1] || symbol,
      },
    });

    chartRef.current = chart;

    // 🕯️ CANDLESTICK SERIES
    const candlestickSeries = chart.addSeries(CandlestickSeries, {
      upColor: "#10b981",
      downColor: "#f43f5e",
      borderVisible: true,
      borderUpColor: "#10b981",
      borderDownColor: "#f43f5e",
      wickVisible: true,
      wickUpColor: "#10b981",
      wickDownColor: "#f43f5e",
    });

    // 📊 VOLUME SERIES
    const volumeSeries = chart.addSeries(HistogramSeries, {
      color: "#94a3b8",
      priceFormat: { type: "volume" },
      priceScaleId: "", // overlay
    });

    volumeSeries.priceScale().applyOptions({
      scaleMargins: { top: 0.8, bottom: 0 },
    });

    candlestickSeries.setData(candles);
    
    // Map candles to volume data
    const volumeData = candles.map(c => ({
      time: c.time,
      value: c.volume || 100, // Fallback if missing
      color: c.close >= c.open ? "rgba(34, 197, 94, 0.3)" : "rgba(239, 68, 68, 0.3)",
    }));
    volumeSeries.setData(volumeData);

    // 🎯 DRAW TRADE MARKERS (GROUPED)
    if (trades && trades.length > 0) {
      // 1. Group by date to prevent overlap
      const grouped = trades.reduce((acc, trade) => {
        const rawDate = trade.created_at || trade.timestamp || trade.executed_at;
        if (!rawDate) return acc;
        const d = new Date(rawDate);
        if (isNaN(d.getTime())) return acc;
        const dateKey = d.toISOString().split("T")[0];
        
        if (!acc[dateKey]) acc[dateKey] = { buy: [], sell: [] };
        const side = String(trade.side || "").toLowerCase();
        if (side === "buy") acc[dateKey].buy.push(trade);
        else acc[dateKey].sell.push(trade);
        return acc;
      }, {});

      // 2. Map grouped trades to markers
      const markers = [];
      Object.entries(grouped).forEach(([time, sideData]) => {
        if (sideData.buy.length > 0) {
          const count = sideData.buy.length;
          const avgPrice = sideData.buy.reduce((s, t) => s + (t.price || t.avg_fill_price || 0), 0) / count;
          markers.push({
            time,
            position: "belowBar",
            color: "#10b981", // More vibrant emerald
            shape: "arrowUp",
            text: count > 1 ? `${count}x BUY @ ${Math.round(avgPrice)}` : `BUY ${Math.round(avgPrice)}`,
            size: 1,
          });
        }
        if (sideData.sell.length > 0) {
          const count = sideData.sell.length;
          const avgPrice = sideData.sell.reduce((s, t) => s + (t.price || t.avg_fill_price || 0), 0) / count;
          markers.push({
            time,
            position: "aboveBar",
            color: "#f43f5e", // More vibrant rose
            shape: "arrowDown",
            text: count > 1 ? `${count}x SELL @ ${Math.round(avgPrice)}` : `SELL ${Math.round(avgPrice)}`,
            size: 1,
          });
        }
      });
      
      // Sort markers by time
      markers.sort((a, b) => (a.time > b.time ? 1 : -1));
      createSeriesMarkers(candlestickSeries, markers);
    }

    chart.timeScale().fitContent();

    // 🕵️‍♀️ CROSSHAIR MOVE (OHLC LEGEND)
    chart.subscribeCrosshairMove((param) => {
      if (
        param.point === undefined ||
        !param.time ||
        param.point.x < 0 ||
        param.point.x > containerRef.current.clientWidth ||
        param.point.y < 0 ||
        param.point.y > height
      ) {
        setHoveredData(null);
      } else {
        const data = param.seriesData.get(candlestickSeries);
        if (data) {
          setHoveredData(data);
        }
      }
    });

    const handleResize = () => {
      chart.applyOptions({ width: containerRef.current.clientWidth });
    };

    window.addEventListener("resize", handleResize);

    return () => {
      window.removeEventListener("resize", handleResize);
      chart.remove();
    };
  }, [candles, trades, candlesLoading, height]);

  return (
    <div className="relative w-full border border-slate-200 rounded-xl overflow-hidden bg-white shadow-sm" style={{ height: height + 50 }}>
      {/* 🛠️ PRO TOOLBAR */}
      <div className="h-10 border-b border-slate-100 bg-slate-50/50 flex items-center justify-between px-3">
        <div className="flex items-center gap-4">
          <div className="flex items-center gap-2 pr-4 border-r border-slate-200">
            <div className="w-5 h-5 bg-orange-500 rounded-full flex items-center justify-center text-[10px] text-white font-bold italic">₿</div>
            <span className="text-sm font-bold text-slate-700">{symbol.split(":")[1] || symbol}</span>
            <span className="text-xs font-medium text-slate-400">Botmodus</span>
          </div>
          
          <div className="flex items-center gap-3">
            <button className="flex items-center gap-1 text-xs font-bold text-blue-600 px-2 py-1 bg-blue-50 rounded select-none">
              {interval}
            </button>
            <div className="flex items-center gap-2 text-slate-400">
              <BarChart3 size={16} className="cursor-not-allowed opacity-50" />
              <Info size={16} className="cursor-help" title="Execution history is overlayed on OHLCV data" />
            </div>
          </div>
        </div>

        <div className="flex items-center gap-3 text-slate-400">
          <button onClick={() => setFocusedBotId(null)} className="flex items-center gap-2 px-3 py-1 hover:bg-slate-200/50 rounded transition-colors group">
             <Layout size={14} />
             <span className="text-xs font-bold text-slate-500 group-hover:text-blue-600">Back</span>
          </button>
          <Settings2 size={16} className="cursor-pointer hover:text-slate-600" />
          <Maximize2 size={16} className="cursor-pointer hover:text-slate-600" />
        </div>
      </div>

      <div className="relative" style={{ height }}>
        {/* 🏷️ OHLC LEGEND OVERLAY */}
        {focusedBotId && candles.length > 0 && (
          <div className="absolute top-4 left-4 z-20 pointer-events-none p-2 rounded bg-white/40 backdrop-blur-[2px] border border-slate-200/20 select-none flex flex-col gap-1">
            <div className="flex items-center gap-2">
              <span className="text-sm font-black text-slate-800 tracking-tighter">{symbol.split(":")[1] || symbol}</span>
              <span className="text-[10px] font-bold text-white bg-blue-600 px-1 rounded uppercase tracking-widest">{interval}</span>
            </div>
            
            {hoveredData ? (
              <div className="flex gap-3 text-[11px] font-mono leading-none">
                <div className="flex gap-1"><span className="text-slate-400">O</span><span className={hoveredData.close >= hoveredData.open ? "text-emerald-600" : "text-red-500"}>{hoveredData.open.toFixed(2)}</span></div>
                <div className="flex gap-1"><span className="text-slate-400">H</span><span className={hoveredData.close >= hoveredData.open ? "text-emerald-600" : "text-red-500"}>{hoveredData.high.toFixed(2)}</span></div>
                <div className="flex gap-1"><span className="text-slate-400">L</span><span className={hoveredData.close >= hoveredData.open ? "text-emerald-600" : "text-red-500"}>{hoveredData.low.toFixed(2)}</span></div>
                <div className="flex gap-1"><span className="text-slate-400">C</span><span className={hoveredData.close >= hoveredData.open ? "text-emerald-600" : "text-red-500"}>{hoveredData.close.toFixed(2)}</span></div>
              </div>
            ) : candles.length > 0 && (
               <div className="flex gap-3 text-[11px] font-mono leading-none opacity-50">
                <div className="flex gap-1"><span className="text-slate-400">O</span><span>{candles[candles.length-1].open.toFixed(2)}</span></div>
                <div className="flex gap-1"><span className="text-slate-400">H</span><span>{candles[candles.length-1].high.toFixed(2)}</span></div>
                <div className="flex gap-1"><span className="text-slate-400">L</span><span>{candles[candles.length-1].low.toFixed(2)}</span></div>
                <div className="flex gap-1"><span className="text-slate-400">C</span><span>{candles[candles.length-1].close.toFixed(2)}</span></div>
              </div>
            )}
          </div>
        )}

        { (candlesLoading || tradesLoading) && (
          <div className="absolute inset-0 flex items-center justify-center bg-white/50 z-20">
            <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
          </div>
        )}

        {/* 🧩 EMPTY STATE FALLBACK */}
        {!candlesLoading && focusedBotId && candles.length === 0 && (
          <div className="absolute inset-0 flex flex-col items-center justify-center bg-slate-50 dark:bg-slate-900/50 p-8 text-center z-10">
            <div className="w-16 h-16 bg-blue-100 dark:bg-blue-900/30 rounded-full flex items-center justify-center mb-4 text-blue-600">
              <BotIcon size={32} />
            </div>
            <h3 className="text-lg font-bold text-slate-900 dark:text-white mb-2">Nog geen historie gevonden</h3>
            <p className="text-sm text-slate-500 max-w-xs">
              Deze bot heeft nog geen trades vastgelegd. Start een cyclus of gebruik simulatie om hier de uitvoer terug te zien.
            </p>
            <button 
              onClick={() => setFocusedBotId(null)}
              className="mt-6 text-xs font-bold text-blue-600 hover:underline uppercase tracking-widest"
            >
              Terug naar analyse
            </button>
          </div>
        )}

        <div ref={containerRef} className="w-full h-full" />
      </div>
    </div>
  );
}
