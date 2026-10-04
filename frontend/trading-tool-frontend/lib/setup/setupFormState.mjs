import { normalizeDcaWeekday } from "./dcaWeekday.mjs";

export function initialSetupFormState(setup = null) {
  return {
    name: setup?.name ?? "",
    symbol: setup?.symbol ?? "BTC",
    setupType: setup?.setup_type ?? "dca",
    timeframe: setup?.timeframe ?? "1W",
    dcaFrequency: setup?.dca_frequency ?? "weekly",
    dcaDay: normalizeDcaWeekday(setup?.dca_day) ?? "monday",
    dcaMonthDay: setup?.dca_month_day ?? 1,
  };
}
