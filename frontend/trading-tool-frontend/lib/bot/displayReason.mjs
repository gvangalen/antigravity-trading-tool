export function firstDisplayReason(value) {
  const candidates = Array.isArray(value)
    ? value
    : value && typeof value === "object"
      ? [value.reason, value.message, value.detail]
      : [];
  return candidates.find((item) =>
    typeof item === "string" && item.trim() && !["{}", "[]", "null"].includes(item.trim())
  )?.trim();
}
