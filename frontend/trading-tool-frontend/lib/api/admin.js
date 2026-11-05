import { fetchAuth } from '@/lib/api/auth';

/**
 * Haalt alle AI statistieken op voor het admin dashboard.
 * Vereist rol: 'admin'
 */
export const fetchAdminAiStats = () => {
  return fetchAuth(`/api/admin/ai/stats`, {
    method: 'GET',
  });
};

/**
 * Haalt alle gebruikers op voor het admin dashboard.
 * Vereist rol: 'admin'
 */
export const fetchAdminUsers = ({ offset = 0, limit = 50, search = '', plan = 'all' } = {}) => {
  const query = new URLSearchParams({ offset, limit, search, plan });
  return fetchAuth(`/api/admin/users/page?${query}`, {
    method: 'GET',
  });
};

export const fetchAdminFinnV2Overview = () => {
  return fetchAuth('/api/admin/finn-v2/overview', { method: 'GET' });
};

/**
 * Update een gebruiker (plan, limiet, status) door een admin.
 */
export const updateAdminUser = (userId, updates) => {
  return fetchAuth(`/api/admin/users/${userId}`, {
    method: 'PATCH',
    body: JSON.stringify(updates)
  });
};

/**
 * Haalt systeemlogs op met filters.
 */
export const fetchAdminLogs = (filters = {}, options = {}) => {
  const query = new URLSearchParams(filters).toString();
  return fetchAuth(`/api/admin/logs?${query}`, {
    method: 'GET',
    ...options,
  });
};

/**
 * Analyseert recente logs met AI.
 */
export const analyzeAdminLogs = () => {
  return fetchAuth(`/api/admin/logs/analyze`, {
    method: 'POST',
  });
};

export const fetchSystemHealth = () => {
  return fetchAuth(`/api/system/health`, {
    method: 'GET',
  });
};

export const fetchFinnAnalytics = () => {
  return fetchAuth(`/api/system/finn-analytics`, {
    method: 'GET',
  });
};

export const fetchOpenAiRuntime = () => {
  return fetchAuth(`/api/system/openai-runtime`, {
    method: 'GET',
  });
};

export const fetchAdminTelemetry = async () => {
  const [analytics, openaiRuntime, finnV2] = await Promise.allSettled([
    fetchFinnAnalytics(),
    fetchOpenAiRuntime(),
    fetchAdminFinnV2Overview(),
  ]);
  if (analytics.status === 'rejected') throw analytics.reason;
  return {
    analytics: analytics.value,
    openaiRuntime: openaiRuntime.status === 'fulfilled' ? openaiRuntime.value : null,
    finnV2: finnV2.status === 'fulfilled' ? finnV2.value : null,
  };
};
