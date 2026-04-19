"use client";
import React from "react";
import { Globe2, LineChart } from "lucide-react";
import SkeletonTable from "@/components/ui/SkeletonTable";
import TechnicalTerminalGrid from "@/components/technical/TechnicalTerminalGrid";
import { useModal } from "@/components/modal/ModalProvider";
import TradingViewChart from "@/components/charts/TradingViewChart";

const SYMBOL_MAP = {
  "us_dollar_index_(dxy)": "CAPITALCOM:DXY",
  "dxy": "CAPITALCOM:DXY",
  "sp500": "SP:SPX",
  "s&p_500_index": "SP:SPX",
  "vix": "TVC:VIX",
  "volatility_index_(vix)": "TVC:VIX",
  "gold_price": "TVC:GOLD",
  "oil_price": "TVC:USOIL",
  "crude_oil_price_(wti)": "TVC:USOIL",
  "us10y": "TVC:US10Y",
  "us_10-year_yield": "TVC:US10Y",
  "us02y": "TVC:US02Y",
  "us_2-year_yield": "TVC:US02Y",
  "btc_dominance": "CRYPTOCAP:BTC.D",
  "bitcoin_dominance": "CRYPTOCAP:BTC.D",
  "fear_greed_index": "COINBASE:BTCUSD",
};

export default function MacroSummaryTableForDashboard({
  data = [],
  loading = false,
  error = "",
  onRetry = null,
}) {
  const { openConfirm } = useModal();

  // ⏳ LOADING
  if (loading) {
    return <SkeletonTable rows={5} columns={5} />;
  }

  const handleViewChart = (name) => {
    const normalized = name.toLowerCase().replace(/ /g, "_");
    const symbol = SYMBOL_MAP[normalized] || "BINANCE:BTCUSDT";

    openConfirm({
      title: `Live Chart: ${name}`,
      description: (
        <div className="w-full h-[400px] mt-4">
          <TradingViewChart symbol={symbol} height={400} />
        </div>
      ),
      confirmText: "Close",
      icon: <LineChart className="w-5 h-5 text-blue-500" />,
      tone: "info"
    });
  };

  // ✅ Data defensief maken
  const safeData = Array.isArray(data) ? data : [];

  // 🔥 DEFINITIEVE NORMALISATIE
  const formatted = safeData.map((item) => ({
    name: item.display_name || item.name || item.indicator || "–",
    indicator: item.indicator || item.name || "–",
    value: item.value ?? null,
    score: item.score ?? null,
    action: item.action ?? "–",
    interpretation: item.interpretation ?? "–",
    timestamp: item.timestamp,
  }));

  return (
    <TechnicalTerminalGrid
      title="Macro Indicatoren"
      icon={<Globe2 className="w-5 h-5 text-[var(--primary)]" />}
      data={formatted}
      error={error}
      onRetry={onRetry}
      onRemove={null} 
      onViewChart={handleViewChart}
    />
  );
}
