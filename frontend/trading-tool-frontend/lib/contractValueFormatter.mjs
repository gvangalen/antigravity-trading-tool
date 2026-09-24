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

const RISK_LABELS = Object.freeze({
  nl: Object.freeze({ cautious: "Voorzichtig", conservative: "Voorzichtig", balanced: "Gebalanceerd", moderate: "Gebalanceerd", aggressive: "Offensief" }),
  en: Object.freeze({ cautious: "Cautious", conservative: "Conservative", balanced: "Balanced", moderate: "Balanced", aggressive: "Aggressive" }),
  de: Object.freeze({ cautious: "Vorsichtig", conservative: "Konservativ", balanced: "Ausgewogen", moderate: "Ausgewogen", aggressive: "Offensiv" }),
});

export function formatDraftCardValue(value, locale = "nl") {
  const language = normalizeProductLocale(locale);
  if (value == null) return "";
  if (Array.isArray(value)) return value.map((item) => formatDraftCardValue(item, locale)).filter(Boolean).join(", ");
  if (typeof value === "object") {
    const target = value.target ?? value.price ?? value.target_price ?? value.value;
    return target == null ? "" : formatDraftCardValue(target, locale);
  }
  if (typeof value === "number") return new Intl.NumberFormat(language).format(value);
  const normalized = String(value).trim().toLowerCase();
  return RISK_LABELS[language][normalized] || String(value);
}
