'use client';

import { useEffect, useState } from "react";
import { TrendingUp } from "lucide-react";
import CardWrapper from "@/components/ui/CardWrapper";
import CardLoader from "@/components/ui/CardLoader";
import { fetchLastSetup } from "@/lib/api/setups";
import AIInsightBlock from "@/components/ui/AIInsightBlock";

export default function ActiveSetupCard() {
  const [setup, setSetup] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function load() {
      try {
        const data = await fetchLastSetup();
        setSetup(data || null);
      } catch (err) {
        console.error("❌ ActiveSetupCard error:", err);
      } finally {
        setLoading(false);
      }
    }
    load();
  }, []);

  const trend = setup?.trend?.toLowerCase() || "neutral";

  const TREND_TEXT = {
    bullish: "Deze setup is bullish en momenteel actief.",
    bearish: "Deze setup is bearish en vereist extra voorzichtigheid.",
    neutral: "Deze setup is actief, maar de trend is neutraal.",
  };

  return (
    <CardWrapper
      title="Actieve Setup"
      icon={<TrendingUp className="w-4 h-4 text-[var(--primary)]" />}
    >
      <div className="flex flex-col gap-4 min-h-[220px] text-sm">

        {loading && <CardLoader text="Setup laden…" />}

        {!loading && !setup && (
          <p className="italic text-[var(--text-light)]">Geen actieve setup gevonden.</p>
        )}

        {!loading && setup && (
          <>
            <div className="space-y-[3px] text-[var(--text-dark)]">
              <p><strong>Naam:</strong> {setup.name}</p>
              <p><strong>Trend:</strong> {setup.trend}</p>
              <p><strong>Timeframe:</strong> {setup.timeframe}</p>
              <p><strong>Type:</strong> {setup.strategy_type}</p>
              <p><strong>Asset:</strong> {setup.symbol}</p>
            </div>

            <AIInsightBlock text={TREND_TEXT[trend]} variant="dashboard" />
          </>
        )}

      </div>
    </CardWrapper>
  );
}
