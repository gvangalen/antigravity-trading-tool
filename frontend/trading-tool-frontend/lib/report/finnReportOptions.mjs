export const FINN_REPORT_TYPE_KEYS = ["today", "week", "blocked", "behavior"];

export const FALLBACK_FINN_REPORT_OPTIONS = [
  {
    key: "today",
    label: "Today",
    eyebrow: "Daily reflection",
    prompt: "Give me my Finn report for today",
    empty: "No Finn activity is available yet.",
  },
];

export function getFinnReportOptions(finnOptions = {}) {
  return FINN_REPORT_TYPE_KEYS
    .map((key) => ({ key, ...(finnOptions?.[key] || {}) }))
    .filter((option) => option.label && option.prompt);
}

export function resolveFinnReportOptions(finnOptions = {}) {
  const options = getFinnReportOptions(finnOptions);
  return options.length ? options : FALLBACK_FINN_REPORT_OPTIONS;
}

export function resolveActiveFinnReportOption(options = [], activeKey = "today") {
  return options.find((option) => option.key === activeKey) || options[0] || FALLBACK_FINN_REPORT_OPTIONS[0];
}
