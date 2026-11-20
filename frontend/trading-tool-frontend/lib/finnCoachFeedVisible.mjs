function activityTime(item) {
  const value = Date.parse(item.activity_at || item.created_at);
  return Number.isFinite(value) ? value : 0;
}

export function visibleCoachFeedItems(items) {
  return items.filter((item) => item.status === "unread")
    .sort((a, b) => Number(Number(b.priority) >= 4) - Number(Number(a.priority) >= 4) ||
      activityTime(b) - activityTime(a) ||
      String(b.id).localeCompare(String(a.id)))
    .slice(0, 3);
}
