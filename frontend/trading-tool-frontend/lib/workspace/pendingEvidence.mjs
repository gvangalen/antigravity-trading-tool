const EVIDENCE_CATEGORIES = ["market", "macro", "technical"];

function needsMaterialization(row) {
  if (!row || typeof row !== "object") return false;
  if (row.data_status === "pending_refresh") return true;
  if (row.data_status !== "insufficient_data") return false;

  return row.value === null
    || row.value === undefined
    || row.value === ""
    || !Number.isFinite(Number(row.value));
}

export function pendingWorkspaceEvidenceCategories(workspace) {
  const categories = workspace?.categories || {};
  return EVIDENCE_CATEGORIES.filter((category) =>
    Array.isArray(categories?.[category]?.rows)
      && categories[category].rows.some(needsMaterialization),
  );
}

export async function materializeWorkspaceEvidence(categories, synchronize) {
  const results = [];
  for (const category of categories) {
    try {
      const payload = await synchronize(category);
      const failed = Array.isArray(payload?.failed) ? payload.failed : [];
      results.push({
        category,
        status: failed.length === 0 ? "fulfilled" : "rejected",
        reason: failed.length === 0 ? null : "provider_refresh_incomplete",
      });
    } catch {
      // Each category owns an independent provider request. Keep the
      // remaining configured evidence eligible for materialization.
      results.push({ category, status: "rejected", reason: "provider_refresh_failed" });
    }
  }
  return results;
}
