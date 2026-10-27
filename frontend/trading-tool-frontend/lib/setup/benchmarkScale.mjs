import { MARKET_CONDITIONS, marketConditionForScore } from "./scoreConditions.mjs";

const validScore = (value) => {
  if (value === null || value === undefined || value === "" || typeof value === "boolean") return null;
  const number = Number(value);
  return Number.isFinite(number) && number >= 0 && number <= 100 ? number : null;
};

export function benchmarkScaleBands() {
  return MARKET_CONDITIONS.map((band, index) => {
    const start = index === 0 ? 0 : band.min - 0.5;
    const end = index === MARKET_CONDITIONS.length - 1 ? 100 : band.max + 0.5;
    return { ...band, start, end, width: end - start };
  });
}

export function withSelectedBenchmarkSetup(search, setupId) {
  const params = new URLSearchParams(String(search || "").replace(/^\?/, ""));
  const id = Number(setupId);
  if (Number.isSafeInteger(id) && id > 0) params.set("benchmarkSetup", String(id));
  else params.delete("benchmarkSetup");
  return params.toString();
}

export function withSelectedTradingQuote(search, quoteCurrency) {
  // A setup selected for the previous quote must not remain selected after
  // changing the market whose score and conditions are being displayed.
  const params = new URLSearchParams(withSelectedBenchmarkSetup(search, null));
  const quote = String(quoteCurrency || "").trim().toUpperCase();
  if (quote) params.set("quote", quote);
  else params.delete("quote");
  return params.toString();
}

export function benchmarkSetupSessionKey(userId, symbol) {
  const owner = Number(userId);
  const asset = String(symbol || "").trim().toUpperCase();
  if (!Number.isSafeInteger(owner) || owner <= 0 || !/^[A-Z0-9]{1,15}$/.test(asset)) return null;
  return `benchmarkSetup:${owner}:${asset}`;
}

export function selectedBenchmarkSetupMatch(matches, selectedId) {
  const ownerMatches = Array.isArray(matches) ? matches : [];
  return ownerMatches.find((match) => String(match.setup_id) === String(selectedId))
    || ownerMatches.find((match) => match.is_best)
    || ownerMatches[0]
    || null;
}

export function benchmarkSetupView(score, match) {
  const current = validScore(score);
  const condition = match?.conditions?.benchmark;
  const minimum = validScore(condition?.minimum);
  const maximum = validScore(condition?.maximum);
  const hasCondition = minimum !== null || maximum !== null;
  const validBounds = !hasCondition || minimum === null || maximum === null || minimum <= maximum;
  const preset = validBounds && minimum !== null && maximum !== null
    ? MARKET_CONDITIONS.find((band) => band.min === minimum && band.max === maximum) || null
    : null;
  const sourceScore = validScore(match?.components?.benchmark?.score);
  const sourceAgrees = current !== null && sourceScore !== null && Math.round(current) === Math.round(sourceScore);
  const status = !match ? "no_setup" : !hasCondition || !validBounds ? "no_condition"
    : current === null ? "insufficient_data"
      : !sourceAgrees ? "updating"
        : match.status === "matches" || match.status === "outside_conditions" ? match.status : "updating";

  return {
    current,
    currentBand: current === null ? null : marketConditionForScore(current),
    minimum,
    maximum,
    preset,
    status,
    zone: hasCondition && validBounds
      ? { start: Math.max(0, (minimum ?? 0) - (minimum === null ? 0 : 0.5)),
          end: Math.min(100, (maximum ?? 100) + (maximum === null ? 0 : 0.5)) }
      : null,
  };
}
