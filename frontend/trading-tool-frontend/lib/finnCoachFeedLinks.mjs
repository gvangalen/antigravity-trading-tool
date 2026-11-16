export function coachFeedDetailsHref(item = {}) {
  if (item.subject_type === "report") {
    return `/report?type=${encodeURIComponent(item.evidence?.report_type || "daily")}&date=${encodeURIComponent(item.evidence?.report_date || "")}`;
  }
  if (item.subject_type === "reflection") {
    return `/report?reflection_week=${encodeURIComponent(item.evidence?.week_start || "")}#finn-trades-title`;
  }
  if (item.subject_type === "setup") {
    return `/setup?symbol=${encodeURIComponent(item.symbol || "")}&setup_id=${encodeURIComponent(item.subject_id || "")}`;
  }
  if (item.subject_type === "bot") {
    const base = `/bot?symbol=${encodeURIComponent(item.symbol || "")}&bot_id=${encodeURIComponent(item.subject_id || "")}`;
    return item.event_type === "data_blocked" &&
      Object.values(item.evidence?.missing_indicators || {}).some((names) => Array.isArray(names) && names.length)
      ? `${base}&focus=trade` : base;
  }
  const pair = String(item.evidence?.trading_pair || "").toUpperCase();
  const quote = pair.startsWith(`${String(item.symbol || "").toUpperCase()}/`)
    ? pair.split("/")[1] : null;
  const base = `/asset?symbol=${encodeURIComponent(item.symbol || "")}`;
  return item.evidence?.market_id && /^[A-Z]{2,12}$/.test(quote || "")
    ? `${base}&variant=v3&tab=market&quote=${encodeURIComponent(quote)}` : base;
}
