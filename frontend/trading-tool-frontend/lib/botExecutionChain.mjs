function normalizeId(value) {
  return value === null || value === undefined ? null : String(value);
}

function asObject(value) {
  return value && typeof value === "object" && !Array.isArray(value) ? value : null;
}

function findById(items, id) {
  const wanted = normalizeId(id);
  if (!wanted || !Array.isArray(items)) return null;

  return items.find((item) => normalizeId(item?.id) === wanted) || null;
}

function readNumeric(value) {
  const candidate =
    value && typeof value === "object" ? value.score ?? value.value : value;

  if (candidate === null || candidate === undefined || candidate === "") {
    return null;
  }

  return Number.isFinite(Number(candidate)) ? Number(candidate) : null;
}

export function resolveBotExecutionChain(bot, strategies = [], setups = []) {
  const embeddedStrategy = asObject(bot?.strategy);
  const strategyId =
    bot?.strategy_id ?? bot?.strategyId ?? embeddedStrategy?.id ?? null;
  const listedStrategy = findById(strategies, strategyId);
  const strategy = listedStrategy
    ? { ...(embeddedStrategy || {}), ...listedStrategy }
    : embeddedStrategy;

  const embeddedSetup = asObject(strategy?.setup) || asObject(bot?.setup);
  const setupId =
    strategy?.setup_id ??
    strategy?.setupId ??
    embeddedSetup?.id ??
    bot?.setup_id ??
    null;
  const listedSetup = findById(setups, setupId);
  const setup = listedSetup
    ? { ...(embeddedSetup || {}), ...listedSetup }
    : embeddedSetup;

  return {
    strategy,
    setup,
    strategyId,
    setupId,
    isComplete: Boolean(strategy && setup),
  };
}

export function readLinkedSetupScore(scores, setup) {
  if (!setup) return null;

  for (const key of ["score", "current_score", "latest_score"]) {
    const value = readNumeric(setup[key]);
    if (value !== null) return value;
  }

  const setupId = normalizeId(setup.id);
  if (!setupId) return null;

  for (const containerKey of ["setup_scores", "setups"]) {
    const value = readNumeric(scores?.[containerKey]?.[setupId]);
    if (value !== null) return value;
  }

  for (const key of ["setup", "setup_score"]) {
    const raw = asObject(scores?.[key]);
    if (!raw) continue;

    const scopedId = normalizeId(raw.setup_id ?? raw.entity_id ?? raw.id);
    if (scopedId !== setupId) continue;

    const value = readNumeric(raw.score ?? raw.value);
    if (value !== null) return value;
  }

  return null;
}
