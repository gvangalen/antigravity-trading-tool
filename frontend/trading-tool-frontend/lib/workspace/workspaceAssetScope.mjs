export function matchesWorkspaceAsset(workspace, symbol, periods = null) {
  if (!workspace || String(workspace.symbol || "").toUpperCase() !== String(symbol || "").toUpperCase()) {
    return false;
  }
  if (!periods) return true;
  return ["market", "macro", "technical"].every(
    (category) => workspace.periods?.[category] === periods[category],
  );
}
