export function restoreOnboardingIndicator(preferences, catalog, stepCompleted) {
  if (!stepCompleted || preferences?.scope !== "symbol_override") return null;

  const name = String(preferences?.indicators?.[0]?.indicator || "").trim();
  if (!name) return null;

  return (Array.isArray(catalog) ? catalog : []).find(
    (item) => String(item?.name || "").trim().toLowerCase() === name.toLowerCase(),
  ) || { name, display_name: name };
}

export function hasSavedOnboardingAnalysisChoices({ asset, market, macro, technical }) {
  return Boolean(asset && market && macro && technical);
}

export function canChooseOnboardingIndicator(kind, { asset, market, macro }) {
  if (!asset) return false;
  if (kind === "market") return true;
  if (kind === "macro") return Boolean(market);
  if (kind === "technical") return Boolean(market && macro);
  return false;
}
