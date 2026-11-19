const REPORT_TYPES = new Set(["daily_report_ready", "periodic_report_ready", "weekly_reflection"]);
const REPORT_WINDOW_MS = 36 * 60 * 60 * 1000;

function activityTime(item) {
  const value = Date.parse(item.activity_at || item.created_at);
  return Number.isFinite(value) ? value : 0;
}

function attentionRank(item, now) {
  const priority = Math.max(0, Math.min(5, Number(item.priority) || 0));
  if (priority >= 4) return 30 + priority;
  const age = now - Date.parse(item.created_at);
  if (REPORT_TYPES.has(item.event_type) && Number.isFinite(age) &&
      age >= 0 && age <= REPORT_WINDOW_MS) return 25;
  return 20 + priority;
}

export function visibleCoachFeedItems(items, now = Date.now()) {
  // Discussed updates and opened reports live in history. Keep risk and
  // pending confirmations ahead of routine updates and recent reports.
  const ordered = items.filter((item) => item.status === "unread")
    .sort((a, b) => attentionRank(b, now) - attentionRank(a, now) ||
      activityTime(b) - activityTime(a) || String(b.id).localeCompare(String(a.id)));
  const first = ordered.slice(0, 3);
  const report = ordered.find((item) => REPORT_TYPES.has(item.event_type) && attentionRank(item, now) === 25);
  return report && !first.some((item) => item.id === report.id)
    ? [...first.slice(0, 2), report] : first;
}
