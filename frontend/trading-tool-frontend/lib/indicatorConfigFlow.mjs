export async function persistIndicatorConfiguration({
  mode, indicator, category, assetSymbol, draft,
  onSubmitAction, saveCustomRules, updateIndicatorSettings,
}) {
  const input = { indicator, category, assetSymbol, draft };
  let indicatorCreated = false;
  let configurationSaved = false;
  let addResult = null;
  try {
    const weight = typeof draft.weight === "number" ? draft.weight : 1;
    // An indicator without a system template needs its five owner rules before
    // the add endpoint can safely include it in Score 2.0.
    if (mode === "add" && draft.score_mode === "custom") {
      await saveCustomRules({
        category, indicator, symbol: assetSymbol,
        rules: Array.isArray(draft.rules) ? draft.rules : [], weight,
        create_only: true,
      });
      configurationSaved = true;
    }
    if (mode === "add" && onSubmitAction) {
      addResult = await onSubmitAction(input);
      indicatorCreated = true;
    }

    if (draft.score_mode === "custom") {
      if (mode !== "add") {
        await saveCustomRules({
          category, indicator, symbol: assetSymbol,
          rules: Array.isArray(draft.rules) ? draft.rules : [], weight,
        });
      }
    } else {
      await updateIndicatorSettings({
        category, indicator, symbol: assetSymbol,
        score_mode: draft.score_mode || "standard", weight,
      });
    }

    if (mode !== "add") await onSubmitAction?.(input);
    return { pendingSource: addResult?.status === "pending_source" };
  } catch (error) {
    throw Object.assign(error instanceof Error ? error : new Error(String(error)), { indicatorCreated, configurationSaved });
  }
}

export function indicatorConfigFailureMessage({ error, indicatorLabel, assetSymbol, actionFailed }) {
  if (error?.configurationSaved && !error?.indicatorCreated) {
    return `${indicatorLabel}: je scoreregels zijn opgeslagen, maar de bronmeting kon niet worden opgehaald. De indicator heeft nog geen score.`;
  }
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
