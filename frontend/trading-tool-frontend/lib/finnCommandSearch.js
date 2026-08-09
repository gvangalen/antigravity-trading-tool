export const FINN_COMMAND_OPEN_EVENT = "finn-command-search:open";
export const FINN_INDICATOR_MODAL_OPEN_EVENT = "finn-indicator-config:open";
export const FINN_INDICATOR_MODAL_COMPLETED_EVENT = "finn-indicator-config:completed";

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
