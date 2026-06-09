import { analyticsApi } from './tradamindApi';

let sessionId: string | null = null;

export function getAssistantSessionId() {
  if (sessionId) return sessionId;
  sessionId = `mobile-sess-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
  return sessionId;
}

export async function trackAssistantEvent(event: Parameters<typeof analyticsApi.track>[0]) {
  try {
    await analyticsApi.track({
      session_id: getAssistantSessionId(),
      surface: 'mobile',
      ...event,
    });
  } catch (error) {
    console.warn('Assistant analytics event failed', event.event_name, error);
  }
}
