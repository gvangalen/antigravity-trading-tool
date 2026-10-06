export async function persistIndicatorConfiguration({
  mode, indicator, category, assetSymbol, draft,
  onSubmitAction, saveCustomRules, updateIndicatorSettings,
}) {
  const input = { indicator, category, assetSymbol, draft };
  let indicatorCreated = false;
  try {
    if (mode === "add" && onSubmitAction) {
      await onSubmitAction(input);
      indicatorCreated = true;
    }

    const weight = typeof draft.weight === "number" ? draft.weight : 1;
    if (draft.score_mode === "custom") {
      await saveCustomRules({
        category, indicator, symbol: assetSymbol,
        rules: Array.isArray(draft.rules) ? draft.rules : [], weight,
      });
    } else {
      await updateIndicatorSettings({
        category, indicator, symbol: assetSymbol,
        score_mode: draft.score_mode || "standard", weight,
      });
    }

    if (mode !== "add") await onSubmitAction?.(input);
  } catch (error) {
    throw Object.assign(error instanceof Error ? error : new Error(String(error)), { indicatorCreated });
  }
}

export function indicatorConfigFailureMessage({ error, indicatorLabel, assetSymbol, actionFailed }) {
  if (error?.indicatorCreated) {
    return `${indicatorLabel} is toegevoegd, maar de score-instellingen zijn niet opgeslagen. Open de indicator opnieuw om ze te bewaren.`;
  }
  if (error?.status === 409) {
    return `${indicatorLabel} is al toegevoegd voor ${assetSymbol}. Bewerk de bestaande indicator.`;
  }
  if (error?.status === 400 || error?.status === 422) {
    try {
      const detail = JSON.parse(error?.body || "{}").detail;
      if (typeof detail === "string" && detail.trim()) return detail;
    } catch {}
  }
  return actionFailed;
}
