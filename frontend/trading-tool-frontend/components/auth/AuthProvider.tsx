"use client";

import {
  createContext,
  useContext,
  useState,
  useEffect,
  useCallback,
  useRef,
} from "react";

import { API_BASE_URL } from "@/lib/config";
import {
  saveUserLocal,
  loadUserLocal,
} from "@/lib/api/user";
import {
  buildAuthHeaders,
  storeAuthTokens,
  clearStoredAuth,
  apiRefresh,
} from "@/lib/api/auth";
import { getActiveLocale, normalizeLocale } from "@/lib/i18n";

/* ===========================================================
   CONTEXT
=========================================================== */
const AuthContext = createContext(null);

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) {
    throw new Error("useAuth must be used inside <AuthProvider>");
  }
  return ctx;
}

/* ===========================================================
   fetchWithAuth
=========================================================== */
async function fetchWithAuth(
  url: string,
  options: RequestInit = {}
): Promise<Response> {
  const method = String(options.method || "GET").toUpperCase();
  return fetch(url, {
    credentials: "include",
    headers: {
      ...Object.fromEntries(
        buildAuthHeaders({
          "Content-Type": "application/json",
          ...(options.headers ?? {}),
        }, method).entries()
      ),
    },
    ...options,
  });
}

/* ===========================================================
   AUTH PROVIDER
=========================================================== */
export function AuthProvider({ children }) {
  // localStorage is alleen hint (snellere UX)
  const initialUser = loadUserLocal() ?? null;

  const [user, setUser] = useState(initialUser);
  const [loading, setLoading] = useState(true);
  const [sessionChecked, setSessionChecked] = useState(false);

  const sessionInFlight = useRef(false);
  const abortRef = useRef<AbortController | null>(null);

  const fetchCurrentUser = useCallback(async (signal?: AbortSignal) => {
    return fetch(`${API_BASE_URL}/api/auth/me`, {
      credentials: "include",
      headers: Object.fromEntries(
        buildAuthHeaders({ "Content-Type": "application/json" }, "GET").entries()
      ),
      signal,
    });
  }, []);

  /* -------------------------------------------------------
     SESSION CHECK (/me)
  ------------------------------------------------------- */
  const loadSession = useCallback(async () => {
    // We don't return early here anymore to allow Strict Mode double-invocation 
    // to correctly abort the first and finish the second.
    sessionInFlight.current = true;

    if (abortRef.current) {
      abortRef.current.abort();
    }

    const controller = new AbortController();
    abortRef.current = controller;

    try {
      let res = await fetchCurrentUser(controller.signal);

      if (res.status === 401) {
        const refreshed = await apiRefresh();
        if (refreshed.success && !controller.signal.aborted) {
          res = await fetchCurrentUser(controller.signal);
        }
      }

      if (res.ok) {
        const u = await res.json();
        setUser(u);
        saveUserLocal(u);
      } else {
        setUser(null);
        clearStoredAuth();
      }
      
      // ✅ Definitive result from server
      setSessionChecked(true);

    } catch (err: any) {
      if (err?.name !== "AbortError") {
        console.error("❌ Auth /me error:", err);
        setUser(null);
        clearStoredAuth();
        setSessionChecked(true); // Fout telt ook als 'gechecked'
      }
    } finally {
      // Alleen loading dichten als dit nog steeds de actieve check is
      if (abortRef.current === controller) {
        sessionInFlight.current = false;
        setLoading(false);
      }
    }
  }, [fetchCurrentUser]);

  /* -------------------------------------------------------
     INIT (1x)
  ------------------------------------------------------- */
  useEffect(() => {
    loadSession();

    return () => {
      if (abortRef.current) {
        abortRef.current.abort();
      }
    };
  }, [loadSession]);

  /* -------------------------------------------------------
     TOKEN REFRESH (veilig)
  ------------------------------------------------------- */
  useEffect(() => {
    const interval = setInterval(async () => {
      try {
        await fetchWithAuth(`${API_BASE_URL}/api/auth/refresh`, {
          method: "POST",
        });
      } catch {
        // refresh mag stil falen
      }
    }, 50 * 60 * 1000);

    return () => clearInterval(interval);
  }, []);

  /* -------------------------------------------------------
     LOGIN  ✅ FIXED
  ------------------------------------------------------- */
  const login = useCallback(async (email: string, password: string, locale?: string | null) => {
    try {
      const normalizedLocale = normalizeLocale(locale) || getActiveLocale(typeof window !== "undefined" ? window : undefined);
      const res = await fetchWithAuth(`${API_BASE_URL}/api/auth/login`, {
        method: "POST",
        body: JSON.stringify({ email, password, locale: normalizedLocale }),
      });

      if (!res.ok) {
        const body = await res.json().catch(() => null);
        return {
          success: false,
          message: res.status === 401
            ? "E-mail of wachtwoord klopt niet."
            : body?.detail || "Login server reageert niet goed. Probeer opnieuw.",
        };
      }

      const data = await res.json().catch(() => ({}));
      storeAuthTokens({
        access_token: data?.access_token,
        refresh_token: data?.refresh_token,
      });
      const loginUser = data?.user ?? null;

      if (loginUser) {
        setUser(loginUser);
        saveUserLocal(loginUser);
      }
      setSessionChecked(true);
      setLoading(false);

      // 📳 Haptic Success
      import("@/lib/haptics").then(({ hapticFeedback }) => {
        hapticFeedback.notification();
      });

      return { success: true };
    } catch (err) {
      console.error("❌ Login fout:", err);
      return {
        success: false,
        message: typeof navigator !== "undefined" && !navigator.onLine
          ? "Je lijkt offline. Controleer je internetverbinding."
          : "Kan de server niet bereiken. Probeer opnieuw.",
      };
    }
  }, []);

  /* -------------------------------------------------------
     LOGOUT
  ------------------------------------------------------- */
  const logout = useCallback(async () => {
    setUser(null);
    clearStoredAuth();

    try {
      await fetchWithAuth(`${API_BASE_URL}/api/auth/logout`, {
        method: "POST",
      });
      
      // 📳 Haptic Feedback
      import("@/lib/haptics").then(({ hapticFeedback }) => {
        hapticFeedback.impact();
      });

    } catch {
      /* stil */
    }
  }, []);

  /* -------------------------------------------------------
     CONTEXT VALUE
  ------------------------------------------------------- */
  const value = {
    user,
    loading,
    sessionChecked,
    isAuthenticated: !!user,
    login,
    logout,
    fetchWithAuth,
    reload: loadSession,
  };

  return (
    <AuthContext.Provider value={value}>
      {children}
    </AuthContext.Provider>
  );
}
