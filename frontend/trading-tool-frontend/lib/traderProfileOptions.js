export const TRADER_TYPE_VALUES = [
  "investor",
  "dca_investor",
  "swing_trader",
  "day_trader",
  "scalper",
  "hybrid",
];

export const TIMEFRAME_VALUES = ["5m", "15m", "1h", "4h", "1d", "1w", "1m"];

export const ASSET_FOCUS_VALUES = [
  "bitcoin",
  "crypto_general",
  "stocks",
  "etfs",
  "forex",
  "commodities",
];

export const GOAL_VALUES = [
  "wealth_building",
  "extra_income",
  "active_trading",
  "financial_independence",
  "retirement",
  "capital_preservation",
];

export const EXPERIENCE_LEVEL_VALUES = ["beginner", "intermediate", "advanced", "professional"];

export const RISK_PROFILE_VALUES = ["conservative", "balanced", "aggressive"];

function createOptions(values, labels = {}) {
  return values.map((value) => ({
    value,
    label: labels[value] || value,
  }));
}

export function getTraderTypeOptions(t) {
  return createOptions(TRADER_TYPE_VALUES, t?.traderProfile?.options?.traderTypes);
}

export function getTimeframeOptions(t) {
  return createOptions(TIMEFRAME_VALUES, t?.traderProfile?.options?.timeframes);
}

export function getAssetFocusOptions(t) {
  return createOptions(ASSET_FOCUS_VALUES, t?.traderProfile?.options?.assetFocus);
}

export function getGoalOptions(t) {
  return createOptions(GOAL_VALUES, t?.traderProfile?.options?.goals);
}

export function getExperienceLevelOptions(t) {
  return createOptions(EXPERIENCE_LEVEL_VALUES, t?.traderProfile?.options?.experienceLevels);
}

export function getRiskProfileOptions(t) {
  return createOptions(RISK_PROFILE_VALUES, t?.traderProfile?.options?.riskProfiles);
}

export function createOptionLabelMap(options) {
  return options.reduce((acc, option) => {
    acc[option.value] = option.label;
    return acc;
  }, {});
}

function ensureArray(value) {
  if (Array.isArray(value)) {
    return value.filter(Boolean);
  }
  if (typeof value === "string" && value.trim()) {
    return [value];
  }
  return [];
}

export function normalizeTraderProfilePreferences(preferences = {}) {
  const traderTypes = ensureArray(preferences.trader_types ?? preferences.trader_type);
  const investmentGoals = ensureArray(preferences.investment_goals_list ?? preferences.investment_goals);
  const experienceLevels = ensureArray(preferences.experience_levels ?? preferences.experience_level);
  const riskProfiles = ensureArray(preferences.risk_profiles ?? preferences.risk_profile);

  return {
    trader_types: traderTypes,
    primary_timeframes: ensureArray(preferences.primary_timeframes),
    asset_focus: ensureArray(preferences.asset_focus),
    investment_goals_list: investmentGoals,
    experience_levels: experienceLevels,
    risk_profiles: riskProfiles,
  };
}

export function serializeTraderProfilePreferences(form = {}) {
  const traderTypes = ensureArray(form.trader_types);
  const investmentGoals = ensureArray(form.investment_goals_list);
  const experienceLevels = ensureArray(form.experience_levels);
  const riskProfiles = ensureArray(form.risk_profiles);

  return {
    trader_types: traderTypes,
    trader_type: traderTypes[0] || "",
    primary_timeframes: ensureArray(form.primary_timeframes),
    asset_focus: ensureArray(form.asset_focus),
    investment_goals_list: investmentGoals,
    investment_goals: investmentGoals[0] || "",
    experience_levels: experienceLevels,
    experience_level: experienceLevels[0] || "",
    risk_profiles: riskProfiles,
    risk_profile: riskProfiles[0] || "",
  };
}
