"use client";

import { useState, useRef } from "react";
import { fetchAuth } from "@/lib/api/auth";
import { useVisibilityPolling } from "@/hooks/useVisibilityPolling";

// ⭐ JULLIE STANDAARD
import { useModal } from "@/components/modal/ModalProvider";
import { useActiveSetup } from "@/app/providers/SetupProvider";

// Lucide Icons
import {
  TrendingUp,
  TrendingDown,
  Layers,
  Brain,
  Filter,
} from "lucide-react";

export default function TopSetupsMini() {
  const { showSnackbar } = useModal();
  const { setActiveSetup } = useActiveSetup();

  const [topSetups, setTopSetups] = useState([]);
  const [loading, setLoading] = useState(true);
  const [trendFilter, setTrendFilter] = useState("all");
  const [lastUpdated, setLastUpdated] = useState(null);
  const loadingRef = useRef(false);

  /* -------------------------------------------------------------
     🔄 Data ophalen
  ------------------------------------------------------------- */
  async function loadTopSetups({ silent = false } = {}) {
    if (loadingRef.current) return;
    loadingRef.current = true;
    try {
      if (!silent) setLoading(true);

      let data;

      // ⭐ Eerst top-endpoint proberen
      try {
        data = await fetchAuth(`/api/setups/top?limit=10`, { method: "GET" });
      } catch (err) {
        console.warn("⚠️ Top endpoint faalt, fallback naar /setups", err);
        data = await fetchAuth(`/api/setups`, { method: "GET" });
      }

      const setups = Array.isArray(data)
        ? data
        : Array.isArray(data?.setups)
        ? data.setups
        : [];

      const sorted = setups
        .filter((s) => typeof s.score === "number")
        .sort((a, b) => b.score - a.score)
        .slice(0, 10);

      setTopSetups(sorted);
      setLastUpdated(new Date());
    } catch (error) {
      console.error("❌ Fout bij laden setups:", error);
      showSnackbar("Top-setups laden mislukt", "danger");
      setTopSetups([]);
    } finally {
      setLoading(false);
      loadingRef.current = false;
    }
  }

  useVisibilityPolling(() => loadTopSetups({ silent: true }), {
    intervalMs: 60000,
    backgroundIntervalMs: 180000,
    runImmediately: true,
    deps: [],
  });

  /* -------------------------------------------------------------
     🎚 Filter
  ------------------------------------------------------------- */
  const filteredSetups = topSetups
    .filter((s) => trendFilter === "all" || s.trend === trendFilter)
    .slice(0, 3);

  /* -------------------------------------------------------------
     📡 Loading / Empty states
  ------------------------------------------------------------- */
  if (loading) {
    return (
      <div className="text-[var(--text-light)] text-sm text-center py-4">
        📡 Setups laden...
      </div>
    );
  }

  if (topSetups.length === 0) {
    return (
      <div className="text-[var(--text-light)] text-sm text-center py-4">
        ⚠️ Geen actieve setups gevonden.
      </div>
    );
  }

  /* -------------------------------------------------------------
     📊 Trend icons
  ------------------------------------------------------------- */
  const trendIcon = (trend) => {
    switch (trend) {
      case "bullish":
        return <TrendingUp size={14} className="text-green-600" />;
      case "bearish":
        return <TrendingDown size={14} className="text-red-600" />;
      default:
        return <Layers size={14} className="text-yellow-600" />;
    }
  };

  /* -------------------------------------------------------------
     🧠 Component
  ------------------------------------------------------------- */
  return (
    <div className="space-y-4 text-sm">
      {/* Header */}
      <div className="flex items-center justify-between">
        <h4 className="font-semibold text-[var(--text-dark)] flex items-center gap-2">
          <Brain size={16} className="text-[var(--primary-dark)]" />
          Top Setups
        </h4>

        {lastUpdated && (
          <span className="text-xs text-[var(--text-light)] italic">
            {lastUpdated.toLocaleTimeString()}
          </span>
        )}
      </div>

      {/* Filter dropdown */}
      <div className="flex items-center gap-2">
        <Filter size={14} className="text-[var(--text-light)]" />
        <select
          value={trendFilter}
          onChange={(e) => setTrendFilter(e.target.value)}
          className="
            text-xs px-2 py-1 rounded-lg border border-[var(--border)]
            bg-[var(--bg-soft)]
            text-[var(--text-dark)]
            focus:ring-1 focus:ring-[var(--primary)]
            cursor-pointer
          "
        >
          <option value="all">Alle trends</option>
          <option value="bullish">Bullish</option>
          <option value="bearish">Bearish</option>
          <option value="neutral">Neutraal</option>
        </select>
      </div>

      {/* Setup lijst */}
      <ul className="space-y-2">
        {filteredSetups.length === 0 ? (
          <p className="text-[var(--text-light)] text-sm italic">
            Geen setups voor deze trend.
          </p>
        ) : (
          filteredSetups.map((setup) => (
            <li
              key={setup.id}
              onClick={() => setActiveSetup(setup)}
              className="
                bg-[var(--bg-soft)] hover:bg-white 
                border border-[var(--border)] hover:border-[var(--primary)]
                rounded-xl px-3 py-2 flex items-center justify-between
                transition-all shadow-sm cursor-pointer
              "
            >
              <div className="flex items-center gap-2">
                {trendIcon(setup.trend)}

                <div>
                  <span className="font-semibold text-[var(--text-dark)]">
                    {setup.name}
                  </span>

                  {/* ✅ FIX: geen indicators meer */}
                  <span className="ml-2 text-xs text-[var(--text-light)]">
                    {setup.symbol || "-"} · {setup.timeframe || "-"}
                  </span>
                </div>
              </div>

              {/* ✅ FIX: geen decimals */}
              <span className="font-semibold text-[var(--text-dark)]">
                {Math.round(setup.score ?? 0)}
              </span>
            </li>
          ))
        )}
      </ul>
    </div>
  );
}
