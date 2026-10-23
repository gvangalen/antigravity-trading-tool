export function selectLastBotDecision(todayDecision, history, botId) {
  if (todayDecision?.action) return todayDecision;
  const ownDecisions = (history || []).filter((item) =>
    Number(item?.bot_id) === Number(botId) && !item?.is_trade && item?.action
  );
  const timestamp = (item) => Date.parse(item.decision_ts || item.created_at || item.date || "") || 0;
  return ownDecisions.sort((left, right) =>
    timestamp(right) - timestamp(left)
  )[0] || null;
}
