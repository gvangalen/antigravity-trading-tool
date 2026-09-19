const EXECUTION_MODE_LABELS = Object.freeze({
  nl: Object.freeze({ fixed: "Vast bedrag", custom: "Aangepast" }),
  en: Object.freeze({ fixed: "Fixed amount", custom: "Custom" }),
  de: Object.freeze({ fixed: "Fester Betrag", custom: "Benutzerdefiniert" }),
});

export function normalizeProductLocale(locale) {
  const language = String(locale || "nl").trim().toLowerCase().split(/[-_]/, 1)[0];
  return Object.hasOwn(EXECUTION_MODE_LABELS, language) ? language : "nl";
}

export function formatExecutionMode(value, locale = "nl") {
  const normalized = String(value || "").trim().toLowerCase();
  if (!normalized) return "";
  return EXECUTION_MODE_LABELS[normalizeProductLocale(locale)][normalized] || "";
}
