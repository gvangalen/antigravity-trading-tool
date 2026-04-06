"use client";

import { useEffect, useState } from "react";
import { fetchDailySetupScores } from "@/lib/api/setups";

export function useDailySetupScores() {
  const [dailySetups, setDailySetups] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    load();
  }, []);

  async function load() {
    setLoading(true);
    try {
      const data = await fetchDailySetupScores();
      setDailySetups(Array.isArray(data) ? data : []);
    } catch (e) {
      console.error("❌ daily setup scores error", e);
      setDailySetups([]);
    } finally {
      setLoading(false);
    }
  }

  return {
    dailySetups,
    loading,
  };
}
