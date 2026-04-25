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
export const fetchAdminUsers = () => {
  return fetchAuth(`/api/admin/users`, {
    method: 'GET',
  });
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
export const fetchAdminLogs = (filters = {}) => {
  const query = new URLSearchParams(filters).toString();
  return fetchAuth(`/api/admin/logs?${query}`, {
    method: 'GET',
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
