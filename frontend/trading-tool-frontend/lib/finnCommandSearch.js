export const FINN_COMMAND_OPEN_EVENT = "finn-command-search:open";
export const FINN_INDICATOR_MODAL_OPEN_EVENT = "finn-indicator-config:open";
export const FINN_INDICATOR_MODAL_COMPLETED_EVENT = "finn-indicator-config:completed";

export function closeFeedDiscussionIfCurrent(current, nonce) {
  return current?.request.nonce === nonce ? null : current;
}

export function updateFeedDiscussionDraftIfCurrent(current, nonce, draft) {
  return current?.request.nonce === nonce ? { ...current, draft } : current;
}

export function resolveFeedItemContext(item) {
  const symbol = String(item?.symbol || "").trim().toUpperCase();
  const pair = String(item?.evidence?.trading_pair || "").trim().toUpperCase();
  const [pairSymbol, quoteCurrency, extra] = pair.split("/");
  const exactPair = !extra && pairSymbol === symbol && /^[A-Z]{3,5}$/.test(quoteCurrency || "");
  const marketId = item?.evidence?.market_id;
  return {
    ...(symbol ? { symbol } : {}),
    ...(exactPair ? { quote_currency: quoteCurrency } : {}),
    ...(exactPair && Number.isSafeInteger(marketId) && marketId > 0 ? { market_id: marketId } : {}),
  };
}

export function coachFeedDiscussionQuestion(item, locale = "nl") {
  const symbol = String(item?.symbol || "").trim().toUpperCase();
  const pair = String(item?.evidence?.trading_pair || "").trim().toUpperCase();
  const asset = pair.startsWith(`${symbol}/`) ? pair : symbol;
  const title = String(item?.title || "").trim();
  const setupName = String(item?.evidence?.setup_name || "").trim();
  const setup = setupName ? `'${setupName}'` : asset;
  const pairUnset = item?.evidence?.trading_pair_status === "not_saved_on_setup";
  const exactWatchlistPair = pair.startsWith(`${symbol}/`);
  const week = String(item?.evidence?.week_start || "").trim();
  const reportDate = String(item?.evidence?.report_date || "").trim();
  const reportPair = String(item?.evidence?.attention_pair || "").trim().toUpperCase();
  const reportType = String(item?.evidence?.report_type || "daily").trim();
  const reportName = {
    daily: ["dag", "daily", "Tages"], weekly: ["week", "weekly", "Wochen"],
    monthly: ["maand", "monthly", "Monats"], quarterly: ["kwartaal", "quarterly", "Quartals"],
  }[reportType] || ["", "", ""];
  const labels = {
    nl: {
      bot: `Bespreek dit opgeslagen Paper-botbesluit voor ${asset}: ${title}. Controleer de beslissing, opgeslagen regels en eventuele uitvoering in de botgeschiedenis. Leg uit waarom de bot wel of niet handelde en adviseer één concrete vervolgstap. Gebruik geen actuele koers als bewijs voor een historische uitvoering; wijzig niets.`,
      exit: `Controleer deze uitgevoerde Paper-verkoop voor ${asset} in de botgeschiedenis, order en portefeuille. Leg uit of de positie echt is gesloten en bied dan één korte reflectievraag aan. Gebruik geen actuele koers als bewijs voor de uitvoering; wijzig niets.`,
      risk: `Bespreek deze Paper-positierisicokaart voor ${asset}: ${title}. Vergelijk de huidige, opnieuw gelezen positieconcentratie met de opgeslagen botlimiet en noem het waarderingsmoment. Als de actuele waardering ontbreekt, zeg welke bron ontbreekt. Adviseer één concrete controle; wijzig geen bot of positie.`,
      plan: `Bespreek deze planupdate voor setup ${setup} (${asset}): ${title}. Lees de opgeslagen setup en bijbehorende score.${pair ? " Gebruik dit exacte handelspaar." : " Als bij de setup geen handelspaar is opgeslagen, zeg dat expliciet en kies er niet zelf een."}`,
      data: `Bespreek deze melding over ontbrekend scorebewijs voor ${setupName ? `setup ${setup}` : asset}: ${title}. Controleer de opgeslagen setup, bronstatus en score.${pair ? ` Gebruik ${pair} als exact handelspaar.` : pairUnset ? " Zeg expliciet dat bij deze setup geen handelspaar is opgeslagen." : " Leid geen handelspaar af uit alleen het assetsymbool."}`,
      weekly: `Bespreek mijn opgeslagen weekreflectie${week ? ` van ${week}` : ""}. Lees de afgesloten trades en noem alleen patronen die door de dossiers zijn onderbouwd.`,
      report: `Bespreek het opgeslagen ${reportName[0]}rapport van ${reportDate} en het aandachtspunt voor ${reportPair}. Lees dat rapport opnieuw, onderscheid de momentopname van actuele Analyse en geef één controleerbare vervolgstap. Als dit rapport ontbreekt, zeg dat expliciet. Wijzig niets.`,
      watchlist: `Bekijk mijn watchlist-notering ${asset}. Controleer de huidige indicatoren en benchmark ${exactWatchlistPair ? "voor dit exacte handelspaar" : "voor deze asset; leid geen handelspaar af"} en adviseer welke volgende analysestap logisch is. Doe alleen een voorstel; wijzig of sla niets op.`,
      analysis: `Controleer de actuele benchmark en bronmomenten voor ${asset}. Adviseer of een setup een logische volgende stap is en welke keuze nog van mij nodig is. Maak niets aan.`,
      strategy: `Controleer of setup ${setup} voor ${asset} nog bestaat en of er inmiddels een strategie aan is gekoppeld. Zo niet, adviseer welke strategie past en welke gegevens je van mij nodig hebt. Maak niets aan.`,
      paper: `Controleer de opgeslagen strategie voor setup ${setup} (${asset}), of er inmiddels een bot bestaat en of de strategie uitvoerbaar is. Adviseer alleen of een Paper-proef logisch is en welke risico-instellingen ik eerst moet kiezen. Activeer of verhandel niets.`,
      other: `Bespreek deze melding voor ${asset || "mijn account"}: ${title}. Lees de bijbehorende bron en actuele status opnieuw.`,
    },
    en: {
      bot: `Discuss this saved Paper bot decision for ${asset}: ${title}. Check the decision, saved rules and any execution in bot history. Explain why the bot did or did not act and suggest one concrete next step. Do not use a current quote as proof of a historical execution; change nothing.`,
      exit: `Check this executed Paper sale for ${asset} in bot history, order and portfolio. Explain whether the position is actually closed, then offer one short reflection question. Do not use a current quote as execution evidence; change nothing.`,
      risk: `Discuss this Paper position risk card for ${asset}: ${title}. Compare the current, freshly read position concentration with the saved bot limit and state the valuation time. If the current valuation is unavailable, name the missing source. Suggest one concrete check; change no bot or position.`,
      plan: `Discuss this plan update for setup ${setup} (${asset}): ${title}. Read the saved setup and related score.${pair ? " Use this exact trading pair." : " If no trading pair is saved on the setup, say so explicitly and do not choose one."}`,
      data: `Discuss this missing score evidence for ${setupName ? `setup ${setup}` : asset}: ${title}. Check the saved setup, source status and score.${pair ? ` Use ${pair} as the exact trading pair.` : pairUnset ? " State explicitly that this setup has no saved trading pair." : " Do not infer a trading pair from the asset symbol alone."}`,
      weekly: `Discuss my saved weekly reflection${week ? ` for ${week}` : ""}. Read the closed trades and mention only patterns supported by the records.`,
      report: `Discuss the saved ${reportName[1]} report from ${reportDate} and its attention point for ${reportPair}. Read that report again, distinguish its snapshot from current Analysis and give one verifiable next step. Say so if the report is unavailable. Change nothing.`,
      watchlist: `Review my watchlist listing ${asset}. Check the current indicators and benchmark ${exactWatchlistPair ? "for this exact trading pair" : "for this asset; do not infer a trading pair"} and suggest a logical next analysis step. Only advise; do not change or save anything.`,
      analysis: `Check the current benchmark and source times for ${asset}. Advise whether a setup is a logical next step and what choice you still need from me. Create nothing.`,
      strategy: `Check whether setup ${setup} for ${asset} still exists and whether a strategy is linked now. If not, advise which strategy fits and what details you need from me. Create nothing.`,
      paper: `Check the saved strategy for setup ${setup} (${asset}), whether a bot now exists and whether the strategy is execution ready. Only advise whether a Paper trial is sensible and which risk settings I should choose first. Activate or trade nothing.`,
      other: `Discuss this update for ${asset || "my account"}: ${title}. Recheck its source and current status.`,
    },
    de: {
      bot: `Besprich diese gespeicherte Paper-Botentscheidung für ${asset}: ${title}. Prüfe Entscheidung, gespeicherte Regeln und Ausführung in der Bot-Historie. Erkläre, warum der Bot handelte oder nicht, und empfehle einen konkreten nächsten Schritt. Verwende keinen aktuellen Kurs als Beleg für eine frühere Ausführung; ändere nichts.`,
      exit: `Prüfe diesen ausgeführten Paper-Verkauf für ${asset} in Bot-Historie, Order und Portfolio. Erkläre, ob die Position wirklich geschlossen ist, und stelle dann eine kurze Reflexionsfrage. Verwende keinen aktuellen Kurs als Ausführungsbeleg; ändere nichts.`,
      risk: `Besprich diese Paper-Positionsrisikokarte für ${asset}: ${title}. Vergleiche die erneut gelesene aktuelle Positionskonzentration mit dem gespeicherten Bot-Limit und nenne den Bewertungszeitpunkt. Wenn die aktuelle Bewertung fehlt, nenne die fehlende Quelle. Empfiehl eine konkrete Prüfung; ändere weder Bot noch Position.`,
      plan: `Besprich diese Planaktualisierung für Setup ${setup} (${asset}): ${title}. Lies das gespeicherte Setup und den zugehörigen Score.${pair ? " Verwende dieses genaue Handelspaar." : " Wenn kein Handelspaar gespeichert ist, sage dies ausdrücklich und wähle keines selbst."}`,
      data: `Besprich diese Meldung über fehlende Score-Daten für ${setupName ? `Setup ${setup}` : asset}: ${title}. Prüfe das gespeicherte Setup, den Quellenstatus und den Score.${pair ? ` Verwende ${pair} als genaues Handelspaar.` : pairUnset ? " Sage ausdrücklich, dass für dieses Setup kein Handelspaar gespeichert ist." : " Leite aus dem Assetsymbol allein kein Handelspaar ab."}`,
      weekly: `Besprich meine gespeicherte Wochenreflexion${week ? ` vom ${week}` : ""}. Lies die abgeschlossenen Trades und nenne nur belegte Muster.`,
      report: `Besprich den gespeicherten ${reportName[2]}bericht vom ${reportDate} und den Hinweis für ${reportPair}. Lies den Bericht erneut, unterscheide die Momentaufnahme von der aktuellen Analyse und nenne einen überprüfbaren nächsten Schritt. Sage ausdrücklich, wenn der Bericht fehlt. Ändere nichts.`,
      watchlist: `Prüfe meine Watchlist-Notierung ${asset}. Prüfe die aktuellen Indikatoren und den Benchmark ${exactWatchlistPair ? "für dieses genaue Handelspaar" : "für diesen Wert; leite kein Handelspaar ab"} und schlage den nächsten sinnvollen Analyseschritt vor. Berate nur; ändere oder speichere nichts.`,
      analysis: `Prüfe den aktuellen Benchmark und die Quellenzeitpunkte für ${asset}. Empfiehl, ob ein Setup ein sinnvoller nächster Schritt ist und welche Entscheidung du von mir brauchst. Erstelle nichts.`,
      strategy: `Prüfe, ob Setup ${setup} für ${asset} noch besteht und inzwischen eine Strategie verknüpft ist. Falls nicht, empfehle eine passende Strategie und nenne die benötigten Angaben. Erstelle nichts.`,
      paper: `Prüfe die gespeicherte Strategie für Setup ${setup} (${asset}), ob inzwischen ein Bot existiert und ob die Strategie ausführbar ist. Berate nur, ob ein Paper-Test sinnvoll ist und welche Risikoeinstellungen ich zuerst wählen sollte. Aktiviere oder handle nichts.`,
      other: `Besprich diese Meldung für ${asset || "mein Konto"}: ${title}. Prüfe Quelle und aktuellen Status erneut.`,
    },
  };
  const copy = labels[locale] || labels.nl;
  const kind = item?.event_type === "bot_decision" && item?.evidence?.action === "sell"
    && item?.evidence?.status === "executed" && item?.evidence?.order_status === "filled" ? "exit"
    : item?.event_type === "bot_decision" ? "bot"
    : ["plan_review", "plan_match"].includes(item?.event_type) ? "plan"
      : item?.event_type === "data_blocked" ? "data"
      : item?.event_type === "watchlist_added" ? "watchlist"
      : item?.event_type === "analysis_ready" ? "analysis"
      : item?.event_type === "strategy_next_step" ? "strategy"
      : item?.event_type === "paper_next_step" ? "paper"
      : item?.event_type === "position_risk" ? "risk"
      : item?.event_type?.endsWith("_report_ready") ? "report"
      : item?.event_type === "weekly_reflection" ? "weekly" : "other";
  return copy[kind];
}

export const isDirectCommandSearchMode = (mode) => mode !== "chat";

export function isWorkspaceIndicatorConfigured(workspace, category, indicator) {
  const rows = workspace?.categories?.[category]?.rows;
  const expected = String(indicator || "").trim().toLowerCase();
  return Boolean(expected && Array.isArray(rows) && rows.some((row) =>
    String(row?.name || row?.indicator || "").trim().toLowerCase() === expected
  ));
}

export function resolveFeedDraftQuery(request, query, edit, consumedNonce) {
  if (request?.mode !== "chat" || !request?.context?.feed_item_id ||
      consumedNonce === request.nonce) return query;
  return edit?.nonce === request.nonce ? edit.value : String(request.query || "");
}

export function feedDraftWasEdited(request, submittedQuery) {
  return Boolean(request?.context?.feed_item_id &&
    String(request.query || '').trim() !== String(submittedQuery || '').trim());
}

export function shouldAttachFeedContext(request, submittedQuery, usedNonce) {
  // Selecting a feed item is explicit context, even when the trader rewrites
  // the suggested question. The server rechecks ownership and action bounds.
  return Boolean(
    request?.context?.feed_item_id &&
    request?.nonce &&
    request.nonce !== usedNonce &&
    String(submittedQuery || "").trim()
  );
}

export function selectedFeedItemForSubmission(selection, usedNonce, submittedQuery) {
  return selection?.itemId && selection?.nonce && selection.nonce !== usedNonce
    && String(submittedQuery || "").trim() ? selection.itemId : null;
}

export function openFinnContext({ query, context = {}, autoSubmit = true } = {}) {
  if (typeof window === "undefined") return;
  window.dispatchEvent(
    new CustomEvent(FINN_COMMAND_OPEN_EVENT, {
      detail: {
        mode: "chat",
        query: String(query || "").trim(),
        context,
        autoSubmit,
      },
    })
  );
}

export const FINN_ASSETS = [
  { symbol: "BTC", name: "Bitcoin", icon: "₿", assetClass: "crypto" },
  { symbol: "ETH", name: "Ethereum", icon: "Ξ", assetClass: "crypto" },
  { symbol: "SOL", name: "Solana", icon: "S", assetClass: "crypto" },
  { symbol: "XRP", name: "XRP", icon: "X", assetClass: "crypto" },
  { symbol: "LINK", name: "Chainlink", icon: "L", assetClass: "crypto" },
  { symbol: "ADA", name: "Cardano", icon: "A", assetClass: "crypto" },
  { symbol: "DOT", name: "Polkadot", icon: "P", assetClass: "crypto" },
  { symbol: "MSTR", name: "Strategy Inc.", icon: "M", assetClass: "stock" },
  { symbol: "COIN", name: "Coinbase Global, Inc.", icon: "C", assetClass: "stock" },
  { symbol: "MARA", name: "MARA Holdings, Inc.", icon: "M", assetClass: "stock" },
  { symbol: "RIOT", name: "Riot Platforms, Inc.", icon: "R", assetClass: "stock" },
  { symbol: "CLSK", name: "CleanSpark, Inc.", icon: "C", assetClass: "stock" },
  { symbol: "HUT", name: "Hut 8 Corp.", icon: "H", assetClass: "stock" },
  { symbol: "BTDR", name: "Bitdeer Technologies Group", icon: "B", assetClass: "stock" },
  { symbol: "WULF", name: "TeraWulf Inc.", icon: "W", assetClass: "stock" },
  { symbol: "CORZ", name: "Core Scientific, Inc.", icon: "C", assetClass: "stock" },
  { symbol: "AAPL", name: "Apple Inc.", icon: "A", assetClass: "stock" },
  { symbol: "MSFT", name: "Microsoft Corporation", icon: "M", assetClass: "stock" },
  { symbol: "SPY", name: "SPDR S&P 500 ETF Trust", icon: "S", assetClass: "etf" },
  { symbol: "QQQ", name: "Invesco QQQ Trust", icon: "Q", assetClass: "etf" },
  { symbol: "IBIT", name: "iShares Bitcoin Trust ETF", icon: "I", assetClass: "etf" },
  { symbol: "FBTC", name: "Fidelity Wise Origin Bitcoin Fund", icon: "F", assetClass: "etf" },
  { symbol: "GLD", name: "SPDR Gold Shares", icon: "G", assetClass: "etf" },
];

export function matchesAssetGroup(asset, group) {
  if (!group) return true;
  const assetClass = String(asset?.assetClass || "").toLowerCase();
  if (group === "stocks") return assetClass === "stock";
  if (group === "etfs") return assetClass === "etf";
  if (group === "crypto") return assetClass === "crypto";
  return false;
}

export function buildExactPairOptions(assets, marketsBySymbol, query = "") {
  return assets.filter((asset) => asset.assetClass === "crypto").flatMap((asset) =>
    (marketsBySymbol[asset.symbol] || [])
      .filter((market) => matchesCommandQuery(`${market.pair} ${asset.symbol} ${asset.name}`, query))
      .map((market) => ({ asset, market }))
  );
}

const COMMAND_WORDS = new Set([
  "add",
  "aan",
  "als",
  "an",
  "analyse",
  "asset",
  "bei",
  "bitte",
  "de",
  "der",
  "die",
  "een",
  "for",
  "find",
  "für",
  "ga",
  "go",
  "het",
  "in",
  "mijn",
  "my",
  "naar",
  "offne",
  "open",
  "search",
  "select",
  "selecteer",
  "set",
  "stel",
  "the",
  "toe",
  "to",
  "voeg",
  "wechsel",
  "wissel",
  "zoek",
  "suche",
  "kies",
  "zu",
  "zum",
]);

export function normalizeCommandText(value) {
  return String(value || "")
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, " ")
    .trim();
}

export function getCommandTokens(query) {
  const tokens = normalizeCommandText(query)
    .split(/\s+/)
    .filter(Boolean);
  const meaningful = tokens.filter((token) => !COMMAND_WORDS.has(token));
  return meaningful.length > 0 ? meaningful : tokens;
}

export function matchesCommandQuery(candidate, query) {
  const tokens = getCommandTokens(query);
  if (tokens.length === 0) return true;
  const haystack = normalizeCommandText(candidate);
  return tokens.every((token) => haystack.includes(token));
}

export function getDefaultIndicatorCategory(pathname) {
  if (pathname === "/macro") return "macro";
  if (pathname === "/market") return "market";
  return "technical";
}

export function isExactMarketInWatchlist(items, marketId) {
  return (items || []).some((item) =>
    item?.market_id != null && String(item.market_id) === String(marketId)
  );
}
