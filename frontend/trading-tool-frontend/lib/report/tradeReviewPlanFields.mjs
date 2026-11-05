export function visiblePlanFields(entries, labels = {}) {
  return entries.filter(([key, value]) => (
    key !== 'market_id' && Boolean(labels[key]) && value != null && value !== ''
  ));
}
