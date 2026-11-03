import { marketConditionChoiceFromSetup, marketConditionPayload } from "../setup/scoreConditions.mjs";

const WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"];

function savedWeekday(value) {
  return WEEKDAYS[Number(value) - 1] || String(value || "").toLowerCase();
}

export function setupPatchForOnboarding(saved, draft, conditionChoice, scoreTouched = false) {
  const patch = {};
  const name = draft.name.trim();
  if (name !== saved.name) patch.name = name;
  if (draft.timeframe !== saved.timeframe) patch.timeframe = draft.timeframe;

  if (draft.setupType === "dca") {
    const frequency = draft.dcaFrequency;
    if (frequency !== saved.dca_frequency) patch.dca_frequency = frequency;
    const weekday = frequency === "weekly" ? draft.dcaDay : null;
    const previousWeekday = saved.dca_frequency === "weekly" ? savedWeekday(saved.dca_day) : null;
    if (weekday !== previousWeekday) patch.dca_day = weekday;
    const monthDay = frequency === "monthly" ? Number(draft.dcaMonthDay) : null;
    const previousMonthDay = saved.dca_frequency === "monthly" ? Number(saved.dca_month_day) : null;
    if (monthDay !== previousMonthDay) patch.dca_month_day = monthDay;
  }

  const oldChoice = marketConditionChoiceFromSetup(saved);
  const scoreChanged = conditionChoice !== oldChoice || (conditionChoice === "custom" && scoreTouched && (
    Number(draft.min_benchmark_score) !== Number(saved.min_benchmark_score) ||
    Number(draft.max_benchmark_score) !== Number(saved.max_benchmark_score)
  ));
  if (scoreChanged) Object.assign(patch, marketConditionPayload(conditionChoice, {
    min_benchmark_score: Number(draft.min_benchmark_score),
    max_benchmark_score: Number(draft.max_benchmark_score),
  }));
  return patch;
}

function targetPrices(value) {
  if (Array.isArray(value)) return value.map((item) => Number(typeof item === "object" ? item.price : item));
  return String(value || "").split(",").map((item) => Number(item.trim())).filter(Number.isFinite);
}

export function strategyPatchForOnboarding(saved, draft, isTrade) {
  const patch = {};
  const name = draft.name.trim();
  if (name !== saved.name) patch.name = name;
  const amount = Number(draft.baseAmount);
  if (amount !== Number(saved.base_amount ?? saved.amount)) patch.base_amount = amount;
  if (isTrade) {
    if (Number(draft.entry) !== Number(saved.entry)) patch.entry = Number(draft.entry);
    if (Number(draft.stopLoss) !== Number(saved.stop_loss)) patch.stop_loss = Number(draft.stopLoss);
    const targets = targetPrices(draft.targets);
    if (JSON.stringify(targets) !== JSON.stringify(targetPrices(saved.targets))) patch.targets = targets;
  }
  return patch;
}

export function resolveSavedOnboardingPlan({ symbol, setups, strategies, fallbackSetup, setupId = 0, strategyId = 0 }) {
  const requestedSetupId = Number(setupId);
  const requestedStrategyId = Number(strategyId);
  const selectedStrategy = requestedStrategyId > 0
    ? strategies.find((item) => Number(item.id ?? item.strategy_id) === requestedStrategyId)
    : null;
  const selectedSetupId = requestedSetupId > 0 ? requestedSetupId : Number(selectedStrategy?.setup_id);
  const selectedSetup = selectedSetupId > 0
    ? setups.find((item) => Number(item.id ?? item.setup_id) === selectedSetupId && String(item.symbol).toUpperCase() === symbol)
    : fallbackSetup;
  if ((requestedSetupId > 0 && !selectedSetup) ||
      (requestedStrategyId > 0 && (!selectedStrategy || Number(selectedStrategy.setup_id) !== Number(selectedSetup?.id ?? selectedSetup?.setup_id)))) {
    return { invalid: true, setup: null, strategy: null };
  }
  return { invalid: false, setup: selectedSetup || null, strategy: selectedStrategy || null };
}

export function resolveOnboardingStrategyDetails(candidate, strategies, setupId) {
  if (!candidate) return { invalid: false, strategy: null };
  const candidateId = Number(candidate.id ?? candidate.strategy_id);
  const detailed = strategies.find((item) => Number(item.id ?? item.strategy_id) === candidateId);
  if (!detailed || Number(detailed.setup_id) !== Number(setupId) ||
      (detailed.execution_mode === "custom" &&
        (!Array.isArray(detailed.decision_curve?.points) || detailed.decision_curve.points.length < 2))) {
    return { invalid: true, strategy: null };
  }
  return { invalid: false, strategy: detailed };
}
