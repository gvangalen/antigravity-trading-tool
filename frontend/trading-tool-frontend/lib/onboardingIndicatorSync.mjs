export function classifyOnboardingIndicatorSync(result, indicator) {
  const key = String(indicator || "").trim().toLowerCase();
  if (!key || !Array.isArray(result?.synced) || !Array.isArray(result?.failed)) {
    return "failed";
  }
  if (result.failed.some((item) => String(item?.indicator || "").trim().toLowerCase() === key)) {
    return "failed";
  }
  const entry = result.synced.find(
    (item) => String(item?.indicator || "").trim().toLowerCase() === key,
  );
  if (!entry || entry.payload?.duplicate || entry.payload?.status === "pending_source") {
    return "failed";
  }
  if (entry.payload?.value == null) return "failed";
  const explanation = String(entry.payload?.interpretation || entry.payload?.uitleg || "").toLowerCase();
  if (/geen (vastgelegde|gevalideerde|passende) scoreregel|no (matching|validated) score rule/.test(explanation)) {
    return "missing_rule";
  }
  return entry.payload?.score == null ? "pending_score" : "ready";
}

export function classifyOnboardingWorkspaceChoice(workspace, kind, indicator) {
  const key = String(indicator || "").trim().toLowerCase();
  const rows = workspace?.categories?.[kind]?.rows;
  if (!key || !Array.isArray(rows)) return "unknown";
  const row = rows.find((item) => String(item?.name || "").trim().toLowerCase() === key);
  if (!row || row.value == null) return "failed";
  if (row.score_unavailable_reason === "missing_rule") return "missing_rule";
  if (row.score == null || row.freshness?.stale !== false) return "pending_score";
  return "ready";
}
