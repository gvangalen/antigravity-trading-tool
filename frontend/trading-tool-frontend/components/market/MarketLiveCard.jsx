"use client";

import { useRef, useState } from "react";
import { formatNumber } from "@/components/market/utils";
import { fetchLatestPrice } from "@/lib/api/market";
import { MarketCardSkeleton } from "@/components/dashboard/DashboardSkeleton";
import { useVisibilityPolling } from "@/hooks/useVisibilityPolling";
import { useTranslation } from "@/app/providers/I18nProvider";
import { normalizeLocale } from "@/lib/i18n";

// Lucide icons
import {
  TrendingUp,
  TrendingDown,
  Clock,
  Activity,
} from "lucide-react";

export default function MarketLiveCard({ symbol = "BTC", data = null, loading: propLoading = false, error: propError = "" }) {
  const { locale } = useTranslation();
  const isDutch = normalizeLocale(locale) === "nl";
  const [internalPrice, setInternalPrice] = useState(null);
  const [internalLoading, setInternalLoading] = useState(true);
  const [internalError, setInternalError] = useState("");
  const isFetchingRef = useRef(false);

  const asset = data || internalPrice;
  const loading = propLoading || (data ? false : internalLoading);
  const error = propError || (data ? "" : internalError);
  const copy = {
    fetchError: isDutch ? `Fout bij ophalen ${symbol}-data` : `Failed to load ${symbol} data`,
    unavailable: isDutch ? `Geen ${symbol} data beschikbaar` : `No ${symbol} data available`,
    livePrice: isDutch ? `Live ${symbol} koers` : `Live ${symbol} price`,
    currentPrice: isDutch ? "Huidige koers (USD)" : "Current price (USD)",
    change24h: isDutch ? "24u verandering" : "24h change",
    volume24h: isDutch ? "24u volume" : "24h volume",
  };

  useVisibilityPolling(loadData, {
    enabled: !data && Boolean(symbol),
    intervalMs: 30000,
    backgroundIntervalMs: 120000,
    runImmediately: true,
    deps: [data, symbol],
  });

  async function loadData() {
    if (isFetchingRef.current) return;
    isFetchingRef.current = true;
    setInternalLoading(true);
    try {
      const resp = await fetchLatestPrice(symbol, { forceFresh: false });
      setInternalPrice(resp);
      setInternalError("");
    } catch (err) {
      console.error(`❌ Fout bij ophalen ${symbol}:`, err);
      setInternalError(copy.fetchError);
    } finally {
      setInternalLoading(false);
      isFetchingRef.current = false;
    }
  }

  if (loading && !asset) {
    return <MarketCardSkeleton />;
  }

  if (error || !asset) {
    return (
      <div className="w-full p-6 bg-red-50 rounded-2xl border border-red-100 text-red-600">
          <p className="font-bold flex items-center gap-2">
            <TrendingDown className="w-4 h-4" />
            {error || copy.unavailable}
          </p>
      </div>
    );
  }

  const priceChange = asset.change_24h || 0;
  const positive = priceChange >= 0;
  const changeColor = positive ? "text-green-600" : "text-red-600";
  const ChangeIcon = positive ? TrendingUp : TrendingDown;
  const formatTimestamp = (timestamp) =>
    timestamp
      ? new Date(timestamp).toLocaleTimeString(isDutch ? "nl-NL" : "en-US", {
          hour: "2-digit",
          minute: "2-digit",
        })
      : "–";

  return (
    <div className="card card-p hover:border-blue-600/30">
       <div className="flex items-center justify-between mb-10">
          <div className="flex items-center gap-3 text-blue-600">
             <Activity className="w-5 h-5" />
             <span className="text-[11px] font-black uppercase tracking-[0.2em]">{copy.livePrice}</span>
          </div>
          <div suppressHydrationWarning className="flex items-center gap-1.5 text-[10px] font-bold text-slate-400">
             <Clock size={12} className="opacity-50" />
             {formatTimestamp(asset.timestamp)}
          </div>
       </div>

       <div className="flex flex-col md:flex-row md:items-end justify-between gap-8">
          <div>
             <span className="metric-label">{copy.currentPrice}</span>
             <h2 suppressHydrationWarning className="metric-value text-5xl font-mono !tracking-tighter">
                ${Number(asset.price || 0).toLocaleString(undefined, { 
                  minimumFractionDigits: 2,
                  maximumFractionDigits: symbol === 'BTC' ? 2 : 4 
                })}
             </h2>
              <div className={`flex items-center gap-2 mt-4 font-black ${changeColor}`}>
                <ChangeIcon size={18} />
                <span className="text-lg">{positive ? "+" : ""}{Number(priceChange).toFixed(2)}%</span>
                <span className="text-[10px] uppercase tracking-widest text-secondary opacity-60 ml-1 sm:ml-2">{copy.change24h}</span>
              </div>
          </div>

          <div className="flex items-center gap-8 border-t md:border-t-0 md:border-l-2 border-slate-100 pt-6 md:pt-0 md:pl-8">
             <div className="flex flex-col">
                <span className="metric-label">{copy.volume24h}</span>
                <span className="text-lg font-black text-slate-900">${formatNumber(asset.volume)}</span>
             </div>
          </div>
       </div>
    </div>
  );
}
