export function symbolsNeedingQuoteBackfill(workspace, watchlistRows, assetSymbol, selectedQuote) {
  const symbols = new Set();
  if (!selectedQuote && workspace && (workspace.quote?.price === null || workspace.quote?.price === undefined)) {
    symbols.add(assetSymbol);
  }
  for (const row of watchlistRows || []) {
    if (row?.market_id || (row?.price !== null && row?.price !== undefined)) continue;
    const symbol = String(row?.symbol || "").toUpperCase();
    if (symbol) symbols.add(symbol);
  }
  return [...symbols].sort();
}

export function mergeQuoteBackfill(workspace, quoteMap, assetSymbol) {
  if (!workspace || !quoteMap || quoteMap.size === 0) return workspace;

  let changed = false;
  const nextWorkspace = { ...workspace };
  const activeQuote = quoteMap.get(assetSymbol);
  if (!nextWorkspace.market_id && activeQuote && (nextWorkspace.quote?.price === null || nextWorkspace.quote?.price === undefined)) {
    nextWorkspace.quote = { ...(nextWorkspace.quote || {}), ...activeQuote };
    changed = true;
  }

  if (Array.isArray(nextWorkspace.watchlist?.rows)) {
    const nextRows = nextWorkspace.watchlist.rows.map((row) => {
      if (row?.market_id || (row?.price !== null && row?.price !== undefined)) return row;
      const rowSymbol = String(row?.symbol || "").toUpperCase();
      const backfilledQuote = quoteMap.get(rowSymbol);
      if (!backfilledQuote) return row;
      changed = true;
      return {
        ...row,
        price: backfilledQuote.price,
        change_24h: backfilledQuote.change_24h,
        quote: { ...(row?.quote || {}), ...backfilledQuote },
      };
    });
    if (changed) nextWorkspace.watchlist = { ...nextWorkspace.watchlist, rows: nextRows };
  }

  return changed ? nextWorkspace : workspace;
}
