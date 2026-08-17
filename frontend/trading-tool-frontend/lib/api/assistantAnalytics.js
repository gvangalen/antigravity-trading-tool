'use client';

import { fetchAuth } from '@/lib/api/auth';

const SESSION_STORAGE_KEY = 'tradamind_assistant_session_id';

function scopedAssistantSessionStorageKey(scope = "anonymous") {
  const normalized = String(scope || "anonymous").trim() || "anonymous";
  return `${SESSION_STORAGE_KEY}:${normalized}`;
}

export function getAssistantSessionId(scope = "anonymous") {
  if (typeof window === 'undefined') return 'server-session';
  const storageKey = scopedAssistantSessionStorageKey(scope);
  const existing = window.sessionStorage.getItem(storageKey);
  if (existing) return existing;
  const created = `sess-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
  window.sessionStorage.setItem(storageKey, created);
  return created;
}

export function trackAssistantEvent(event = {}) {
  const sessionScope = event.user_id || event.userId || event.scope || "anonymous";
  const payload = {
    session_id: getAssistantSessionId(sessionScope),
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
