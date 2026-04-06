"use client";

import { useEffect, useMemo, useState, useCallback } from "react";
import IndicatorScoreEditor from "./IndicatorScoreEditor";
import { useModal } from "@/components/modal/ModalProvider";

import {
  getIndicatorConfig,
  updateIndicatorSettings,
  saveCustomRules as apiSaveCustomRules,
} from "@/lib/api/indicatorConfig";

/* --------------------------------------------------
  Keep normalize consistent with backend + editor
-------------------------------------------------- */
const NAME_ALIASES = {
  fear_and_greed_index: "fear_greed_index",
  fear_greed: "fear_greed_index",
  sandp500: "sp500",
  "s&p500": "sp500",
  "s&p_500": "sp500",
  sp_500: "sp500",
};

function normalizeIndicatorName(name) {
  const normalized = String(name || "")
    .toLowerCase()
    .replace(/&/g, "and")
    .replace(/s&p/g, "sp")
    .replace(/\s+/g, "_")
    .replace(/-+/g, "_")
    .trim();

  return NAME_ALIASES[normalized] || normalized;
}

export default function IndicatorScorePanel({ indicator, category }) {
  const { showSnackbar } = useModal();

  const normalizedIndicator = useMemo(
    () => normalizeIndicatorName(indicator),
    [indicator]
  );

  const [config, setConfig] = useState(null);
  const [loading, setLoading] = useState(true);
  const [errorMsg, setErrorMsg] = useState("");

  /* ---------------------------
     Load indicator config
  --------------------------- */
  const loadConfig = useCallback(async () => {
    if (!normalizedIndicator || !category) return;

    setLoading(true);
    setErrorMsg("");

    try {
      const res = await getIndicatorConfig(category, normalizedIndicator);

      setConfig({
        rules: Array.isArray(res?.rules) ? res.rules : [],
        score_mode: res?.score_mode || "standard",
        weight: typeof res?.weight === "number" ? res.weight : 1,
      });
    } catch (e) {
      console.error("Failed loading config", e);

      // ✅ voorkom dat je voor altijd op "Laden…" blijft
      setConfig({
        rules: [],
        score_mode: "standard",
        weight: 1,
      });

      const msg =
        e?.message ||
        "Config laden mislukt. Check API / indicator key / backend logs.";

      setErrorMsg(msg);
      showSnackbar("Kon score-config niet laden", "danger");
    } finally {
      setLoading(false);
    }
  }, [category, normalizedIndicator, showSnackbar]);

  useEffect(() => {
    loadConfig();
  }, [loadConfig]);

  /* ---------------------------
     Save STANDARD / CONTRARIAN
     (mode + weight)

     ✅ Update: support silent autosave from Editor
        Editor can call:
        onSave({ ..., __silent: true })
  --------------------------- */
  const saveSettings = useCallback(
    async (settings) => {
      try {
        const nextMode = settings?.score_mode ?? "standard";
        const nextWeight =
          typeof settings?.weight === "number" ? settings.weight : 1;

        await updateIndicatorSettings({
          category,
          indicator: normalizedIndicator,
          score_mode: nextMode,
          weight: nextWeight,
        });

        setConfig((prev) => ({
          ...(prev || {}),
          score_mode: nextMode,
          weight: nextWeight,
        }));

        // ✅ only show snackbar if not silent
        if (!settings?.__silent) {
          showSnackbar("Instellingen opgeslagen", "success");
        }
      } catch (e) {
        console.error("Save failed", e);
        showSnackbar("Opslaan mislukt", "danger");
      }
    },
    [category, normalizedIndicator, showSnackbar]
  );

  /* ---------------------------
     Save CUSTOM RULES + WEIGHT

     ✅ Editor moet aanroepen:
        onSaveCustom(payload, localWeight)

     payload = [{indicator, category, range_min, range_max, score, trend}, ...]
  --------------------------- */
  const saveCustom = useCallback(
    async (payload, weightFromEditor) => {
      try {
        const rulesOnly = Array.isArray(payload) ? payload : [];
        const nextWeight =
          typeof weightFromEditor === "number" ? weightFromEditor : 1;

        // 1) save rules
        await apiSaveCustomRules({
          category,
          indicator: normalizedIndicator,
          rules: rulesOnly,
        });

        // 2) save mode + weight
        await updateIndicatorSettings({
          category,
          indicator: normalizedIndicator,
          score_mode: "custom",
          weight: nextWeight,
        });

        setConfig((prev) => ({
          ...(prev || {}),
          rules: rulesOnly,
          score_mode: "custom",
          weight: nextWeight,
        }));

        showSnackbar("Custom rules opgeslagen", "success");
      } catch (e) {
        console.error("Custom save failed", e);
        showSnackbar("Custom opslaan mislukt", "danger");
      }
    },
    [category, normalizedIndicator, showSnackbar]
  );

  /* ---------------------------
     UI states
  --------------------------- */
  if (loading) {
    return <div className="p-6 text-sm text-[var(--text-light)]">Laden…</div>;
  }

  if (!config) {
    return (
      <div className="p-6 text-sm text-[var(--text-light)]">
        Kon config niet initialiseren.
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {errorMsg ? (
        <div className="card-surface p-4 text-sm">
          <div className="font-semibold text-[var(--text-dark)]">
            Laden mislukt
          </div>
          <div className="mt-1 text-[var(--text-light)]">{errorMsg}</div>

          <button onClick={loadConfig} className="btn-secondary mt-3">
            Opnieuw proberen
          </button>
        </div>
      ) : null}

      <IndicatorScoreEditor
        indicator={normalizedIndicator}
        category={category}
        rules={config.rules}
        scoreMode={config.score_mode}
        weight={config.weight}
        loading={false}
        onSave={saveSettings}
        onSaveCustom={saveCustom}
      />
    </div>
  );
}
