'use client';

import { fetchAuth } from '@/lib/api/auth';  // ✅ JUISTE AUTH
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
export const assistantChat = (query, context = {}) => {
  return fetchAuth(`/api/assistant/chat`, {
    method: 'POST',
    body: JSON.stringify({ query, context }),
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
