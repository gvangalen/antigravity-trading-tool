'use client';

import { buildAuthHeaders, fetchAuth } from '@/lib/api/auth';  // ✅ JUISTE AUTH
import { API_BASE_URL } from '@/lib/config';

//
// ========================================
// 🧠 1. Genereer AI-uitleg voor een setup
// ========================================
// Backend verwacht: { name, indicators, trend }
export const generateAIExplanation = ({ name, indicators, trend }) => {
  return fetchAuth(`/api/ai/explain_setup`, {
    method: 'POST',
    body: JSON.stringify({ name, indicators, trend }),
  });
};


//
// ========================================
// 🤖 2. Genereer AI-strategie van volledige setup
// ========================================
// Backend verwacht het volledige setup-object
export const generateAIStrategy = (setup) => {
  return fetchAuth(`/api/ai/strategy`, {
    method: 'POST',
    body: JSON.stringify(setup),
  });
};


//
// ========================================
// 📊 3. Haal AI-score op voor asset (default BTC)
// ========================================
export const fetchAIScore = (symbol = 'BTC') => {
  return fetchAuth(`/api/ai/score?symbol=${symbol}`, {
    method: 'GET',
  });
};

// ========================================
// 💬 4. AI Assistant Chat
// ========================================
export const assistantChat = (query, context = {}, history = [], sessionId = null) => {
  return fetchAuth(`/api/assistant/chat`, {
    method: 'POST',
    body: JSON.stringify({ query, context, history, session_id: sessionId }),
  });
};

export const executeAssistantAction = (action) => {
  const actionId = action?.action_id || action?.id;
  if (!actionId) {
    throw new Error("Deze Finn actie mist een server-issued action_id.");
  }
  return fetchAuth(`/api/assistant/actions/execute`, {
    method: 'POST',
    body: JSON.stringify({ action_id: actionId }),
  });
};

export const fetchFinnState = () => {
  return fetchAuth(`/api/assistant/finn/state`, {
    method: 'GET',
  });
};

export const fetchFinnMissionControl = () => {
  return fetchAuth(`/api/assistant/mission-control`, {
    method: 'GET',
  }).then(async (res) => {
    if (res) return res;

    const fallback = await fetch(`${API_BASE_URL}/api/assistant/mission-control`, {
      method: 'GET',
      credentials: 'include',
      headers: {
        'Content-Type': 'application/json',
      },
    });

    if (!fallback.ok) {
      throw new Error(`Mission Control fallback request failed (${fallback.status})`);
    }

    const text = await fallback.text();
    try {
      return JSON.parse(text);
    } catch (err) {
      console.error('Finn Mission Control fallback JSON parse failed', text.slice(0, 1000));
      throw err;
    }
  });
};

// ========================================
// ⚙️ 5. AI Assistant Preferences
// ========================================
export const getAssistantPreferences = () => {
  return fetchAuth(`/api/assistant/preferences`, {
    method: 'GET',
  });
};

export const updateAssistantPreferences = (preferences) => {
  return fetchAuth(`/api/assistant/preferences`, {
    method: 'PATCH',
    body: JSON.stringify(preferences),
  });
};

// ========================================
// 💡 6. AI Assistant Insight
// ========================================
export const fetchAssistantInsight = (context) => {
  return fetchAuth(`/api/assistant/insight`, {
    method: 'POST',
    body: JSON.stringify(context),
  });
};

// ========================================
// ⚡ 7. Execute Pending AI Action
// ========================================
export const executePendingAction = (actionIdOrAction) => {
  const actionId = typeof actionIdOrAction === 'string'
    ? actionIdOrAction
    : actionIdOrAction?.action_id || actionIdOrAction?.id;
  return fetchAuth(`/api/assistant/actions/execute`, {
    method: 'POST',
    body: JSON.stringify({ action_id: actionId }),
  });
};

// ========================================
// ⚡ 8. AI Assistant Chat Stream (SSE) with Resilience
// ========================================
let activeAbortController = null;

export const assistantChatStream = async (
  query,
  context = {},
  history = [],
  onChunk,
  onEnvelope,
  onError,
  maxRetries = 2,
  sessionId = null,
) => {
  // 1. Cancel previous stream to prevent duplicates & resource leaks
  if (activeAbortController) {
    try {
      activeAbortController.abort();
    } catch (e) {
      console.warn("Aborted previous assistant stream:", e);
    }
  }

  activeAbortController = new AbortController();
  const signal = activeAbortController.signal;

  let attempt = 0;
  let delay = 1000;

  while (attempt <= maxRetries) {
    if (signal.aborted) return;

    try {
      const headers = Object.fromEntries(
        buildAuthHeaders({ 'Content-Type': 'application/json' }, 'POST').entries()
      );

      const response = await fetch(`${API_BASE_URL}/api/assistant/chat/stream`, {
        method: 'POST',
        headers,
        credentials: 'include',
        signal,
        body: JSON.stringify({ query, context, history, session_id: sessionId }),
      });

      if (!response.ok) {
        throw new Error(`Streaming request failed: ${response.statusText}`);
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder('utf-8');
      let buffer = '';

      while (true) {
        if (signal.aborted) {
          try { reader.cancel(); } catch {}
          return;
        }

        const { value, done } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        
        const parts = buffer.split('\n\n');
        buffer = parts.pop() || '';

        for (const part of parts) {
          if (!part.trim()) continue;

          const lines = part.split('\n');
          let event = 'text';
          let data = '';

          for (const line of lines) {
            if (line.startsWith('event:')) {
              event = line.replace('event:', '').trim();
            } else if (line.startsWith('data:')) {
              data = line.replace('data:', '').trim();
            }
          }

          if (event === 'text') {
            onChunk(data);
          } else if (event === 'envelope') {
            try {
              const parsedEnvelope = JSON.parse(data);
              onEnvelope(parsedEnvelope);
            } catch (err) {
              console.error('Error parsing SSE envelope:', err);
            }
          } else if (event === 'error') {
            try {
              const errObj = JSON.parse(data);
              onError(errObj.response || 'An error occurred during streaming.');
            } catch {
              onError(data || 'An error occurred during streaming.');
            }
          }
        }
      }

      // If we finished successfully, clear abort controller reference and break
      if (activeAbortController?.signal === signal) {
        activeAbortController = null;
      }
      return;

    } catch (error) {
      if (error.name === 'AbortError') {
        console.log("Stream fetch explicitly aborted.");
        return;
      }

      console.warn(`Stream attempt ${attempt + 1} failed.`, error);
      attempt++;

      if (attempt <= maxRetries && !signal.aborted) {
        // Wait with exponential backoff before retrying
        await new Promise(resolve => setTimeout(resolve, delay));
        delay *= 2;
      } else {
        console.error('Max streaming retries reached. Failing gracefully.', error);
        if (activeAbortController?.signal === signal) {
          activeAbortController = null;
        }
        onError(error.message || 'Connection failed.');
      }
    }
  }
};
