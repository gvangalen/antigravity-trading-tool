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
