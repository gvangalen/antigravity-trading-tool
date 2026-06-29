'use client';

import { useEffect, useState } from "react";
import { TrendingUp } from "lucide-react";
import CardWrapper from "@/components/ui/CardWrapper";
import CardLoader from "@/components/ui/CardLoader";
import { fetchLastSetup } from "@/lib/api/setups";
import AIInsightBlock from "@/components/ui/AIInsightBlock";
import { useTranslation } from "@/app/providers/I18nProvider";

export default function ActiveSetupCard() {
  const { t } = useTranslation();
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
    bullish: t?.dashboard?.cards?.setupBullish,
    bearish: t?.dashboard?.cards?.setupBearish,
    neutral: t?.dashboard?.cards?.setupNeutral,
  };

  return (
    <CardWrapper
      title={t?.dashboard?.cards?.setup}
      icon={<TrendingUp className="w-4 h-4 text-[var(--primary)]" />}
    >
      <div className="flex flex-col gap-4 min-h-[220px] text-sm">

        {loading && <CardLoader text={t?.dashboard?.cards?.loading_setup} />}

        {!loading && !setup && (
          <p className="italic text-[var(--text-light)]">{t?.dashboard?.cards?.no_setup}</p>
        )}

        {!loading && setup && (
          <>
            <div className="space-y-[3px] text-[var(--text-dark)]">
              <p><strong>{t?.common?.name}:</strong> {setup.name}</p>
              <p><strong>{t?.common?.trend}:</strong> {setup.trend}</p>
              <p><strong>{t?.dashboard?.brain?.timeframe}:</strong> {setup.timeframe}</p>
              <p><strong>{t?.common?.type}:</strong> {setup.strategy_type}</p>
              <p><strong>{t?.common?.asset}:</strong> {setup.symbol}</p>
            </div>

            <AIInsightBlock text={TREND_TEXT[trend]} variant="dashboard" />
          </>
        )}

      </div>
    </CardWrapper>
  );
}
