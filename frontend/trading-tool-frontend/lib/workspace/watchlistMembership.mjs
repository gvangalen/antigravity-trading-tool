export function watchlistRowKey(row) {
  const marketId = row?.market_id ?? row?.marketId;
  if (marketId !== null && marketId !== undefined && marketId !== "") {
    return `market:${marketId}`;
  }
  const symbol = String(row?.symbol || "").trim().toUpperCase();
  return symbol ? `symbol:${symbol}` : null;
}

export function reconcileWatchlistMembership(savedItems, workspaceRows, previousRows = []) {
  const byKey = (rows) => new Map((Array.isArray(rows) ? rows : [])
    .map((row) => [watchlistRowKey(row), row])
    .filter(([key]) => key));
  const workspaceByKey = byKey(workspaceRows);
  const previousByKey = byKey(previousRows);
  const seen = new Set();

  return (Array.isArray(savedItems) ? savedItems : []).flatMap((saved) => {
    const key = watchlistRowKey(saved);
    if (!key || seen.has(key)) return [];
    seen.add(key);
    return [{
      saved,
      workspace: workspaceByKey.get(key) || null,
      previous: previousByKey.get(key) || null,
    }];
  });
}
