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
