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

export function getPlanName(plan, copy) {
  return (plan?.hasStrategy ? plan.strategy?.name : null) || plan?.setup?.name || copy.planTerm;
}

export function getFeaturedPlanMessage(copy, plan) {
  // The user may have plans for other assets but none for the selected asset.
  // Navigation between assets can reach this state before data refreshes too.
  if (!plan) return copy.noPlansBody;
  if (!plan.hasStrategy) {
    return `${getPlanName(plan, copy)}: ${copy.setupReady.toLowerCase()}, ${copy.missingStrategy.toLowerCase()}.`;
  }
  if (!plan.complete) {
    return `${getPlanName(plan, copy)}: ${copy.strategyTerm.toLowerCase()} ${copy.notReady.toLowerCase()}.`;
  }
  return `${getPlanName(plan, copy)} ${copy.readyForAutomation.toLowerCase()}.`;
}
