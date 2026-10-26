const TRANSIENT_GATEWAY_STATUSES = new Set([502, 503, 504]);
// Production's phased backend restart has briefly left the single upstream
// unavailable for about 20 seconds. Keep this read-only feed alive through
// that handover while still surfacing a sustained outage after 31 seconds.
const RETRY_DELAYS_MS = [1000, 2000, 4000, 8000, 16000];

export async function readCoachFeedWithRetry(read, { isCurrent = () => true, wait = (ms) => new Promise((resolve) => setTimeout(resolve, ms)) } = {}) {
  for (let attempt = 0; ; attempt += 1) {
    if (!isCurrent()) return null;
    try {
      return await read();
    } catch (error) {
      if (!TRANSIENT_GATEWAY_STATUSES.has(error?.status) || attempt >= RETRY_DELAYS_MS.length || !isCurrent()) {
        throw error;
      }
      await wait(RETRY_DELAYS_MS[attempt]);
    }
  }
}
