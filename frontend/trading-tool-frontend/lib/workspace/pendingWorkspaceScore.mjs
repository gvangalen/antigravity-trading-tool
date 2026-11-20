import { exactMarketScoreNeedsRefresh } from "./pendingExactMarketScore.mjs";
import { pendingWorkspaceEvidenceCategories } from "./pendingEvidence.mjs";

const RETRYABLE_ASSET_STATES = new Set([
  "missing_score", "score_rebuild_pending", "missing_indicator_reading",
  "score_unverified", "configuration_unverified", "stale_source",
]);

export function workspaceScoreNeedsRefresh(workspace, selectedQuote) {
  if (!workspace) return false;
  if (selectedQuote) return exactMarketScoreNeedsRefresh(workspace, selectedQuote);

  const daily = workspace.daily || {};
  if (daily.benchmark_score !== null && daily.benchmark_score !== undefined) return false;
  return ["market", "macro", "technical"].some((category) =>
    RETRYABLE_ASSET_STATES.has(daily?.[category]?.source_status)
  ) || pendingWorkspaceEvidenceCategories(workspace).length > 0;
}
