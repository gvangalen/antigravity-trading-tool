const REPORT_TYPES = new Set(["daily_report_ready", "periodic_report_ready", "weekly_reflection"]);

export function visibleCoachFeedItems(items, now = Date.now()) {
  const first = items.slice(0, 3);
  const report = items.find((item) => {
    const age = now - Date.parse(item.created_at);
    return REPORT_TYPES.has(item.event_type) && item.status === "unread" &&
      Number.isFinite(age) && age >= 0 && age <= 36 * 60 * 60 * 1000;
  });
  return report && !first.some((item) => item.id === report.id)
    ? [...first.slice(0, 2), report] : first;
}
