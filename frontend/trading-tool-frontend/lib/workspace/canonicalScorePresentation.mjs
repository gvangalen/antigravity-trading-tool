const ALIASES = {
  s_and_p500: "sp500",
  s_and_p_500: "sp500",
  sandp500: "sp500",
  sandp_500: "sp500",
  fear_and_greed_index: "fear_greed_index",
};

export function evidenceKey(name) {
  const key = String(name || "").trim().toLowerCase()
    .replace(/&/g, "and").replace(/\s+/g, "_").replace(/-+/g, "_");
  return ALIASES[key] || key;
}

export function validatedDayEvidence(indicatorScore, evidence, name) {
  if (indicatorScore === null || indicatorScore === undefined || indicatorScore === "") return null;
  if (!Number.isFinite(Number(indicatorScore))) return null;
  const row = evidence?.[evidenceKey(name)] || null;
  return row && ["custom", "system_template"].includes(row.rule_origin) ? row : null;
}

export function indicatorSourceFreshness(freshness) {
  if (freshness?.status !== "available") return "unavailable";
  return freshness.stale ? "stale" : "current";
}

export function normalizedIndicatorPosition(evidence) {
  const value = evidence?.normalized_value;
  if (value === null || value === undefined || value === "") return null;
  const numeric = Number(value);
  return Number.isFinite(numeric) ? Math.round(numeric) : null;
}

export function currentIndicatorScore(item, evidence, hasValue, currentEvidenceAvailable) {
  if (!hasValue || (currentEvidenceAvailable && !evidence)) return null;
  const value = currentEvidenceAvailable ? evidence?.score : item?.score;
  if (value === null || value === undefined || value === "") return null;
  const numeric = Number(value);
  return Number.isFinite(numeric) && numeric >= 0 && numeric <= 100 ? numeric : null;
}

export function hasCompleteDailyBenchmark(workspace, symbol) {
  const validScore = (value) => value !== null && value !== undefined && value !== ""
    && Number.isFinite(Number(value));
  const daily = workspace?.daily;
  return String(workspace?.symbol || "").toUpperCase() === String(symbol || "").toUpperCase()
    && validScore(daily?.benchmark_score)
    && ["market", "macro", "technical"].every((category) => validScore(daily?.[category]?.score));
}

export function formatBenchmarkScore(value, locale = "nl") {
  if (value === null || value === undefined || value === "") return "—";
  const score = Number(value);
  if (!Number.isFinite(score)) return "—";
  return new Intl.NumberFormat(locale, { maximumFractionDigits: 1 }).format(score);
}
