export function getBotApiErrorMessage(error, fallback) {
  try {
    const detail = JSON.parse(error?.body || "{}").detail;
    if (typeof detail === "string" && detail.trim()) return detail;
    if (typeof detail?.message === "string" && detail.message.trim()) return detail.message;
  } catch {}
  return error?.message && error.message !== "API request failed" ? error.message : fallback;
}
