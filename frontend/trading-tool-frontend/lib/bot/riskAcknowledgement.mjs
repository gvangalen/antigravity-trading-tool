export function getBotRiskAcknowledgement(error) {
  if (error?.status !== 409 || typeof error?.body !== "string") {
    return null;
  }

  try {
    const body = JSON.parse(error.body);
    const detail = body?.detail;
    if (detail?.code !== "BOT_RISK_ACK_REQUIRED") {
      return null;
    }

    return {
      code: detail.code,
      message: typeof detail.message === "string" ? detail.message : "",
      behavioralEvent: detail.behavioral_event ?? null,
    };
  } catch {
    return null;
  }
}

export function getBotSaveErrorMessage(error, fallback) {
  const acknowledgement = getBotRiskAcknowledgement(error);
  if (acknowledgement?.message) {
    return acknowledgement.message;
  }

  if (typeof error?.body === "string") {
    try {
      const parsed = JSON.parse(error.body);
      if (typeof parsed?.detail === "string" && parsed.detail.trim()) {
        return parsed.detail.trim();
      }
    } catch {
      // Use the fallback for non-JSON error payloads.
    }
  }

  if (typeof error?.message === "string" && error.message.trim()) {
    return error.message.trim();
  }

  return fallback;
}
