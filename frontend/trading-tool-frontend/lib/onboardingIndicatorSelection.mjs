export function restoreOnboardingIndicator(preferences, catalog, stepCompleted) {
  if (!stepCompleted || preferences?.scope !== "symbol_override") return null;

  const name = String(preferences?.indicators?.[0]?.indicator || "").trim();
  if (!name) return null;

  return (Array.isArray(catalog) ? catalog : []).find(
    (item) => String(item?.name || "").trim().toLowerCase() === name.toLowerCase(),
  ) || { name, display_name: name };
}
