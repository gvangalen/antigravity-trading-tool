/**
 * The active-setup endpoint intentionally exposes `setup_id`.  Keep that
 * identifier distinct from list/detail objects, which still use `id`.
 */
export function getSetupId(setup) {
  const candidate = setup?.setup_id ?? setup?.id;
  const value = Number(candidate);
  return Number.isInteger(value) && value > 0 ? value : null;
}

export function getActiveSetupId(activeSetup) {
  const value = Number(activeSetup?.setup_id);
  return Number.isInteger(value) && value > 0 ? value : null;
}

export function getPlanCompletionForAsset(symbol, setup, strategy) {
  const setupId = getSetupId(setup);
  const setupDone = Boolean(
    setupId && String(setup?.symbol || "").toUpperCase() === String(symbol || "").toUpperCase()
  );
  const strategyDone = Boolean(
    setupDone && strategy && Number(strategy.setup_id) === setupId
  );
  return { setupDone, strategyDone };
}

// Onboarding must use full saved records. The active-match endpoint is a
// projection without DCA cadence or score limits and cannot hydrate this form.
export function findSavedSetupForAsset(symbol, lastSetup, savedSetups = []) {
  const target = String(symbol || "").toUpperCase();
  const matches = (setup) => setup && String(setup.symbol || "").toUpperCase() === target;
  if (matches(lastSetup)) return lastSetup;
  return savedSetups
    .filter(matches)
    .sort((left, right) => (getSetupId(right) || 0) - (getSetupId(left) || 0))[0] || null;
}

export function getPlanStrategiesForAsset(symbol, strategies = [], setups = []) {
  const target = String(symbol || "").toUpperCase();
  return strategies.filter((strategy) => {
    if (String(strategy?.symbol || "").toUpperCase() !== target) return false;
    const setup = setups.find((item) => getSetupId(item) === Number(strategy.setup_id)) || strategy.setup;
    return setup && String(setup.symbol || "").toUpperCase() === target;
  });
}

/**
 * Create responses expose the canonical identifier at the envelope level.
 * Preserve it when a consumer needs the nested setup object for display.
 */
export function normalizeSetupSaveResponse(response) {
  const setup = response?.setup ?? response;
  const setupId = Number(response?.setup_id ?? setup?.setup_id ?? setup?.id);

  if (!setup || !Number.isInteger(setupId) || setupId <= 0) {
    return null;
  }

  return { ...setup, setup_id: setupId };
}
