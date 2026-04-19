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
  clearUserLocal,
} from "@/lib/api/user";

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
  return fetch(url, {
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      ...(options.headers ?? {}),
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
      const res = await fetch(`${API_BASE_URL}/api/auth/me`, {
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        signal: controller.signal,
      });

      if (res.ok) {
        const u = await res.json();
        setUser(u);
        saveUserLocal(u);
      } else {
        setUser(null);
        clearUserLocal();
      }
      
      // ✅ Definitive result from server
      setSessionChecked(true);

    } catch (err: any) {
      if (err?.name !== "AbortError") {
        console.error("❌ Auth /me error:", err);
        setUser(null);
        clearUserLocal();
        setSessionChecked(true); // Fout telt ook als 'gechecked'
      }
    } finally {
      // Alleen loading dichten als dit nog steeds de actieve check is
      if (abortRef.current === controller) {
        sessionInFlight.current = false;
        setLoading(false);
      }
    }
  }, []);

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
  const login = useCallback(async (email: string, password: string) => {
    try {
      const res = await fetchWithAuth(`${API_BASE_URL}/api/auth/login`, {
        method: "POST",
        body: JSON.stringify({ email, password }),
      });

      if (!res.ok) {
        return {
          success: false,
          message: "Ongeldige inloggegevens",
        };
      }

      // 🔥 BELANGRIJK:
      // laad server session opnieuw zodat cookies & context sync zijn
      await loadSession();

      // 📳 Haptic Success
      import("@/lib/haptics").then(({ hapticFeedback }) => {
        hapticFeedback.notification();
      });

      return { success: true };
    } catch (err) {
      console.error("❌ Login fout:", err);
      return {
        success: false,
        message: "Serverfout",
      };
    }
  }, [loadSession]);

  /* -------------------------------------------------------
     LOGOUT
  ------------------------------------------------------- */
  const logout = useCallback(async () => {
    setUser(null);
    clearUserLocal();

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
