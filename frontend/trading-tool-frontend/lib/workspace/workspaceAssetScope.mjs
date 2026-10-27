export function matchesWorkspaceAsset(workspace, symbol, periods = null, quoteCurrency = null) {
  if (!workspace || String(workspace.symbol || "").toUpperCase() !== String(symbol || "").toUpperCase()) {
    return false;
  }
  if (quoteCurrency && String(workspace.quote_currency || "").toUpperCase() !== String(quoteCurrency).toUpperCase()) {
    return false;
  }
  if (!quoteCurrency && workspace.quote_currency) return false;
  if (!periods) return true;
  return ["market", "macro", "technical"].every(
    (category) => workspace.periods?.[category] === periods[category],
  );
}
