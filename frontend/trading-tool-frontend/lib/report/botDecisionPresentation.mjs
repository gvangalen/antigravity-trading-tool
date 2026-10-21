export function recordedBotDecision(snapshot) {
  let value = snapshot;
  if (typeof value === "string") {
    try {
      value = JSON.parse(value);
    } catch {
      return null;
    }
  }
  if (Array.isArray(value)) value = value[0];
  if (!value || typeof value !== "object" || Array.isArray(value)) return null;
  if (typeof value.action !== "string" || !value.action.trim()) return null;
  return value;
}
