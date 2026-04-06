'use client';

import { useMarketData } from '@/hooks/useMarketData';
import MarketLiveCard from '@/components/market/MarketLiveCard';
import MarketSevenDayTable from '@/components/market/MarketSevenDayTable';

export default function MarketSummaryForDashboard() {
  const { sevenDayData, btcLive } = useMarketData();

  return (
    <div className="space-y-4">
      <MarketSevenDayTable history={sevenDayData} />
    </div>
  );
}
