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
