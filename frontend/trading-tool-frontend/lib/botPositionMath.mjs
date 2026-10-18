export function fullPaperPositionQuantity(balanceBase) {
  const quantity = Number(balanceBase);
  return Number.isFinite(quantity) && quantity > 0 ? String(quantity) : "";
}

export function botSessionPerformance(positionValue, executedCash, grossBuys) {
  const value = Number(positionValue);
  const cash = Number(executedCash);
  const buys = Number(grossBuys);
  if (positionValue == null || executedCash == null ||
      !Number.isFinite(value) || !Number.isFinite(cash)) {
    return { pnlEur: null, pnlPct: null };
  }
  const pnlEur = value + cash;
  return {
    pnlEur,
    pnlPct: grossBuys != null && Number.isFinite(buys) && buys > 0
      ? (pnlEur / buys) * 100 : null,
  };
}
