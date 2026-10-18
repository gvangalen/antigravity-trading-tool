import { marketConditionChoiceFromSetup } from "./scoreConditions.mjs";

function fillBounds(template, min, max) {
  return String(template || "")
    .replace("{min}", String(min))
    .replace("{max}", String(max));
}

export function formatSetupScoreConditions(setup, copy = {}) {
  if (!setup) return copy.savedNotReady;

  const choice = marketConditionChoiceFromSetup(setup);
  if (choice === "off") return copy.savedNoConditions;

  if (choice !== "custom") {
    const option = copy.options?.[choice];
    if (option?.title && option?.rule) return `${option.title} · ${option.rule}`;
  }

  const min = setup.min_benchmark_score;
  const max = setup.max_benchmark_score;
  if (min == null && max == null) return copy.savedNoConditions;
  const template = min == null
    ? copy.savedThrough
    : max == null
      ? copy.savedFrom
      : copy.savedBetween;
  return `${copy.savedCustomTitle}: ${copy.savedBenchmark || "benchmark"} ${fillBounds(template, min, max)}`;
}
