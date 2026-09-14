/**
 * Converts API validation details into text before they reach react-hot-toast.
 * FastAPI can return `{ loc, msg, type }` objects or arrays for a 4xx response.
 */
export function toSnackbarMessage(message, fallback = "Er is iets misgegaan.") {
  if (typeof message === "string") {
    return message.trim() || fallback;
  }

  if (typeof message === "number") {
    return String(message);
  }

  if (Array.isArray(message)) {
    return toSnackbarMessage(message[0], fallback);
  }

  if (message && typeof message === "object") {
    const detail = message.detail ?? message.message ?? message.msg;
    if (typeof detail === "string" && detail.trim()) {
      return detail;
    }
  }

  return fallback;
}
