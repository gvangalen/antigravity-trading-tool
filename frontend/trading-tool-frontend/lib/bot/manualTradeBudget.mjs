const nonNegative = (value) => {
  const number = Number(value);
  return Number.isFinite(number) ? Math.max(0, number) : 0;
};

// Manual Paper budget, daily and order caps use 0 to mean disabled. Virtual
// cash remains mandatory; Live bots keep a positive total-budget requirement.
export function manualTradeAvailableQuote({
  totalBudget, invested, dailyLimit, todaySpent, maxOrder, isLive, paperCash,
}) {
  const total = nonNegative(totalBudget);
  const remainingTotal = total > 0
    ? Math.max(0, total - nonNegative(invested))
    : isLive ? 0 : Infinity;
  const daily = nonNegative(dailyLimit);
  const remainingDaily = daily > 0
    ? Math.max(0, daily - nonNegative(todaySpent)) : Infinity;
  const order = nonNegative(maxOrder);
  let available = Math.min(remainingTotal, remainingDaily, order > 0 ? order : Infinity);
  if (!isLive) {
    available = Math.min(available, paperCash == null ? 0 : nonNegative(paperCash));
  }
  return {
    remainingBudget: Number.isFinite(remainingTotal) ? remainingTotal : available,
    available: Number.isFinite(available) ? available : 0,
  };
}
