"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { createPortal } from "react-dom";
import {
  CheckCircle2,
  ChevronDown,
  ChevronUp,
  SlidersHorizontal,
  Sparkles,
  X,
} from "lucide-react";

import IndicatorScoreEditor from "@/components/scoring/IndicatorScoreEditor";
import { useModal } from "@/components/modal/ModalProvider";
import {
  getIndicatorConfig,
  saveCustomRules,
  updateIndicatorSettings,
} from "@/lib/api/indicatorConfig";
import { getAssistantPreferences } from "@/lib/api/ai";
import { normalizeTraderProfilePreferences } from "@/lib/traderProfileOptions";

const NAME_ALIASES = {
  fear_and_greed_index: "fear_greed_index",
  fear_greed: "fear_greed_index",
  sandp500: "sp500",
  "s&p500": "sp500",
  "s&p_500": "sp500",
  sp_500: "sp500",
};

const DEFAULT_RULES = [
  { range_min: 0, range_max: 20, score: 10, trend: "veryLow" },
  { range_min: 20, range_max: 40, score: 25, trend: "low" },
  { range_min: 40, range_max: 60, score: 50, trend: "neutral" },
  { range_min: 60, range_max: 80, score: 75, trend: "active" },
  { range_min: 80, range_max: 100, score: 100, trend: "high" },
];

const SIMPLE_WEIGHT_OPTIONS = [
  { id: "low", label: "Laag", value: 0.6 },
  { id: "normal", label: "Normaal", value: 1 },
  { id: "high", label: "Hoog", value: 2 },
];

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

function getCategoryLabel(category) {
  if (category === "technical") return "Technical";
  if (category === "macro") return "Macro";
  if (category === "market") return "Market";
  return "Indicator";
}

function getIndicatorLabel(indicator) {
  const label = String(indicator || "").replace(/_/g, " ").trim();
  if (!label) return "Indicator";
  return label
    .split(" ")
    .map((part) => (part.length <= 3 ? part.toUpperCase() : part.charAt(0).toUpperCase() + part.slice(1)))
    .join(" ");
}

function normalizeDraft(category, indicator, config = {}) {
  const normalizedIndicator = normalizeIndicatorName(indicator);
  const rules = Array.isArray(config?.rules) && config.rules.length > 0
    ? config.rules
    : DEFAULT_RULES;

  return {
    indicator: normalizedIndicator,
    category,
    score_mode: config?.score_mode || "standard",
    weight: typeof config?.weight === "number" ? config.weight : 1,
    rules: rules.map((rule, index) => ({
      indicator: normalizedIndicator,
      category,
      range_min: Number(rule?.range_min ?? DEFAULT_RULES[index]?.range_min ?? 0),
      range_max: Number(rule?.range_max ?? DEFAULT_RULES[index]?.range_max ?? 20),
      score: Number(rule?.score ?? DEFAULT_RULES[index]?.score ?? 50),
      trend: rule?.trend || DEFAULT_RULES[index]?.trend || "neutral",
    })),
  };
}

function getWeightOptionFromValue(value) {
  const next = typeof value === "number" ? value : 1;
  const distances = SIMPLE_WEIGHT_OPTIONS.map((option) => ({
    option,
    distance: Math.abs(option.value - next),
  })).sort((a, b) => a.distance - b.distance);

  return distances[0]?.option || SIMPLE_WEIGHT_OPTIONS[1];
}

function configsMatch(a, b) {
  if (!a || !b) return false;
  if ((a.score_mode || "standard") !== (b.score_mode || "standard")) return false;
  if (Math.abs((a.weight || 1) - (b.weight || 1)) > 0.05) return false;

  const aRules = Array.isArray(a.rules) ? a.rules : [];
  const bRules = Array.isArray(b.rules) ? b.rules : [];
  if (aRules.length !== bRules.length) return false;

  return aRules.every((rule, index) => {
    const compare = bRules[index];
    return (
      Number(rule?.range_min) === Number(compare?.range_min) &&
      Number(rule?.range_max) === Number(compare?.range_max) &&
      Number(rule?.score) === Number(compare?.score)
    );
  });
}

function buildProfileContext(preferences = {}) {
  const profile = normalizeTraderProfilePreferences(preferences);
  const traderTypes = Array.isArray(profile.trader_types) ? profile.trader_types : [];
  const timeframes = Array.isArray(profile.primary_timeframes) ? profile.primary_timeframes : [];
  const riskProfiles = Array.isArray(profile.risk_profiles) ? profile.risk_profiles : [];
  const goals = Array.isArray(profile.investment_goals_list) ? profile.investment_goals_list : [];

  const primaryTraderType = traderTypes[0] || "";
  const primaryRisk = riskProfiles[0] || "";
  const summarySegments = [];

  if (primaryTraderType === "swing_trader") summarySegments.push("jouw swingprofiel");
  else if (primaryTraderType === "day_trader") summarySegments.push("jouw daytrading-profiel");
  else if (primaryTraderType === "scalper") summarySegments.push("jouw scalping-profiel");
  else if (primaryTraderType === "investor" || primaryTraderType === "dca_investor") summarySegments.push("jouw investeringsprofiel");

  if (timeframes.length > 0) {
    summarySegments.push(`op ${timeframes.map((value) => value.toUpperCase()).join(" en ")}`);
  }

  return {
    traderTypes,
    timeframes,
    riskProfiles,
    goals,
    primaryTraderType,
    primaryRisk,
    summaryText: summarySegments.join(" ") || "deze workflow",
  };
}

function getPresetLibrary(category, indicator, profileContext) {
  const normalizedIndicator = normalizeIndicatorName(indicator);
  const summarySuffix = profileContext?.summaryText || "deze workflow";

  const genericIntro =
    category === "technical"
      ? "Kies eerst hoe FINN deze indicator moet meenemen in je technische routine."
      : `Kies eerst hoe FINN deze ${getCategoryLabel(category).toLowerCase()}-indicator moet meenemen.`;

  const genericPresets = [
    {
      id: "default",
      label: "Standaard interpreteren",
      help: "FINN leest deze indicator op de gebruikelijke manier.",
      score_mode: "standard",
      defaultWeightId: "normal",
      summaryTemplate: (weightLabel) => `FINN gebruikt ${getIndicatorLabel(indicator)} op de standaardmanier met ${weightLabel.toLowerCase()} invloed.`,
      recommendationReason: `Aanbevolen als veilige start voor ${summarySuffix}.`,
    },
    {
      id: "contrarian",
      label: "Tegendraads lezen",
      help: "FINN draait hoge en lage waardes om voor een meer contrair signaal.",
      score_mode: "contrarian",
      defaultWeightId: "normal",
      summaryTemplate: (weightLabel) => `FINN leest ${getIndicatorLabel(indicator)} contrair met ${weightLabel.toLowerCase()} invloed.`,
      recommendationReason: `Handig wanneer je vooral extremen wilt benutten binnen ${summarySuffix}.`,
    },
  ];

  if (category !== "technical") {
    return {
      description: genericIntro,
      presets: genericPresets,
    };
  }

  if (normalizedIndicator === "rsi") {
    const recommendedId =
      profileContext?.primaryTraderType === "day_trader" || profileContext?.primaryTraderType === "scalper"
        ? "trend_strength"
        : "oversold_reversal";

    return {
      description: "RSI laat zien of momentum afkoelt of juist doorzet. Zo kan FINN beter kiezen of hij op uitputting of trendsterkte moet letten.",
      presets: [
        {
          id: "oversold_reversal",
          label: "Oververkocht kopen",
          help: "Gebruik RSI vooral om zwakke fases en mogelijke rebounds te herkennen.",
          score_mode: "contrarian",
          defaultWeightId: "normal",
          summaryTemplate: (weightLabel) => `FINN gebruikt RSI als oversold-signaal met ${weightLabel.toLowerCase()} invloed.`,
          recommendationReason: `Aanbevolen voor ${summarySuffix}.`,
          recommended: recommendedId === "oversold_reversal",
        },
        {
          id: "trend_strength",
          label: "Trendsterkte volgen",
          help: "Gebruik RSI vooral als bevestiging dat momentum mee- of tegenzit.",
          score_mode: "standard",
          defaultWeightId: "normal",
          summaryTemplate: (weightLabel) => `FINN gebruikt RSI als trendbevestiging met ${weightLabel.toLowerCase()} invloed.`,
          recommendationReason: `Aanbevolen wanneer je sneller op momentum wilt reageren binnen ${summarySuffix}.`,
          recommended: recommendedId === "trend_strength",
        },
      ],
    };
  }

  if (normalizedIndicator === "ma_200") {
    const recommendedId =
      profileContext?.primaryTraderType === "day_trader" || profileContext?.primaryTraderType === "scalper"
        ? "confirmation_only"
        : "trend_filter";

    return {
      description: "MA 200 helpt FINN zien of de grotere trend mee- of tegenwerkt. Zo voorkom je dat een klein signaal te veel gewicht krijgt.",
      presets: [
        {
          id: "trend_filter",
          label: "Trend volgen",
          help: "Gebruik MA 200 als stevige trendfilter voor richting en bias.",
          score_mode: "standard",
          defaultWeightId: "normal",
          summaryTemplate: (weightLabel) => `FINN gebruikt MA 200 als trendfilter met ${weightLabel.toLowerCase()} invloed.`,
          recommendationReason: `Aanbevolen voor ${summarySuffix}.`,
          recommended: recommendedId === "trend_filter",
        },
        {
          id: "confirmation_only",
          label: "Alleen als bevestiging gebruiken",
          help: "Gebruik MA 200 lichter, vooral om andere signalen te bevestigen.",
          score_mode: "standard",
          defaultWeightId: "low",
          summaryTemplate: (weightLabel) => `FINN gebruikt MA 200 als extra bevestiging met ${weightLabel.toLowerCase()} invloed.`,
          recommendationReason: `Aanbevolen wanneer je korter handelt en MA 200 niet alles wilt laten domineren.`,
          recommended: recommendedId === "confirmation_only",
        },
      ],
    };
  }

  return {
    description: genericIntro,
    presets: genericPresets,
  };
}

function buildPresetDraft(preset, category, indicator, currentDraft) {
  const weightOption =
    SIMPLE_WEIGHT_OPTIONS.find((option) => option.id === preset.defaultWeightId) || SIMPLE_WEIGHT_OPTIONS[1];

  return {
    ...(currentDraft || normalizeDraft(category, indicator)),
    score_mode: preset.score_mode || "standard",
    weight: weightOption.value,
    rules:
      preset.score_mode === "custom" && Array.isArray(preset.rules) && preset.rules.length > 0
        ? preset.rules.map((rule) => ({ ...rule }))
        : (currentDraft?.rules || normalizeDraft(category, indicator).rules).map((rule) => ({ ...rule })),
  };
}

function derivePresetState(draft, presets) {
  const matches = presets.find((preset) => configsMatch(draft, buildPresetDraft(preset, draft?.category, draft?.indicator, draft)));
  return matches?.id || "custom";
}

export default function IndicatorConfigModal({
  isOpen,
  category,
  indicator,
  assetSymbol,
  mode = "add",
  onClose,
  onSubmitAction,
  onCompleted,
}) {
  const { showSnackbar } = useModal();
  const [draft, setDraft] = useState(null);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [mounted, setMounted] = useState(false);
  const [advancedOpen, setAdvancedOpen] = useState(false);
  const [profileContext, setProfileContext] = useState(buildProfileContext());

  const categoryLabel = useMemo(() => getCategoryLabel(category), [category]);
  const normalizedIndicator = useMemo(() => normalizeIndicatorName(indicator), [indicator]);
  const indicatorLabel = useMemo(() => getIndicatorLabel(indicator), [indicator]);
  const actionLabel = mode === "edit" ? "Opslaan" : `${indicatorLabel} toevoegen`;

  const presetLibrary = useMemo(
    () => getPresetLibrary(category, normalizedIndicator, profileContext),
    [category, normalizedIndicator, profileContext]
  );

  const presets = presetLibrary.presets || [];
  const recommendedPreset = useMemo(
    () => presets.find((preset) => preset.recommended) || presets[0] || null,
    [presets]
  );

  const selectedPresetId = useMemo(() => derivePresetState(draft, presets), [draft, presets]);
  const selectedPreset = useMemo(
    () => presets.find((preset) => preset.id === selectedPresetId) || null,
    [presets, selectedPresetId]
  );
  const selectedWeight = useMemo(() => getWeightOptionFromValue(draft?.weight), [draft?.weight]);

  const summaryText = useMemo(() => {
    if (!draft) return "";
    const presetForSummary =
      selectedPreset ||
      recommendedPreset || {
        summaryTemplate: (weightLabel) =>
          `FINN gebruikt ${indicatorLabel} met ${weightLabel.toLowerCase()} invloed.`,
      };

    return presetForSummary.summaryTemplate(selectedWeight.label);
  }, [draft, indicatorLabel, recommendedPreset, selectedPreset, selectedWeight.label]);

  const recommendationText = useMemo(() => {
    if (selectedPreset?.recommendationReason) return selectedPreset.recommendationReason;
    if (recommendedPreset?.recommendationReason) return recommendedPreset.recommendationReason;
    return `Aanbevolen als veilige start voor ${profileContext.summaryText || "deze workflow"}.`;
  }, [profileContext.summaryText, recommendedPreset, selectedPreset]);

  const isValidDraft = useMemo(() => {
    if (!draft) return false;
    if (!draft.score_mode) return false;
    if (!Number.isFinite(draft.weight)) return false;
    if (draft.score_mode === "custom") {
      return Array.isArray(draft.rules) && draft.rules.length > 0;
    }
    return true;
  }, [draft]);

  const handleDraftChange = useCallback((nextDraft) => {
    setDraft((prev) => ({
      ...(prev || {}),
      ...nextDraft,
      rules: Array.isArray(nextDraft?.rules) ? nextDraft.rules : prev?.rules || [],
    }));
  }, []);

  const handleSelectPreset = useCallback(
    (preset) => {
      if (!category || !normalizedIndicator) return;
      setDraft((currentDraft) => buildPresetDraft(preset, category, normalizedIndicator, currentDraft));
    },
    [category, normalizedIndicator]
  );

  const handleSelectWeight = useCallback((weightOption) => {
    setDraft((currentDraft) => {
      if (!currentDraft) return currentDraft;
      return {
        ...currentDraft,
        weight: weightOption.value,
      };
    });
  }, []);

  useEffect(() => {
    setMounted(true);
    return () => setMounted(false);
  }, []);

  useEffect(() => {
    if (!isOpen) return;

    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";

    return () => {
      document.body.style.overflow = previousOverflow;
    };
  }, [isOpen]);

  useEffect(() => {
    if (!isOpen || !category || !normalizedIndicator) return;

    let active = true;
    setLoading(true);
    setAdvancedOpen(false);

    Promise.all([
      getIndicatorConfig(category, normalizedIndicator),
      getAssistantPreferences().catch(() => null),
    ])
      .then(([configResponse, preferencesResponse]) => {
        if (!active) return;

        const normalizedDraft = normalizeDraft(category, normalizedIndicator, configResponse || {});
        const nextProfile = buildProfileContext(preferencesResponse?.preferences || preferencesResponse || {});
        const nextLibrary = getPresetLibrary(category, normalizedIndicator, nextProfile);
        const nextRecommended = nextLibrary.presets?.find((preset) => preset.recommended) || nextLibrary.presets?.[0] || null;

        setProfileContext(nextProfile);
        setDraft(normalizedDraft);

        if (!configResponse && nextRecommended) {
          setDraft(buildPresetDraft(nextRecommended, category, normalizedIndicator, normalizedDraft));
        }
      })
      .catch((error) => {
        if (!active) return;
        console.error("Failed to load indicator config modal:", error);
        setDraft(normalizeDraft(category, normalizedIndicator));
        showSnackbar(`Configuratie voor ${indicatorLabel} kon niet volledig geladen worden.`, "danger");
      })
      .finally(() => {
        if (active) {
          setLoading(false);
        }
      });

    return () => {
      active = false;
    };
  }, [category, indicatorLabel, isOpen, normalizedIndicator, showSnackbar]);

  const handleConfirm = useCallback(async () => {
    if (!indicator || !category || !draft || saving || !isValidDraft) return;

    setSaving(true);

    try {
      if (draft.score_mode === "custom") {
        await saveCustomRules({
          category,
          indicator,
          rules: Array.isArray(draft.rules) ? draft.rules : [],
        });
      }

      await updateIndicatorSettings({
        category,
        indicator,
        score_mode: draft.score_mode || "standard",
        weight: typeof draft.weight === "number" ? draft.weight : 1,
      });

      await onSubmitAction?.({
        indicator,
        category,
        assetSymbol,
        draft,
      });

      showSnackbar(
        mode === "edit"
          ? `${indicatorLabel} opgeslagen voor ${assetSymbol} ${categoryLabel}.`
          : `${indicatorLabel} toegevoegd aan ${assetSymbol} ${categoryLabel}.`,
        "success"
      );

      onCompleted?.({
        indicator,
        category,
        assetSymbol,
        draft,
      });

      onClose?.();
    } catch (error) {
      console.error("Failed to confirm indicator config modal:", error);
      showSnackbar(`Actie voor ${indicatorLabel} is mislukt.`, "danger");
    } finally {
      setSaving(false);
    }
  }, [
    assetSymbol,
    category,
    categoryLabel,
    draft,
    indicator,
    indicatorLabel,
    isValidDraft,
    mode,
    onClose,
    onCompleted,
    onSubmitAction,
    saving,
    showSnackbar,
  ]);

  if (!isOpen || !indicator || !category || !mounted) return null;

  return createPortal(
    <div className="fixed inset-0 z-[400] overflow-y-auto bg-slate-950/55 px-4 py-6 backdrop-blur-sm sm:px-6 sm:py-8">
      <div className="flex min-h-full items-center justify-center">
        <div className="relative flex max-h-[calc(100vh-3rem)] w-full max-w-5xl flex-col overflow-hidden rounded-[32px] border border-slate-200 bg-white shadow-[0_35px_120px_-35px_rgba(15,23,42,0.55)]">
          <button
            type="button"
            onClick={onClose}
            className="absolute right-5 top-5 z-10 rounded-2xl p-2 text-slate-400 transition hover:bg-slate-100 hover:text-slate-700"
          >
            <X size={20} />
          </button>

          <div className="border-b border-slate-100 px-6 py-6 sm:px-8">
            <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
              <div className="max-w-2xl">
                <div className="text-[10px] font-black uppercase tracking-[0.28em] text-blue-600">
                  Indicator Configuration
                </div>
                <h2 className="mt-2 text-3xl font-black tracking-tight text-slate-950">
                  {indicatorLabel}
                </h2>
                <p className="mt-3 text-sm font-medium leading-6 text-slate-500">
                  {presetLibrary.description}
                </p>
              </div>

              <div className="inline-flex items-center gap-2 self-start rounded-full border border-blue-100 bg-blue-50 px-3 py-1.5 text-[10px] font-black uppercase tracking-[0.22em] text-blue-600">
                <SlidersHorizontal size={12} />
                {categoryLabel} Configuration
              </div>
            </div>
          </div>

          <div className="flex-1 overflow-y-auto px-6 py-6 sm:px-8 sm:py-8">
            {loading || !draft ? (
              <div className="rounded-[28px] border border-slate-200 bg-slate-50 px-6 py-12 text-sm font-semibold text-slate-500">
                Configuratie laden...
              </div>
            ) : (
              <div className="space-y-6">
                <section className="rounded-[30px] border border-slate-200 bg-white p-6 shadow-sm">
                  <div className="flex items-start gap-4">
                    <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-2xl bg-blue-50 text-blue-600">
                      <Sparkles size={20} />
                    </div>
                    <div className="space-y-2">
                      <div className="text-[10px] font-black uppercase tracking-[0.22em] text-slate-400">
                        Aanbevolen voor jouw profiel
                      </div>
                      <div className="text-lg font-black text-slate-950">
                        {selectedPreset?.label || recommendedPreset?.label || "Standaard start"}
                      </div>
                      <p className="text-sm font-medium leading-6 text-slate-500">
                        {recommendationText}
                      </p>
                    </div>
                  </div>
                </section>

                <section className="rounded-[30px] border border-slate-200 bg-white p-6 shadow-sm">
                  <div className="text-[10px] font-black uppercase tracking-[0.22em] text-slate-400">
                    Hoe moet FINN deze indicator gebruiken?
                  </div>
                  <div className="mt-4 grid gap-3 lg:grid-cols-2">
                    {presets.map((preset) => {
                      const active = selectedPresetId === preset.id;
                      return (
                        <button
                          key={preset.id}
                          type="button"
                          onClick={() => handleSelectPreset(preset)}
                          className={`rounded-[24px] border px-5 py-4 text-left transition ${
                            active
                              ? "border-blue-200 bg-blue-50 shadow-sm"
                              : "border-slate-200 bg-white hover:border-slate-300 hover:bg-slate-50"
                          }`}
                        >
                          <div className="flex items-start justify-between gap-3">
                            <div>
                              <div className="text-base font-black text-slate-950">{preset.label}</div>
                              <div className="mt-2 text-sm font-medium leading-6 text-slate-500">
                                {preset.help}
                              </div>
                            </div>
                            <div
                              className={`mt-1 flex h-5 w-5 items-center justify-center rounded-full border ${
                                active ? "border-blue-600 bg-blue-600 text-white" : "border-slate-300 bg-white text-transparent"
                              }`}
                            >
                              <CheckCircle2 size={12} />
                            </div>
                          </div>
                        </button>
                      );
                    })}

                    {selectedPresetId === "custom" ? (
                      <div className="rounded-[24px] border border-amber-200 bg-amber-50 px-5 py-4">
                        <div className="text-base font-black text-slate-950">Aangepast</div>
                        <div className="mt-2 text-sm font-medium leading-6 text-slate-500">
                          Je geavanceerde instellingen wijken af van de standaard presets.
                        </div>
                      </div>
                    ) : null}
                  </div>
                </section>

                <section className="rounded-[30px] border border-slate-200 bg-white p-6 shadow-sm">
                  <div className="text-[10px] font-black uppercase tracking-[0.22em] text-slate-400">
                    Invloed
                  </div>
                  <div className="mt-4 flex flex-wrap gap-3">
                    {SIMPLE_WEIGHT_OPTIONS.map((option) => {
                      const active = selectedWeight.id === option.id;
                      return (
                        <button
                          key={option.id}
                          type="button"
                          onClick={() => handleSelectWeight(option)}
                          className={`rounded-full border px-5 py-3 text-sm font-black transition ${
                            active
                              ? "border-blue-200 bg-blue-50 text-blue-700"
                              : "border-slate-200 bg-white text-slate-600 hover:border-slate-300 hover:text-slate-900"
                          }`}
                        >
                          {option.label}
                        </button>
                      );
                    })}
                  </div>
                </section>

                <section className="rounded-[30px] border border-slate-200 bg-slate-50/80 p-6 shadow-sm">
                  <div className="text-[10px] font-black uppercase tracking-[0.22em] text-slate-400">
                    Samenvatting
                  </div>
                  <p className="mt-3 text-base font-semibold leading-7 text-slate-800">
                    {summaryText}
                  </p>
                </section>

                <section className="rounded-[30px] border border-slate-200 bg-white shadow-sm">
                  <button
                    type="button"
                    onClick={() => setAdvancedOpen((current) => !current)}
                    className="flex w-full items-center justify-between gap-4 px-6 py-5 text-left"
                  >
                    <div>
                      <div className="text-[10px] font-black uppercase tracking-[0.22em] text-slate-400">
                        Geavanceerde instellingen
                      </div>
                      <div className="mt-2 text-sm font-medium text-slate-500">
                        Voor gevorderde gebruikers: scoring mode, exacte weight en ranges.
                      </div>
                    </div>
                    <div className="rounded-full border border-slate-200 bg-slate-50 p-2 text-slate-500">
                      {advancedOpen ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
                    </div>
                  </button>

                  {advancedOpen ? (
                    <div className="border-t border-slate-100 px-4 pb-4 pt-2 sm:px-6 sm:pb-6">
                      <IndicatorScoreEditor
                        indicator={normalizedIndicator}
                        category={category}
                        rules={draft.rules}
                        scoreMode={draft.score_mode}
                        weight={draft.weight}
                        loading={false}
                        deferred
                        onDraftChange={handleDraftChange}
                      />
                    </div>
                  ) : null}
                </section>
              </div>
            )}
          </div>

          <div className="border-t border-slate-100 px-6 py-5 sm:px-8">
            <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
              <div className="text-sm font-semibold text-slate-500">
                {summaryText}
              </div>

              <div className="flex items-center justify-end gap-4">
                <button
                  type="button"
                  onClick={onClose}
                  disabled={saving}
                  className="rounded-2xl border border-slate-200 px-5 py-3 text-[11px] font-black uppercase tracking-[0.2em] text-slate-500 transition hover:border-slate-300 hover:text-slate-700 disabled:opacity-50"
                >
                  Annuleren
                </button>
                <button
                  type="button"
                  onClick={handleConfirm}
                  disabled={saving || !isValidDraft || loading}
                  className="inline-flex min-w-[220px] items-center justify-center gap-2 rounded-2xl bg-blue-600 px-5 py-3 text-[11px] font-black uppercase tracking-[0.22em] text-white shadow-lg shadow-blue-600/20 transition hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-50"
                >
                  {saving ? "Bezig..." : actionLabel}
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>,
    document.body
  );
}
