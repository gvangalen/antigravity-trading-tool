"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { createPortal } from "react-dom";
import {
  CheckCircle2,
  ChevronDown,
  ChevronUp,
  Check,
  SlidersHorizontal,
  Sparkles,
  X,
} from "lucide-react";

import IndicatorScoreEditor from "@/components/scoring/IndicatorScoreEditor";
import { useModal } from "@/components/modal/ModalProvider";
import { useTranslation } from "@/app/providers/I18nProvider";
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
  { id: "low", value: 0.6 },
  { id: "normal", value: 1 },
  { id: "high", value: 2 },
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

function getCategoryLabel(category, copy) {
  return copy.categories?.[category] || copy.categories?.indicator || "Indicator";
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

function areRulesEqual(a = [], b = []) {
  if (a === b) return true;
  if (!Array.isArray(a) || !Array.isArray(b)) return false;
  if (a.length !== b.length) return false;

  return a.every((rule, index) => {
    const compare = b[index];
    return (
      String(rule?.indicator || "") === String(compare?.indicator || "") &&
      String(rule?.category || "") === String(compare?.category || "") &&
      Number(rule?.range_min) === Number(compare?.range_min) &&
      Number(rule?.range_max) === Number(compare?.range_max) &&
      Number(rule?.score) === Number(compare?.score) &&
      String(rule?.trend || "") === String(compare?.trend || "")
    );
  });
}

function areDraftsEqual(a, b) {
  if (a === b) return true;
  if (!a || !b) return false;

  return (
    String(a.indicator || "") === String(b.indicator || "") &&
    String(a.category || "") === String(b.category || "") &&
    String(a.score_mode || "standard") === String(b.score_mode || "standard") &&
    Number(a.weight || 1) === Number(b.weight || 1) &&
    areRulesEqual(a.rules, b.rules)
  );
}

function getWeightOptionFromValue(value) {
  const next = typeof value === "number" ? value : 1;
  const distances = SIMPLE_WEIGHT_OPTIONS.map((option) => ({
    option,
    distance: Math.abs(option.value - next),
  })).sort((a, b) => a.distance - b.distance);

  return distances[0]?.option || SIMPLE_WEIGHT_OPTIONS[1];
}

function buildProfileContext(preferences = {}, copy) {
  const profile = normalizeTraderProfilePreferences(preferences);
  const traderTypes = Array.isArray(profile.trader_types) ? profile.trader_types : [];
  const timeframes = Array.isArray(profile.primary_timeframes) ? profile.primary_timeframes : [];
  const riskProfiles = Array.isArray(profile.risk_profiles) ? profile.risk_profiles : [];
  const goals = Array.isArray(profile.investment_goals_list) ? profile.investment_goals_list : [];

  const primaryTraderType = traderTypes[0] || "";
  const primaryRisk = riskProfiles[0] || "";
  const summarySegments = [];

  const profileLabel = copy.profileTypes?.[primaryTraderType];
  if (profileLabel) summarySegments.push(profileLabel);

  if (timeframes.length > 0) {
    summarySegments.push(`${copy.onTimeframes} ${timeframes.map((value) => value.toUpperCase()).join(` ${copy.and} `)}`);
  }

  return {
    traderTypes,
    timeframes,
    riskProfiles,
    goals,
    primaryTraderType,
    primaryRisk,
    summaryText: summarySegments.join(" ") || copy.thisWorkflow,
  };
}

function getRoleModel(category, indicator, profileContext, copy) {
  const normalizedIndicator = normalizeIndicatorName(indicator);
  const summarySuffix = profileContext?.summaryText || copy.thisWorkflow;
  const generic = copy.roles.generic;

  if (category !== "technical") {
    return {
      description: generic.description.replace("{indicator}", getIndicatorLabel(indicator)),
      whenQuestion: generic.whenQuestion,
      whenOptions: [{ id: "default", ...generic.always }],
      recommendedWhen: ["default"],
      interpretationQuestion: generic.interpretationQuestion,
      interpretationOptions: [
        { id: "standard", ...generic.standard },
        { id: "contrarian", ...generic.contrarian },
      ],
      recommendedInterpretation: "standard",
      summaryLabel: getIndicatorLabel(indicator),
      recommendationReason: generic.recommendation.replace("{profile}", summarySuffix),
    };
  }

  if (normalizedIndicator === "rsi") {
    const fastProfile =
      profileContext?.primaryTraderType === "day_trader" || profileContext?.primaryTraderType === "scalper";

    return {
      description: copy.roles.rsi.description,
      whenQuestion: copy.roles.rsi.whenQuestion,
      whenOptions: [
        { id: "oversold", ...copy.roles.rsi.oversold },
        { id: "overbought", ...copy.roles.rsi.overbought },
        { id: "always", ...copy.roles.rsi.always },
      ],
      recommendedWhen: fastProfile ? ["always"] : ["oversold", "overbought"],
      interpretationQuestion: generic.interpretationQuestion,
      interpretationOptions: [
        { id: "standard", ...copy.roles.rsi.standard },
        { id: "contrarian", ...copy.roles.rsi.contrarian },
      ],
      recommendedInterpretation: fastProfile ? "standard" : "contrarian",
      summaryLabel: "RSI",
      recommendationReason: (fastProfile ? copy.roles.rsi.fastRecommendation : copy.roles.rsi.swingRecommendation)
        .replace("{profile}", summarySuffix),
    };
  }

  if (normalizedIndicator === "ma_200") {
    const fastProfile =
      profileContext?.primaryTraderType === "day_trader" || profileContext?.primaryTraderType === "scalper";

    return {
      description: copy.roles.ma200.description,
      whenQuestion: copy.roles.ma200.whenQuestion,
      whenOptions: [
        { id: "bull", ...copy.roles.ma200.bull },
        { id: "bear", ...copy.roles.ma200.bear },
        { id: "sideways", ...copy.roles.ma200.sideways },
      ],
      recommendedWhen: fastProfile ? ["bull", "bear"] : ["bull", "bear", "sideways"],
      interpretationQuestion: generic.interpretationQuestion,
      interpretationOptions: [
        { id: "standard", ...copy.roles.ma200.standard },
        { id: "contrarian", ...copy.roles.ma200.contrarian },
      ],
      recommendedInterpretation: "standard",
      summaryLabel: "MA 200",
      recommendationReason: (fastProfile ? copy.roles.ma200.fastRecommendation : copy.roles.ma200.standardRecommendation)
        .replace("{profile}", summarySuffix),
    };
  }

  return {
    description: generic.description.replace("{indicator}", getIndicatorLabel(indicator)),
    whenQuestion: generic.whenQuestion,
    whenOptions: [{ id: "default", ...generic.always }],
    recommendedWhen: ["default"],
    interpretationQuestion: generic.interpretationQuestion,
    interpretationOptions: [
      { id: "standard", ...generic.standard },
      { id: "contrarian", ...generic.contrarian },
    ],
    recommendedInterpretation: "standard",
    summaryLabel: getIndicatorLabel(indicator),
    recommendationReason: generic.recommendation.replace("{profile}", summarySuffix),
  };
}

function buildWhenSummary(ids, options, copy) {
  const labels = options
    .filter((option) => ids.includes(option.id))
    .map((option) => option.label.toLowerCase());

  if (labels.length === 0) return copy.noExtraMoments;
  if (labels.length === 1) return labels[0];
  if (labels.length === 2) return `${labels[0]} ${copy.and} ${labels[1]}`;
  return `${labels.slice(0, -1).join(", ")} ${copy.and} ${labels[labels.length - 1]}`;
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
  const { t } = useTranslation();
  const copy = t.legacyComponents.indicatorConfigModal;
  const [draft, setDraft] = useState(null);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [mounted, setMounted] = useState(false);
  const [advancedOpen, setAdvancedOpen] = useState(false);
  const [profileContext, setProfileContext] = useState(() => buildProfileContext({}, copy));
  const [selectedConditions, setSelectedConditions] = useState([]);

  const categoryLabel = useMemo(() => getCategoryLabel(category, copy), [category, copy]);
  const normalizedIndicator = useMemo(() => normalizeIndicatorName(indicator), [indicator]);
  const indicatorLabel = useMemo(() => getIndicatorLabel(indicator), [indicator]);
  const actionLabel = mode === "edit" ? copy.save : copy.addIndicator.replace("{indicator}", indicatorLabel);
  const roleModel = useMemo(
    () => getRoleModel(category, normalizedIndicator, profileContext, copy),
    [category, copy, normalizedIndicator, profileContext]
  );
  const interpretationOptions = roleModel.interpretationOptions || [];
  const whenOptions = roleModel.whenOptions || [];
  const selectedWeight = useMemo(() => getWeightOptionFromValue(draft?.weight), [draft?.weight]);
  const selectedInterpretation = useMemo(() => draft?.score_mode || roleModel.recommendedInterpretation || "standard", [
    draft?.score_mode,
    roleModel.recommendedInterpretation,
  ]);

  const summaryText = useMemo(() => {
    if (!draft) return "";
    const interpretationLabel = copy.interpretationLabels[selectedInterpretation] || copy.interpretationLabels.standard;
    const whenLabel = buildWhenSummary(selectedConditions, whenOptions, copy);
    const weightLabel = copy.weightOptions[selectedWeight.id].toLowerCase();
    return copy.summaryTemplate
      .replace("{indicator}", roleModel.summaryLabel || indicatorLabel)
      .replace("{interpretation}", interpretationLabel)
      .replace("{when}", whenLabel)
      .replace("{weight}", weightLabel);
  }, [copy, draft, indicatorLabel, roleModel.summaryLabel, selectedConditions, selectedInterpretation, selectedWeight.id, whenOptions]);

  const recommendationText = useMemo(() => {
    if (roleModel.recommendationReason) return roleModel.recommendationReason;
    return copy.roles.generic.recommendation.replace("{profile}", profileContext.summaryText || copy.thisWorkflow);
  }, [copy, profileContext.summaryText, roleModel.recommendationReason]);

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
    setDraft((prev) => {
      const merged = {
        ...(prev || {}),
        ...nextDraft,
        rules: Array.isArray(nextDraft?.rules) ? nextDraft.rules : prev?.rules || [],
      };

      return areDraftsEqual(prev, merged) ? prev : merged;
    });
  }, []);

  const handleSelectWeight = useCallback((weightOption) => {
    setDraft((currentDraft) => {
      if (!currentDraft) return currentDraft;
      return {
        ...currentDraft,
        weight: weightOption.value,
      };
    });
  }, []);

  const handleSelectInterpretation = useCallback((value) => {
    setDraft((currentDraft) => {
      if (!currentDraft) return currentDraft;
      return {
        ...currentDraft,
        score_mode: value,
      };
    });
  }, []);

  const handleToggleCondition = useCallback((conditionId) => {
    setSelectedConditions((current) => {
      if (current.includes(conditionId)) {
        const next = current.filter((item) => item !== conditionId);
        return next.length > 0 ? next : current;
      }
      return [...current, conditionId];
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
        const nextProfile = buildProfileContext(preferencesResponse?.preferences || preferencesResponse || {}, copy);
        const nextRoleModel = getRoleModel(category, normalizedIndicator, nextProfile, copy);

        setProfileContext(nextProfile);
        setDraft({
          ...normalizedDraft,
          score_mode: configResponse?.score_mode || nextRoleModel.recommendedInterpretation || normalizedDraft.score_mode,
        });
        setSelectedConditions(nextRoleModel.recommendedWhen || []);
      })
      .catch((error) => {
        if (!active) return;
        console.error("Failed to load indicator config modal:", error);
        setDraft(normalizeDraft(category, normalizedIndicator));
        showSnackbar(copy.loadFailed.replace("{indicator}", indicatorLabel), "danger");
      })
      .finally(() => {
        if (active) {
          setLoading(false);
        }
      });

    return () => {
      active = false;
    };
  }, [category, copy, indicatorLabel, isOpen, normalizedIndicator, showSnackbar]);

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
          ? copy.saved.replace("{indicator}", indicatorLabel).replace("{asset}", assetSymbol).replace("{category}", categoryLabel)
          : copy.added.replace("{indicator}", indicatorLabel).replace("{asset}", assetSymbol).replace("{category}", categoryLabel),
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
      showSnackbar(copy.actionFailed.replace("{indicator}", indicatorLabel), "danger");
    } finally {
      setSaving(false);
    }
  }, [
    assetSymbol,
    category,
    categoryLabel,
    copy,
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
                  {copy.eyebrow}
                </div>
                <h2 className="mt-2 text-3xl font-black tracking-tight text-slate-950">
                  {indicatorLabel}
                </h2>
                <p className="mt-3 text-sm font-medium leading-6 text-slate-500">
                  {roleModel.description}
                </p>
              </div>

              <div className="inline-flex items-center gap-2 self-start rounded-full border border-blue-100 bg-blue-50 px-3 py-1.5 text-[10px] font-black uppercase tracking-[0.22em] text-blue-600">
                <SlidersHorizontal size={12} />
                {copy.categoryConfiguration.replace("{category}", categoryLabel)}
              </div>
            </div>
          </div>

          <div className="flex-1 overflow-y-auto px-6 py-6 sm:px-8 sm:py-8">
            {loading || !draft ? (
              <div className="rounded-[28px] border border-slate-200 bg-slate-50 px-6 py-12 text-sm font-semibold text-slate-500">
                {copy.loading}
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
                        {copy.recommendedForProfile}
                      </div>
                      <div className="text-lg font-black text-slate-950">
                        {recommendationText}
                      </div>
                    </div>
                  </div>
                </section>

                <section className="rounded-[30px] border border-slate-200 bg-white p-6 shadow-sm">
                  <div className="text-[10px] font-black uppercase tracking-[0.22em] text-slate-400">
                    {roleModel.whenQuestion}
                  </div>
                  <div className="mt-4 grid gap-3 lg:grid-cols-2">
                    {whenOptions.map((option) => {
                      const active = selectedConditions.includes(option.id);
                      return (
                        <button
                          key={option.id}
                          type="button"
                          onClick={() => handleToggleCondition(option.id)}
                          className={`rounded-[24px] border px-5 py-4 text-left transition ${
                            active
                              ? "border-blue-200 bg-blue-50 shadow-sm"
                              : "border-slate-200 bg-white hover:border-slate-300 hover:bg-slate-50"
                          }`}
                        >
                          <div className="flex items-start justify-between gap-3">
                            <div>
                              <div className="text-base font-black text-slate-950">{option.label}</div>
                              <div className="mt-2 text-sm font-medium leading-6 text-slate-500">
                                {option.help}
                              </div>
                            </div>
                            <div
                              className={`mt-1 flex h-5 w-5 items-center justify-center rounded-full border ${
                                active ? "border-blue-600 bg-blue-600 text-white" : "border-slate-300 bg-white text-transparent"
                              }`}
                            >
                              <Check size={12} />
                            </div>
                          </div>
                        </button>
                      );
                    })}
                  </div>
                </section>

                <section className="rounded-[30px] border border-slate-200 bg-white p-6 shadow-sm">
                  <div className="text-[10px] font-black uppercase tracking-[0.22em] text-slate-400">
                    {roleModel.interpretationQuestion}
                  </div>
                  <div className="mt-4 grid gap-3 lg:grid-cols-2">
                    {interpretationOptions.map((option) => {
                      const active = selectedInterpretation === option.id;
                      return (
                        <button
                          key={option.id}
                          type="button"
                          onClick={() => handleSelectInterpretation(option.id)}
                          className={`rounded-[24px] border px-5 py-4 text-left transition ${
                            active
                              ? "border-blue-200 bg-blue-50 shadow-sm"
                              : "border-slate-200 bg-white hover:border-slate-300 hover:bg-slate-50"
                          }`}
                        >
                          <div className="flex items-start justify-between gap-3">
                            <div>
                              <div className="text-base font-black text-slate-950">{option.label}</div>
                              <div className="mt-2 text-sm font-medium leading-6 text-slate-500">
                                {option.help}
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
                  </div>

                  {selectedInterpretation === "custom" ? (
                    <div className="mt-4 rounded-[24px] border border-amber-200 bg-amber-50 px-5 py-4">
                      <div className="text-base font-black text-slate-950">{copy.customTitle}</div>
                      <div className="mt-2 text-sm font-medium leading-6 text-slate-500">
                        {copy.customDescription}
                      </div>
                    </div>
                  ) : null}
                </section>

                <section className="rounded-[30px] border border-slate-200 bg-white p-6 shadow-sm">
                  <div className="text-[10px] font-black uppercase tracking-[0.22em] text-slate-400">
                    {copy.influence}
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
                          {copy.weightOptions[option.id]}
                        </button>
                      );
                    })}
                  </div>
                </section>

                <section className="rounded-[30px] border border-slate-200 bg-slate-50/80 p-6 shadow-sm">
                  <div className="text-[10px] font-black uppercase tracking-[0.22em] text-slate-400">
                    {copy.summary}
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
                        {copy.advancedTitle}
                      </div>
                      <div className="mt-2 text-sm font-medium text-slate-500">
                        {copy.advancedDescription}
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
                  {copy.cancel}
                </button>
                <button
                  type="button"
                  onClick={handleConfirm}
                  disabled={saving || !isValidDraft || loading}
                  className="inline-flex min-w-[220px] items-center justify-center gap-2 rounded-2xl bg-blue-600 px-5 py-3 text-[11px] font-black uppercase tracking-[0.22em] text-white shadow-lg shadow-blue-600/20 transition hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-50"
                >
                  {saving ? copy.saving : actionLabel}
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
