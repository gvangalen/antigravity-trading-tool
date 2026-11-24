function activityTime(item) {
  const value = Date.parse(item.activity_at || item.created_at);
  return Number.isFinite(value) ? value : 0;
}

export function visibleCoachFeedItems(items) {
  return [...items].sort((a, b) => activityTime(b) - activityTime(a) ||
      String(b.id).localeCompare(String(a.id)))
    .slice(0, 3);
}
