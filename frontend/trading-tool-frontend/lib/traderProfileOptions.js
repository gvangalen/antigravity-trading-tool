export const TRADER_TYPES = [
  { value: "investor", label: "Investeerder" },
  { value: "dca_investor", label: "DCA-investeerder" },
  { value: "swing_trader", label: "Swingtrader" },
  { value: "day_trader", label: "Daytrader" },
  { value: "scalper", label: "Scalper" },
  { value: "hybrid", label: "Hybride" },
];

export const TIMEFRAMES = [
  { value: "5m", label: "5m" },
  { value: "15m", label: "15m" },
  { value: "1h", label: "1H" },
  { value: "4h", label: "4H" },
  { value: "1d", label: "Dagelijks" },
  { value: "1w", label: "Wekelijks" },
  { value: "1m", label: "Maandelijks" },
];

export const ASSET_FOCUS = [
  { value: "bitcoin", label: "Bitcoin" },
  { value: "crypto_general", label: "Crypto algemeen" },
  { value: "stocks", label: "Aandelen" },
  { value: "etfs", label: "ETF's" },
  { value: "forex", label: "Forex" },
  { value: "commodities", label: "Grondstoffen" },
];

export const GOALS = [
  { value: "wealth_building", label: "Vermogen opbouwen" },
  { value: "extra_income", label: "Extra inkomen" },
  { value: "active_trading", label: "Actief traden" },
  { value: "financial_independence", label: "Financiële onafhankelijkheid" },
  { value: "retirement", label: "Pensioen" },
  { value: "capital_preservation", label: "Kapitaal behouden" },
];

export const EXPERIENCE_LEVELS = [
  { value: "beginner", label: "Beginner" },
  { value: "intermediate", label: "Gemiddeld" },
  { value: "advanced", label: "Gevorderd" },
  { value: "professional", label: "Professioneel" },
];

export const RISK_PROFILES = [
  { value: "conservative", label: "Conservatief" },
  { value: "balanced", label: "Normaal" },
  { value: "aggressive", label: "Agressief" },
];

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
