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
