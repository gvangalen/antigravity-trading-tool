import { ReactNode, createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';

import { authApi, MobileUser } from '../services/authApi';
import { clearTokens, getAccessToken, saveTokens } from '../services/tokenStorage';

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

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<MobileUser | null>(null);
  const [initializing, setInitializing] = useState(true);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refreshUser = useCallback(async () => {
    const token = await getAccessToken();
    if (!token) {
      setUser(null);
      return;
    }

    try {
      const nextUser = await authApi.me();
      setUser(nextUser);
      setError(null);
    } catch {
      await clearTokens();
      setUser(null);
    }
  }, []);

  useEffect(() => {
    refreshUser().finally(() => setInitializing(false));
  }, [refreshUser]);

  const login = useCallback(async (email: string, password: string) => {
    setLoading(true);
    setError(null);

    try {
      const response = await authApi.login(email.trim(), password);
      if (!response.success || !response.access_token || !response.refresh_token) {
        throw new Error('Login response is incomplete');
      }
      await saveTokens(response.access_token, response.refresh_token);
      setUser(response.user);
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
