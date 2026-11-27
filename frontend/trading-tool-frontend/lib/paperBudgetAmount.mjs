export function normalizePaperBudgetAmount(raw) {
  const amount = String(raw ?? "").trim().replace(",", ".");
  if (!/^\d+(?:\.\d{1,2})?$/.test(amount)) return null;
  const [whole, fraction = ""] = amount.split(".");
  const cents = BigInt(whole) * 100n + BigInt(fraction.padEnd(2, "0"));
  return cents > 0n ? amount : null;
}
