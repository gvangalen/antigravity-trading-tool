export function resolvePlanWorkspaceSymbol({ routeSymbol, selectedAsset, fallbackSymbol } = {}) {
  return String(routeSymbol || selectedAsset || fallbackSymbol || "BTC").trim().toUpperCase();
}

export function selectFeaturedPlan(plans, symbol, activeSetupId) {
  const asset = String(symbol || "").toUpperCase();
  const candidates = (plans || []).filter((plan) =>
    String(plan?.setup?.symbol || "").toUpperCase() === asset
  );
  const activeId = String(activeSetupId || "");
  const best = candidates.find((plan) => plan.match?.is_active) || null;
  const featured = best
    || candidates.find((plan) => plan.bot?.is_active && String(plan.setup?.id || plan.setup?.setup_id || "") === activeId)
    || candidates.find((plan) => String(plan.setup?.id || plan.setup?.setup_id || "") === activeId)
    || candidates.find((plan) => plan.bot?.is_active)
    || candidates[0]
    || null;
  return { best, featured };
}
