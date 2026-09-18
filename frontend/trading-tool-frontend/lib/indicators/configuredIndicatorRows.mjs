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

const INDICATOR_LABELS = {
  dxy: "DXY",
  rsi: "RSI",
  ma_50: "MA 50",
  ma_200: "MA 200",
  price: "Price",
  volume: "Volume",
  change_24h: "24-uurs koerswijziging",
};

export function indicatorDisplayName(value) {
  const normalized = String(value || "").trim().toLowerCase().replace(/[\s-]+/g, "_");
  if (!normalized) return "Indicator";
  return INDICATOR_LABELS[normalized]
    || normalized.split("_").filter(Boolean).map((part) => part.length <= 4 ? part.toUpperCase() : `${part[0].toUpperCase()}${part.slice(1)}`).join(" ");
}
