const RETRYABLE_STATES = new Set([
  "missing_score", "score_rebuild_pending", "missing_indicator_reading",
  "score_unverified", "configuration_unverified",
]);

export function exactMarketScoreNeedsRefresh(workspace, selectedQuote) {
  return Boolean(selectedQuote && ["market", "macro", "technical"].some((category) =>
    (RETRYABLE_STATES.has(workspace?.daily?.[category]?.source_status) ||
     (category !== "macro" && workspace?.daily?.[category]?.source_status === "stale_source"))
  ));
}
