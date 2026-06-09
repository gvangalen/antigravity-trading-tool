'use client';

import { fetchAuth } from '@/lib/api/auth';

const SESSION_STORAGE_KEY = 'tradamind_assistant_session_id';

export function getAssistantSessionId() {
  if (typeof window === 'undefined') return 'server-session';
  const existing = window.sessionStorage.getItem(SESSION_STORAGE_KEY);
  if (existing) return existing;
  const created = `sess-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
  window.sessionStorage.setItem(SESSION_STORAGE_KEY, created);
  return created;
}

export function trackAssistantEvent(event = {}) {
  const payload = {
    session_id: getAssistantSessionId(),
    surface: 'web',
    ...event,
  };

  return fetchAuth('/api/assistant/analytics/events', {
    method: 'POST',
    body: JSON.stringify(payload),
  }).catch((error) => {
    console.warn('Assistant analytics event failed', payload.event_name, error);
    return null;
  });
}
