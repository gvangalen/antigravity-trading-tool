'use client';

import { fetchAuth } from '@/lib/api/auth';

/**
 * 🟢 Dagrapport samenvatting (AUTH verplicht)
 *
 * Gebruikt in:
 *  - Dashboard sidebar
 *  - Daily widgets
 */
export const fetchDailyReportSummary = async () => {
  try {
    const res = await fetchAuth('/api/report/daily/latest');

    // backend returnt volledige report → we pakken summary veld
    if (res?.summary) {
      return { summary: res.summary };
    }

    return { summary: "Geen samenvatting beschikbaar." };

  } catch (e) {
    console.error("❌ [fetchDailyReportSummary] Error:", e);
    return { summary: "Geen samenvatting beschikbaar." };
  }
};
