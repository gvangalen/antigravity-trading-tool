const CATEGORIES = ["market", "macro", "technical"];

export function formatSetupScoreConditions(setup, copy) {
  if (!setup) return copy.notReady;

  const hasAnyLimit = CATEGORIES.some((category) =>
    setup[`min_${category}_score`] != null || setup[`max_${category}_score`] != null
  );
  if (!hasAnyLimit) return copy.noScoreConditions;

  return CATEGORIES.map((category) => {
    const min = setup[`min_${category}_score`];
    const max = setup[`max_${category}_score`];
    const condition = min == null && max == null
      ? copy.noLimit
      : min == null
        ? `${copy.through} ${max}`
        : max == null
          ? `${copy.from} ${min}`
          : `${min}–${max}`;
    return `${copy[category]} ${condition}`;
  }).join(" · ");
}
