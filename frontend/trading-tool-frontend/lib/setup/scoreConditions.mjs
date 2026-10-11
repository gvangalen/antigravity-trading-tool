const SCORE_FIELDS = [
  "min_macro_score", "max_macro_score",
  "min_technical_score", "max_technical_score",
  "min_market_score", "max_market_score",
];

export function hasSetupScoreConditions(setup) {
  return SCORE_FIELDS.some((field) => setup?.[field] != null);
}

export function hasPartialSetupScoreConditions(setup) {
  return hasSetupScoreConditions(setup) && SCORE_FIELDS.some((field) => setup?.[field] == null);
}

export function setupScorePayload(enabled, macro, technical, market, untouchedExistingSetup = null) {
  if (!enabled) {
    return Object.fromEntries(SCORE_FIELDS.map((field) => [field, null]));
  }
  if (untouchedExistingSetup) {
    return Object.fromEntries(SCORE_FIELDS.map((field) => [field, untouchedExistingSetup[field] ?? null]));
  }
  return {
    min_macro_score: macro[0], max_macro_score: macro[1],
    min_technical_score: technical[0], max_technical_score: technical[1],
    min_market_score: market[0], max_market_score: market[1],
  };
}
