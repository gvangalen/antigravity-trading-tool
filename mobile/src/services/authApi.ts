import { apiClient } from './apiClient';

export type MobileUser = {
  id: number;
  email: string;
  role: string;
  is_active: boolean;
  first_name?: string | null;
  last_name?: string | null;
  ai_plan?: string | null;
  ai_requests_limit_day?: number | null;
  ai_requests_used_day?: number | null;
};

export type LoginResponse = {
  success: boolean;
  user: MobileUser;
  access_token: string;
  refresh_token: string;
};

export type RefreshResponse = {
  success: boolean;
  access_token: string;
};

export const authApi = {
  login(email: string, password: string) {
    return apiClient.request<LoginResponse>('/api/auth/login', {
      body: { email, password },
      method: 'POST',
      skipAuth: true,
      skipRefresh: true,
    });
  },

  me() {
    return apiClient.get<MobileUser>('/api/auth/me');
  },

  logout() {
    return apiClient.request<{ success: boolean }>('/api/auth/logout', {
      method: 'POST',
      skipRefresh: true,
    });
  },
};
