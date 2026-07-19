export const FINN_COMMAND_OPEN_EVENT = "finn-command-search:open";
export const FINN_INDICATOR_MODAL_OPEN_EVENT = "finn-indicator-config:open";
export const FINN_INDICATOR_MODAL_COMPLETED_EVENT = "finn-indicator-config:completed";

export const FINN_ASSETS = [
  { symbol: "BTC", name: "Bitcoin", icon: "₿" },
  { symbol: "ETH", name: "Ethereum", icon: "Ξ" },
  { symbol: "SOL", name: "Solana", icon: "S" },
  { symbol: "ADA", name: "Cardano", icon: "A" },
  { symbol: "DOT", name: "Polkadot", icon: "P" },
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
