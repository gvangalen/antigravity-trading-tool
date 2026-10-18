const LEGACY_SCORE_FIELDS = [
  "min_macro_score", "max_macro_score",
  "min_technical_score", "max_technical_score",
  "min_market_score", "max_market_score",
];
const SCORE_FIELDS = ["min_benchmark_score", "max_benchmark_score", ...LEGACY_SCORE_FIELDS];

// Inclusive, non-overlapping bands. The same bounds are sent to the setup
// matcher; labels are presentation only and make no claim about RSI or price.
export const MARKET_CONDITIONS = Object.freeze([
  { id: "heavy_pressure", min: 0, max: 25 },
  { id: "pressure", min: 26, max: 45 },
  { id: "no_direction", min: 46, max: 60 },
  { id: "gaining_strength", min: 61, max: 75 },
  { id: "strong", min: 76, max: 100 },
]);

export function marketConditionForScore(value) {
  if (value === null || value === undefined || value === "") return null;
  const score = Number(value);
  if (!Number.isFinite(score) || score < 0 || score > 100) return null;
  const displayedScore = Math.round(score);
  return MARKET_CONDITIONS.find(({ min, max }) => displayedScore >= min && displayedScore <= max) || null;
}

export function marketConditionChoiceFromSetup(setup) {
  if (!hasSetupScoreConditions(setup)) return "off";
  if (LEGACY_SCORE_FIELDS.some((field) => setup?.[field] != null)) return "custom";
  return MARKET_CONDITIONS.find(({ min, max }) =>
    Number(setup?.min_benchmark_score) === min && Number(setup?.max_benchmark_score) === max
  )?.id || "custom";
}
export function mayKeepUnfilteredTrade(isEdit, setup) {
  return Boolean(isEdit && String(setup?.setup_type || "").toLowerCase() === "trade" && marketConditionChoiceFromSetup(setup) === "off");
}

export function marketConditionPayload(choice, customBounds) {
  if (choice === "off") return Object.fromEntries(SCORE_FIELDS.map((field) => [field, null]));
  const band = MARKET_CONDITIONS.find((item) => item.id === choice);
  if (band) return {
    ...Object.fromEntries(LEGACY_SCORE_FIELDS.map((field) => [field, null])),
    min_benchmark_score: band.min, max_benchmark_score: band.max,
  };
  if (choice === "custom") return {
    ...Object.fromEntries(LEGACY_SCORE_FIELDS.map((field) => [field, null])),
    min_benchmark_score: customBounds?.min_benchmark_score ?? null,
    max_benchmark_score: customBounds?.max_benchmark_score ?? null,
  };
  throw new Error("Choose a market condition before saving");
}

// Existing partial setups show fallback slider values. Keep absent limits
// absent unless the corresponding handle was explicitly moved, including when
// it was moved away and then back to the displayed fallback value.
export function editedCustomScorePayload(existing, benchmark) {
  return marketConditionPayload("custom", {
    min_benchmark_score: benchmark[0], max_benchmark_score: benchmark[1],
  });
}

export function hasSetupScoreConditions(setup) {
  return SCORE_FIELDS.some((field) => setup?.[field] != null);
}

export function hasPartialSetupScoreConditions(setup) {
  return hasSetupScoreConditions(setup) &&
    (setup?.min_benchmark_score == null || setup?.max_benchmark_score == null);
}

export function setupScoreOriginKey(isEdit, setup, touched) {
  if (!isEdit) return "scoreDefaultOrigin";
  if (touched) return "scoreEditedOrigin";
  return hasPartialSetupScoreConditions(setup)
    ? "scorePartialOrigin"
    : "scoreSavedOrigin";
}
