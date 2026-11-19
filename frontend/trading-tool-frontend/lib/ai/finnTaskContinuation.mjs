const savedId = (value) => /^\d+$/.test(String(value || "")) ? String(value) : null;
const marketSymbol = (value) => /^[A-Z0-9]{2,12}$/.test(String(value || "")) ? String(value) : null;

export function buildFinnTaskContinuationPrompt(task) {
  const setupId = savedId(task?.setup_id);
  if (!setupId) return null;
  if (task.step === "strategy") {
    const asset = task.asset ? marketSymbol(task.asset) : null;
    if (task.asset && !asset) return null;
    const setupLabel = asset ? `${asset}-setup` : "setup";
    return `Maak nu de strategie voor de zojuist opgeslagen ${setupLabel} met ID ${setupId}. Gebruik deze bestaande setup; maak geen tweede setup. Vraag gericht naar ontbrekende verplichte strategiekeuzes en leg de strategie ter bevestiging voor.`;
  }
  if (task.step === "score") {
    const strategyId = savedId(task.strategy_id);
    const asset = marketSymbol(task.asset);
    const quote = task.quote_currency ? marketSymbol(task.quote_currency) : null;
    if (!strategyId || !asset || (task.quote_currency && !quote)) return null;
    const pair = quote ? `${asset}/${quote}` : asset;
    return `Haal nu via de bestaande scorefunctie de actuele benchmarkscore op voor ${pair}. Toon één eindresultaat voor de opgeslagen setup ID ${setupId}, de opgeslagen strategie ID ${strategyId} en de beschikbare score. Als de score ontbreekt, zeg welke bron of scorecomponent ontbreekt en behoud het gedeeltelijke resultaat.`;
  }
  return null;
}
