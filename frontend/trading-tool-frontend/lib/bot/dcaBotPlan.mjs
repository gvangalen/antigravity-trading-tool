const cents = (amount) => Math.round(amount * 100) / 100;

export function dcaBotPlan(strategy, setup) {
  if (String(setup?.setup_type || setup?.type || "").toLowerCase() !== "dca") return null;
  const base = Number(strategy?.base_amount);
  if (!Number.isFinite(base) || base <= 0) return null;

  const mode = String(strategy?.execution_mode || "").toLowerCase();
  let multipliers;
  if (mode === "fixed") {
    multipliers = [1];
  } else if (mode === "custom" && Array.isArray(strategy?.decision_curve?.points)) {
    multipliers = strategy.decision_curve.points.map((point) => Number(point?.y));
    if (multipliers.length < 2 || multipliers.some((value) => !Number.isFinite(value) || value <= 0)) return null;
  } else {
    return null;
  }

  const minimum = cents(base * Math.min(...multipliers));
  const maximum = cents(base * Math.max(...multipliers));
  if (minimum <= 0 || maximum <= 0) return null;
  return {
    minimum,
    maximum,
    base: cents(base),
    variable: mode === "custom",
  };
}

export function dcaBotBudgetCheck(plan, values, { automatic = false, paper = false, create = false } = {}) {
  if (!plan) return null;
  const total = Number(values.budget_total_eur);
  const daily = Number(values.budget_daily_limit_eur);
  const minimum = Number(values.budget_min_order_eur);
  const maximum = Number(values.budget_max_order_eur);
  const cash = Number(values.paper_initial_cash_eur);
  if (!Number.isFinite(total) || total < plan.maximum) return "total";
  if (automatic && (!Number.isFinite(daily) || daily < plan.maximum)) return "daily";
  if (automatic && (!Number.isFinite(maximum) || maximum < plan.maximum)) return "maximum";
  if (automatic && (!Number.isFinite(minimum) || minimum > plan.minimum)) return "minimum";
  if (automatic && paper && create && (!Number.isFinite(cash) || cash < plan.maximum)) return "cash";
  return null;
}

export function dcaPurchaseCapacity(plan, total) {
  const budget = Number(total);
  if (!plan || !Number.isFinite(budget) || budget <= 0) return null;
  const plannedCents = Math.round(plan.maximum * 100);
  return plannedCents > 0 ? Math.floor(Math.round(budget * 100) / plannedCents) : null;
}
