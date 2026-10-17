const SCORE_FIELDS = [
  "min_macro_score", "max_macro_score",
  "min_technical_score", "max_technical_score",
  "min_market_score", "max_market_score",
];

// Inclusive, non-overlapping bands. The same bounds are sent to the setup
// matcher; labels are presentation only and make no claim about RSI or price.
export const MARKET_CONDITIONS = Object.freeze([
  { id: "heavy_pressure", min: 0, max: 25 },
  { id: "pressure", min: 26, max: 45 },
  { id: "no_direction", min: 46, max: 60 },
  { id: "gaining_strength", min: 61, max: 75 },
  { id: "strong", min: 76, max: 100 },
]);

export function marketConditionChoiceFromSetup(setup) {
  if (!hasSetupScoreConditions(setup)) return "off";
  if (["macro", "technical"].some((component) =>
    setup?.[`min_${component}_score`] != null || setup?.[`max_${component}_score`] != null
  )) return "custom";
  return MARKET_CONDITIONS.find(({ min, max }) =>
    Number(setup?.min_market_score) === min && Number(setup?.max_market_score) === max
  )?.id || "custom";
}

export function mayKeepUnfilteredTrade(isEdit, setup) {
  return Boolean(isEdit && String(setup?.setup_type || "").toLowerCase() === "trade" && marketConditionChoiceFromSetup(setup) === "off");
}

export function marketConditionPayload(choice, customBounds) {
  if (choice === "off") return Object.fromEntries(SCORE_FIELDS.map((field) => [field, null]));
  const band = MARKET_CONDITIONS.find((item) => item.id === choice);
  if (band) return {
    min_market_score: band.min, max_market_score: band.max,
    min_macro_score: null, max_macro_score: null,
    min_technical_score: null, max_technical_score: null,
  };
  if (choice === "custom") return Object.fromEntries(SCORE_FIELDS.map((field) => [field, customBounds?.[field] ?? null]));
  throw new Error("Choose a market condition before saving");
}

// Existing partial setups show fallback slider values. Keep absent limits
// absent unless the corresponding handle was explicitly moved, including when
// it was moved away and then back to the displayed fallback value.
export function editedCustomScorePayload(existing, macro, technical, market, touchedFields = {}) {
  const visible = setupScorePayload(true, macro, technical, market);
  if (!existing) return visible;
  return Object.fromEntries(SCORE_FIELDS.map((field) => [
    field,
    existing[field] == null && !touchedFields[field]
      ? null : visible[field],
  ]));
}

export function scoreRangeTouchedFields(category, previousRange, nextRange, touchedFields = {}) {
  return {
    ...touchedFields,
    ...(Number(previousRange[0]) !== Number(nextRange[0]) ? { [`min_${category}_score`]: true } : {}),
    ...(Number(previousRange[1]) !== Number(nextRange[1]) ? { [`max_${category}_score`]: true } : {}),
  };
}

export function hasSetupScoreConditions(setup) {
  return SCORE_FIELDS.some((field) => setup?.[field] != null);
}

export function hasPartialSetupScoreConditions(setup) {
  return hasSetupScoreConditions(setup) && SCORE_FIELDS.some((field) => setup?.[field] == null);
}

export function setupScoreOriginKey(isEdit, setup, touched) {
  if (!isEdit) return "scoreDefaultOrigin";
  if (touched) return "scoreEditedOrigin";
  return hasPartialSetupScoreConditions(setup)
    ? "scorePartialOrigin"
    : "scoreSavedOrigin";
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
