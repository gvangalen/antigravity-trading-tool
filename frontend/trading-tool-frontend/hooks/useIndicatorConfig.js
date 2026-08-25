'use client';

import { useState, useEffect } from "react";
import {
  getIndicatorConfig,
  updateIndicatorSettings,
  saveCustomRules,
  resetIndicatorConfig,
} from "@/lib/api/indicatorConfig";

export default function useIndicatorConfig(category, indicator, symbol) {
  const [config, setConfig] = useState(null);
  const [loading, setLoading] = useState(true);

  async function load() {
    setLoading(true);
    const data = await getIndicatorConfig(category, indicator, symbol);
    setConfig(data);
    setLoading(false);
  }

  useEffect(() => {
    if (category && indicator && symbol) load();
  }, [category, indicator, symbol]);

  async function save(settings) {
    await updateIndicatorSettings({
      category,
      indicator,
      symbol,
      ...settings,
    });
    await load();
  }

  async function saveCustom(rules) {
    await saveCustomRules({
      category,
      indicator,
      symbol,
      rules,
    });
    await load();
  }

  async function reset() {
    await resetIndicatorConfig(category, indicator, symbol);
    await load();
  }

  return {
    config,
    loading,
    save,
    saveCustom,
    reset,
  };
}
