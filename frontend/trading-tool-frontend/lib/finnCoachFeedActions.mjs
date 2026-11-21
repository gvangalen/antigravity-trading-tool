const ACTIVE_STATUSES = new Set(["unread", "read"]);

export function canDiscussFeedItem(item, history) {
  if (!item) return false;
  if (item.event_type?.endsWith("_report_ready") &&
      !["benchmark_unavailable", "benchmark_available"].includes(item.evidence?.attention_kind)) return false;
  return ACTIVE_STATUSES.has(item.status) || (history && item.event_type === "data_blocked");
}

export function canUpdateFeedStatus(item) {
  return Boolean(item && ACTIVE_STATUSES.has(item.status));
}
