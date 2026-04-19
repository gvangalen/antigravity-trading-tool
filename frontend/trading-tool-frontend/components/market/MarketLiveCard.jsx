"use client";

import { useEffect, useState } from "react";
import CardWrapper from "@/components/ui/CardWrapper";
import { formatChange, formatNumber } from "@/components/market/utils";
import { fetchLatestBTC } from "@/lib/api/market";
import { MarketCardSkeleton } from "@/components/dashboard/DashboardSkeleton";

// Lucide icons
import {
  Bitcoin,
  TrendingUp,
  TrendingDown,
  BarChart3,
  Loader2,
  Clock,
} from "lucide-react";

export default function MarketLiveCard({ data = null, loading: propLoading = false, error: propError = "" }) {
  const [internalBtc, setInternalBtc] = useState(null);
  const [internalLoading, setInternalLoading] = useState(true);
  const [internalError, setInternalError] = useState("");

  const btc = data || internalBtc;
  const loading = propLoading || (data ? false : internalLoading);
  const error = propError || (data ? "" : internalError);

  useEffect(() => {
    if (!data) {
      loadData();
      const interval = setInterval(loadData, 60000);
      return () => clearInterval(interval);
    }
  }, [data]);

  async function loadData() {
    setInternalLoading(true);
    try {
      const resp = await fetchLatestBTC();
      setInternalBtc(resp);
      setInternalError("");
      
      // 📳 Haptic feedback on success
      import("@/lib/haptics").then(({ hapticFeedback }) => {
        hapticFeedback.impact();
      });

    } catch (err) {
      console.error("❌ Fout bij ophalen BTC:", err);
      setInternalError("Fout bij ophalen BTC-data");
    } finally {
      setInternalLoading(false);
    }
  }

  // -------------------------
  // LOADING
  // -------------------------
  if (loading && !btc) {
    return <MarketCardSkeleton />;
  }

  // -------------------------
  // ERROR
  // -------------------------
  if (error || !btc) {
    return (
      <div className="w-full p-6 bg-red-50 rounded-2xl border border-red-100 text-red-600">
          <p className="font-bold flex items-center gap-2">
            <TrendingDown className="w-4 h-4" />
            {error || "Geen BTC data beschikbaar"}
          </p>
      </div>
    );
  }

  // -------------------------
  // PRICE COLOR
  // -------------------------
  const priceChange = btc.change_24h || 0;
  const positive = priceChange >= 0;

  const changeColor = positive
    ? "text-green-600"
    : "text-red-600";

  const ChangeIcon = positive ? TrendingUp : TrendingDown;

  return (
    <div className="card card-p hover:border-blue-600/30">
       <div className="flex items-center justify-between mb-10">
          <div className="flex items-center gap-3 text-blue-600">
             <Bitcoin className="w-5 h-5" />
             <span className="text-[11px] font-black uppercase tracking-[0.2em]">Live BTC Koers</span>
          </div>
          <div className="flex items-center gap-1.5 text-[10px] font-bold text-slate-400">
             <Clock size={12} className="opacity-50" />
             {btc.timestamp ? new Date(btc.timestamp).toLocaleTimeString() : "–"}
          </div>
       </div>

       <div className="flex flex-col md:flex-row md:items-end justify-between gap-8">
          <div>
             <span className="metric-label">Huidige Koers (USD)</span>
             <h2 className="metric-value text-5xl font-mono !tracking-tighter">
                ${Number(btc.price || 0).toLocaleString(undefined, { minimumFractionDigits: 2 })}
             </h2>
              <div className={`flex items-center gap-2 mt-4 font-black ${changeColor}`}>
                <ChangeIcon size={18} />
                <span className="text-lg">{positive ? "+" : ""}{Number(priceChange).toFixed(2)}%</span>
                <span className="text-[10px] uppercase tracking-widest text-secondary opacity-60 ml-1 sm:ml-2">24u Change</span>
              </div>
          </div>

          <div className="flex items-center gap-8 border-t md:border-t-0 md:border-l-2 border-slate-100 pt-6 md:pt-0 md:pl-8">
             <div className="flex flex-col">
                <span className="metric-label">24u Volume</span>
                <span className="text-lg font-black text-slate-900">${formatNumber(btc.volume)}</span>
             </div>
          </div>
       </div>
    </div>
  );
}
