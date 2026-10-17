import { marketConditionChoiceFromSetup } from "./scoreConditions.mjs";

const CATEGORIES = ["market", "macro", "technical"];

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

  const savedLimits = CATEGORIES.flatMap((category) => {
    const min = setup[`min_${category}_score`];
    const max = setup[`max_${category}_score`];
    if (min == null && max == null) return [];

    const template = min == null
      ? copy.savedThrough
      : max == null
        ? copy.savedFrom
        : copy.savedBetween;
    return [`${copy.savedCategories?.[category]} ${fillBounds(template, min, max)}`];
  });

  return `${copy.savedCustomTitle}: ${savedLimits.join("; ")}`;
}
