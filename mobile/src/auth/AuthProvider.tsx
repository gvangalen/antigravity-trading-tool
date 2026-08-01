import { ReactNode, createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';

import { authApi, MobileUser } from '../services/authApi';
import { clearTokens, getAccessToken, saveTokens } from '../services/tokenStorage';
import { assistantApi } from '../services/tradamindApi';
import { extractBackendAppLanguage, setStoredAppLanguage } from '../preferences/appLocale';

type AuthContextValue = {
  user: MobileUser | null;
  initializing: boolean;
  loading: boolean;
  error: string | null;
  login: (email: string, password: string) => Promise<boolean>;
  logout: () => Promise<void>;
  refreshUser: () => Promise<void>;
};

const AuthContext = createContext<AuthContextValue | undefined>(undefined);
const DEFAULT_SIMULATOR_EMAIL = 'gerrit@example.com';
const DEFAULT_SIMULATOR_PASSWORD = 'test123';
const DEV_AUTO_LOGIN_EMAIL =
  process.env.EXPO_PUBLIC_SIMULATOR_AUTO_LOGIN_EMAIL?.trim() ||
  (__DEV__ ? DEFAULT_SIMULATOR_EMAIL : undefined);
const DEV_AUTO_LOGIN_PASSWORD =
  process.env.EXPO_PUBLIC_SIMULATOR_AUTO_LOGIN_PASSWORD?.trim() ||
  (__DEV__ ? DEFAULT_SIMULATOR_PASSWORD : undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<MobileUser | null>(null);
  const [initializing, setInitializing] = useState(true);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [devAutoLoginTried, setDevAutoLoginTried] = useState(false);

  const login = useCallback(async (email: string, password: string) => {
    setLoading(true);
    setError(null);

    try {
      const response = await authApi.login(email.trim(), password);
      if (!response.success || !response.user) {
        throw new Error('Login failed');
      }

      if (response.access_token && response.refresh_token) {
        await saveTokens(response.access_token, response.refresh_token);
        setUser(response.user);
      } else {
        // Local/mobile dev can authenticate through a secure cookie session.
        await clearTokens();
        const nextUser = await authApi.me();
        setUser(nextUser);
      }

      try {
        const preferences = await assistantApi.preferences();
        await setStoredAppLanguage(extractBackendAppLanguage(preferences));
      } catch {
        // Keep the current app language when backend preferences are unavailable.
      }

      return true;
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError.message : 'Login failed');
      await clearTokens();
      setUser(null);
      return false;
    } finally {
      setLoading(false);
    }
  }, []);

  const refreshUser = useCallback(async () => {
    try {
      const nextUser = await authApi.me();
      const token = await getAccessToken();

      if (!token) {
        if (DEV_AUTO_LOGIN_EMAIL && DEV_AUTO_LOGIN_PASSWORD) {
          const relogged = await login(DEV_AUTO_LOGIN_EMAIL, DEV_AUTO_LOGIN_PASSWORD);
          if (relogged) {
            return;
          }
        }

        setUser(null);
        setError('Authentication required');
        return;
      }

      setUser(nextUser);
      setError(null);

      try {
        const preferences = await assistantApi.preferences();
        await setStoredAppLanguage(extractBackendAppLanguage(preferences));
      } catch {
        // Keep the current app language when backend preferences are unavailable.
      }
    } catch {
      const token = await getAccessToken();
      if (token) {
        await clearTokens();
      }
      setUser(null);
    }
  }, [login]);

  useEffect(() => {
    refreshUser().finally(() => setInitializing(false));
  }, [refreshUser]);

  useEffect(() => {
    if (initializing || loading || devAutoLoginTried) {
      return;
    }
    if (!DEV_AUTO_LOGIN_EMAIL || !DEV_AUTO_LOGIN_PASSWORD) {
      return;
    }

    let cancelled = false;

    async function ensureDevSessionHasToken() {
      const token = await getAccessToken();
      if (cancelled || token) {
        return;
      }

      setDevAutoLoginTried(true);
      await login(DEV_AUTO_LOGIN_EMAIL, DEV_AUTO_LOGIN_PASSWORD).catch(() => {
        // Surface login errors through the existing auth state.
      });
    }

    ensureDevSessionHasToken();

    return () => {
      cancelled = true;
    };
  }, [devAutoLoginTried, initializing, loading, login, user]);

  const logout = useCallback(async () => {
    setLoading(true);
    try {
      await authApi.logout();
    } catch {
      // Local logout is still the source of truth for mobile.
    } finally {
      await clearTokens();
      setUser(null);
      setLoading(false);
    }
  }, []);

  const value = useMemo(
    () => ({
      error,
      initializing,
      loading,
      login,
      logout,
      refreshUser,
      user,
    }),
    [error, initializing, loading, login, logout, refreshUser, user],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within AuthProvider');
  }
  return context;
}
