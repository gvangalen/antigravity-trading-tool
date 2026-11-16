const ACTIVE_STATUSES = new Set(["unread", "read"]);

export function canDiscussFeedItem(item, history) {
  if (!item || item.event_type?.endsWith("_report_ready")) return false;
  return ACTIVE_STATUSES.has(item.status) || (history && item.event_type === "data_blocked");
}

export function canUpdateFeedStatus(item) {
  return Boolean(item && ACTIVE_STATUSES.has(item.status));
}
