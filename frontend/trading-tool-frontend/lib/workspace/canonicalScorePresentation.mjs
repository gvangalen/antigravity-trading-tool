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

export function validatedDayEvidence(categoryScore, evidence, name) {
  if (categoryScore === null || categoryScore === undefined || categoryScore === "") return null;
  if (!Number.isFinite(Number(categoryScore))) return null;
  const row = evidence?.[evidenceKey(name)] || null;
  return row && ["custom", "system_template"].includes(row.rule_origin) ? row : null;
}

export function indicatorSourceFreshness(freshness) {
  if (freshness?.status !== "available") return "unavailable";
  return freshness.stale ? "stale" : "current";
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
