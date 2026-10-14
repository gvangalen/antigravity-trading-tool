const SUPPORTED_LOCALES = new Set(["nl", "en", "de"]);

export function finnSubmissionLocale(renderLocale, documentLanguage) {
  const displayedLocale = String(documentLanguage || "").trim().toLowerCase().split(/[-_]/)[0];
  if (SUPPORTED_LOCALES.has(displayedLocale)) return displayedLocale;
  const fallback = String(renderLocale || "").trim().toLowerCase().split(/[-_]/)[0];
  return SUPPORTED_LOCALES.has(fallback) ? fallback : "nl";
}
