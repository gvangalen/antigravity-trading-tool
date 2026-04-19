'use client';

import { useMarketData } from '@/hooks/useMarketData';
import MarketLiveCard from '@/components/market/MarketLiveCard';
import MarketSevenDayTable from '@/components/market/MarketSevenDayTable';

export default function MarketSummaryForDashboard({ sevenDayData = [], loading = false }) {
  return (
    <div className="space-y-4">
      <MarketSevenDayTable history={sevenDayData} loading={loading} />
    </div>
  );
}
