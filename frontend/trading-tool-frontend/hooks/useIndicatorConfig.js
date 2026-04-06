'use client';

import { useState, useEffect } from "react";
import {
  getIndicatorConfig,
  updateIndicatorSettings,
  saveCustomRules,
  resetIndicatorConfig,
} from "@/lib/api/indicatorConfig";

export default function useIndicatorConfig(category, indicator) {
  const [config, setConfig] = useState(null);
  const [loading, setLoading] = useState(true);

  async function load() {
    setLoading(true);
    const data = await getIndicatorConfig(category, indicator);
    setConfig(data);
    setLoading(false);
  }

  useEffect(() => {
    if (category && indicator) load();
  }, [category, indicator]);

  async function save(settings) {
    await updateIndicatorSettings({
      category,
      indicator,
      ...settings,
    });
    await load();
  }

  async function saveCustom(rules) {
    await saveCustomRules({
      category,
      indicator,
      rules,
    });
    await load();
  }

  async function reset() {
    await resetIndicatorConfig(category, indicator);
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
