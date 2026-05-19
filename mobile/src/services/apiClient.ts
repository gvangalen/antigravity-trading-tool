import { clearTokens, getAccessToken, getRefreshToken, saveAccessToken } from './tokenStorage';

const DEFAULT_API_BASE_URL = 'https://tradamind.com';

declare const process: {
  env?: Record<string, string | undefined>;
};

export const API_BASE_URL =
  process.env?.EXPO_PUBLIC_API_BASE_URL?.replace(/\/$/, '') || DEFAULT_API_BASE_URL;

export type ApiRequestOptions = {
  method?: 'GET' | 'POST' | 'PATCH' | 'DELETE';
  body?: unknown;
  query?: Record<string, string | number | boolean | undefined | null>;
  timeoutMs?: number;
  skipAuth?: boolean;
  skipRefresh?: boolean;
};

export class ApiError extends Error {
  status: number;
  payload: unknown;
  isAuthError: boolean;

  constructor(message: string, status: number, payload?: unknown) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.payload = payload;
    this.isAuthError = status === 401 || status === 403;
  }
}

class APIClient {
  async request<T>(path: string, options: ApiRequestOptions = {}): Promise<T> {
    return this.requestInternal<T>(path, options, false);
  }

  private async requestInternal<T>(
    path: string,
    options: ApiRequestOptions,
    didRetry: boolean,
  ): Promise<T> {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), options.timeoutMs ?? 12000);
    const accessToken = options.skipAuth ? null : await getAccessToken();

    try {
      const response = await fetch(this.buildUrl(path, options.query), {
        body: options.body === undefined ? undefined : JSON.stringify(options.body),
        credentials: 'include',
        headers: {
          Accept: 'application/json',
          'Content-Type': 'application/json',
          'X-Tradamind-Client': 'mobile-expo',
          ...(accessToken ? { Authorization: `Bearer ${accessToken}` } : {}),
        },
        method: options.method ?? 'GET',
        signal: controller.signal,
      });

      const payload = await this.parseResponse(response);

      if (!response.ok) {
        if (response.status === 401 && !didRetry && !options.skipRefresh) {
          const refreshed = await this.refreshAccessToken();
          if (refreshed) {
            return this.requestInternal<T>(path, options, true);
          }
        }

        throw new ApiError(this.errorMessage(payload, response.status), response.status, payload);
      }

      return payload as T;
    } catch (error) {
      if (error instanceof ApiError) {
        throw error;
      }

      if (error instanceof Error && error.name === 'AbortError') {
        throw new ApiError('Request timed out', 0);
      }

      throw new ApiError(error instanceof Error ? error.message : 'Network request failed', 0);
    } finally {
      clearTimeout(timeout);
    }
  }

  get<T>(path: string, query?: ApiRequestOptions['query']) {
    return this.request<T>(path, { query });
  }

  post<T>(path: string, body?: unknown, query?: ApiRequestOptions['query']) {
    return this.request<T>(path, { body, method: 'POST', query });
  }

  private buildUrl(path: string, query?: ApiRequestOptions['query']) {
    const normalizedPath = path.startsWith('/') ? path : `/${path}`;
    const url = new URL(`${API_BASE_URL}${normalizedPath}`);

    Object.entries(query ?? {}).forEach(([key, value]) => {
      if (value !== undefined && value !== null && value !== '') {
        url.searchParams.set(key, String(value));
      }
    });

    return url.toString();
  }

  private async parseResponse(response: Response) {
    const text = await response.text();
    if (!text) return null;

    try {
      return JSON.parse(text);
    } catch {
      return text;
    }
  }

  private errorMessage(payload: unknown, status: number) {
    if (payload && typeof payload === 'object' && 'detail' in payload) {
      const detail = (payload as { detail?: unknown }).detail;
      if (typeof detail === 'string') return detail;
    }

    return status === 401 ? 'Authentication required' : `Request failed with status ${status}`;
  }

  private async refreshAccessToken() {
    const refreshToken = await getRefreshToken();
    if (!refreshToken) return false;

    try {
      const response = await fetch(this.buildUrl('/api/auth/refresh'), {
        body: JSON.stringify({ refresh_token: refreshToken }),
        credentials: 'include',
        headers: {
          Accept: 'application/json',
          'Content-Type': 'application/json',
          'X-Tradamind-Client': 'mobile-expo',
        },
        method: 'POST',
      });

      if (!response.ok) {
        await clearTokens();
        return false;
      }

      const payload = await this.parseResponse(response);
      const accessToken =
        payload && typeof payload === 'object' && 'access_token' in payload
          ? (payload as { access_token?: unknown }).access_token
          : null;

      if (typeof accessToken !== 'string' || !accessToken) {
        await clearTokens();
        return false;
      }

      await saveAccessToken(accessToken);
      return true;
    } catch {
      return false;
    }
  }
}

export const apiClient = new APIClient();
