export function mergeConfiguredIndicatorRows(rows, configuredNames) {
  const result = Array.isArray(rows) ? [...rows] : [];
  const present = new Set(
    result.map((row) => String(row?.name || row?.indicator || "").trim().toLowerCase()).filter(Boolean),
  );

  for (const rawName of Array.isArray(configuredNames) ? configuredNames : []) {
    const name = String(rawName || "").trim();
    const key = name.toLowerCase();
    if (!name || present.has(key)) continue;
    result.push({
      name,
      indicator: name,
      value: null,
      score: null,
      trend: null,
      action: null,
      interpretation: null,
      timestamp: null,
      configured: true,
      data_status: "pending_refresh",
    });
    present.add(key);
  }

  return result;
}
