"use client";

import { API_BASE_URL, IS_NATIVE_APP } from "@/lib/config";
import {
  saveUserLocal,
  loadUserLocal,
  clearUserLocal,
  saveAccessTokenLocal,
  loadAccessTokenLocal,
  saveRefreshTokenLocal,
  loadRefreshTokenLocal,
  clearTokenLocal,
} from "@/lib/api/user";
import { getActiveLocale, normalizeLocale } from "@/lib/i18n";

/* =======================================================
   📌 Native Token Helpers
======================================================= */

export function storeAuthTokens(tokens: {
  access_token?: string | null;
  refresh_token?: string | null;
}) {
  if (!IS_NATIVE_APP) return;
  if (tokens.access_token !== undefined) {
    saveAccessTokenLocal(tokens.access_token);
  }
  if (tokens.refresh_token !== undefined) {
    saveRefreshTokenLocal(tokens.refresh_token);
  }
}

export function loadAccessToken() {
  return IS_NATIVE_APP ? loadAccessTokenLocal() : null;
}

export function loadRefreshToken() {
  return IS_NATIVE_APP ? loadRefreshTokenLocal() : null;
}

export function clearStoredAuth() {
  clearTokenLocal();
  clearUserLocal();
}

export function getCsrfToken() {
  if (typeof document === "undefined") return null;
  const match = document.cookie.match(/(?:^|; )csrf_token=([^;]+)/);
  return match ? decodeURIComponent(match[1]) : null;
}

function buildLoginRedirectUrl(reason?: string) {
  if (typeof window === "undefined") return "/login";
  const currentPath = `${window.location.pathname || "/"}${window.location.search || ""}`;
  const params = new URLSearchParams();
  if (reason) params.set("reason", reason);
  if (currentPath && !currentPath.startsWith("/login")) {
    params.set("next", currentPath);
  }
  const query = params.toString();
  return query ? `/login?${query}` : "/login";
}

function redirectToLogin(reason?: string) {
  if (typeof window !== "undefined") {
    window.location.href = buildLoginRedirectUrl(reason);
  }
}

let csrfBootstrapPromise: Promise<boolean> | null = null;

export async function ensureCsrfCookie() {
  if (IS_NATIVE_APP) return true;
  if (getCsrfToken()) return true;
  if (csrfBootstrapPromise) return csrfBootstrapPromise;

  csrfBootstrapPromise = (async () => {
    try {
      const res = await fetch(`${API_BASE_URL}/api/auth/me`, {
        method: "GET",
        credentials: "include",
        headers: {
          "Content-Type": "application/json",
          ...Object.fromEntries(buildAuthHeaders(undefined, "GET").entries()),
        },
      });

      if (!res.ok) return false;
      return !!getCsrfToken();
    } catch (err) {
      console.warn("⚠️ CSRF bootstrap via /auth/me failed:", err);
      return false;
    } finally {
      csrfBootstrapPromise = null;
    }
  })();

  return csrfBootstrapPromise;
}

export function buildAuthHeaders(headers?: HeadersInit, method: string = "GET") {
  const merged = new Headers(headers || {});
  const accessToken = loadAccessToken();
  const activeLocale = normalizeLocale(getActiveLocale(typeof window !== "undefined" ? window : undefined));

  if (accessToken && !merged.has("Authorization")) {
    merged.set("Authorization", `Bearer ${accessToken}`);
  }

  if (activeLocale && !merged.has("X-Locale")) {
    merged.set("X-Locale", activeLocale);
  }

  const normalizedMethod = String(method || "GET").toUpperCase();
  if (!IS_NATIVE_APP && ["POST", "PUT", "PATCH", "DELETE"].includes(normalizedMethod)) {
    const csrfToken = getCsrfToken();
    if (csrfToken && !merged.has("X-CSRF-Token")) {
      merged.set("X-CSRF-Token", csrfToken);
    }
  }

  return merged;
}

/* =======================================================
   🆔 user_id helpers
======================================================= */

export function getCurrentUserId(): number | null {
  const user = loadUserLocal();
  return user?.id ? Number(user.id) : null;
}

export function setCurrentUserId(id: number | string) {
  if (typeof window === "undefined") return;

  const existing = loadUserLocal() || {};
  const merged = { ...existing, id: Number(id) };

  saveUserLocal(merged);
}

export function clearCurrentUserId() {
  clearUserLocal();
}

/* =======================================================
   🌐 fetchAuth — AUTH + EXPLICIT CACHE POLICY
======================================================= */

function withCacheBust(path: string) {
  // voorkomt dat je URL’s dubbel kapot gaan (als er al ? in zit)
  const sep = path.includes("?") ? "&" : "?";
  return `${path}${sep}_=${Date.now()}`;
}

type FetchAuthOptions = RequestInit & {
  _retry?: boolean;
  _csrfRetry?: boolean;
  forceFresh?: boolean;
};

async function fetchAuthInternal(
  path: string,
  options: FetchAuthOptions = {}
): Promise<any> {
  const method = String(options.method || "GET").toUpperCase();
  if (!IS_NATIVE_APP && ["POST", "PUT", "PATCH", "DELETE"].includes(method) && !getCsrfToken()) {
    await ensureCsrfCookie();
  }
  const cacheMode = options.cache ?? (options.forceFresh || method !== "GET" ? "no-store" : "default");
  const noStoreHeaders =
    cacheMode === "no-store"
      ? {
          "Cache-Control": "no-store, no-cache, must-revalidate, proxy-revalidate",
          Pragma: "no-cache",
          Expires: "0",
        }
      : {};

  const res = await fetch(`${API_BASE_URL}${path}`, {
    ...options,
    credentials: "include",
    cache: cacheMode as RequestCache,
    headers: {
      "Content-Type": "application/json",
      ...noStoreHeaders,
      ...Object.fromEntries(buildAuthHeaders(options.headers, method).entries()),
    },
  });

  if (!res.ok) {
    const text = await res.text().catch(() => "");

    // 🔁 AUTO-REFRESH LOGIC
    if (res.status === 401 && !options._retry) {
      console.warn(`⚠️ 401 Unauthorized op ${path}. Probeer token te refreshen...`);
      const refreshResult = await apiRefresh();
      
      if (refreshResult.success) {
         console.log("✅ Token succesvol vernieuwd! Retrying request...");
         // Retry de originele request met flag _retry
         return fetchAuthInternal(path, { ...options, _retry: true });
      } else {
         console.error("❌ Token refresh mislukt. Gebruiker moet opnieuw inloggen.");
         clearStoredAuth();
         redirectToLogin("session_expired");
      }
    }

    if (
      res.status === 403 &&
      !options._csrfRetry &&
      text.includes("CSRF validation failed")
    ) {
      console.warn(`⚠️ CSRF retry bootstrap voor ${path}`);
      await ensureCsrfCookie();
      return fetchAuthInternal(path, { ...options, _csrfRetry: true });
    }

    const error: any = new Error("API request failed");
    error.status = res.status;
    error.body = text;
    error.path = path;

    if (res.status !== 401) {
      console.error(`❌ fetchAuth ${path} failed:`, res.status, text);
    }
    throw error;
  }

  // ✅ JSON veilig parsen
  const contentType = res.headers.get("content-type") || "";
  if (contentType.includes("application/json")) {
    try {
      return await res.json();
    } catch {
      return null;
    }
  }

  return res;
}

export const fetchAuth = fetchAuthInternal;


/* =======================================================
   🔐 LOGIN
======================================================= */

export async function apiLogin(email: string, password: string, locale?: string | null) {
  try {
    const normalizedLocale = normalizeLocale(locale) || getActiveLocale(typeof window !== "undefined" ? window : undefined);
    const res = await fetch(`${API_BASE_URL}/api/auth/login`, {
      method: "POST",
      credentials: "include",
      headers: {
        "Content-Type": "application/json",
        ...Object.fromEntries(buildAuthHeaders(undefined, "POST").entries()),
      },
      body: JSON.stringify({ email, password, locale: normalizedLocale }),
    });

    if (!res.ok) {
      const body = await res.json().catch(() => null);
      return {
        success: false,
        message: body?.detail || "Ongeldige inloggegevens",
      };
    }

    const data = await res.json();
    const user = data.user || data;

    storeAuthTokens({
      access_token: data.access_token,
      refresh_token: data.refresh_token,
    });
    saveUserLocal(user);
    return { success: true, user };
  } catch (err) {
    console.error("❌ apiLogin error:", err);
    return {
      success: false,
      message: typeof navigator !== "undefined" && !navigator.onLine
        ? "Je lijkt offline. Controleer je internetverbinding."
        : "Kan de server niet bereiken. Probeer opnieuw.",
    };
  }
}

/* =======================================================
   🚪 LOGOUT
======================================================= */

export async function apiLogout() {
  try {
    await fetch(`${API_BASE_URL}/api/auth/logout`, {
      method: "POST",
      credentials: "include",
      headers: {
        "Content-Type": "application/json",
        ...Object.fromEntries(buildAuthHeaders(undefined, "POST").entries()),
      },
    });
    clearStoredAuth();
    return { success: true };
  } catch (err) {
    console.error("❌ apiLogout error:", err);
    return { success: false };
  }
}

/* =======================================================
   🔁 REFRESH
======================================================= */

export async function apiRefresh(refreshToken?: string) {
  try {
    const tokenForRequest = refreshToken || loadRefreshToken();
    const res = await fetch(`${API_BASE_URL}/api/auth/refresh`, {
      method: "POST",
      credentials: "include",
      headers: {
        "Content-Type": "application/json",
        ...Object.fromEntries(buildAuthHeaders(undefined, "POST").entries()),
      },
      body: tokenForRequest
        ? JSON.stringify({ refresh_token: tokenForRequest })
        : undefined,
    });

    if (!res.ok) return { success: false };

    const data = await res.json().catch(() => ({}));
    storeAuthTokens({
      access_token: data.access_token,
      refresh_token: data.refresh_token ?? tokenForRequest,
    });
    return { success: true, ...data };
  } catch (err) {
    console.error("❌ apiRefresh error:", err);
    return { success: false };
  }
}

export async function apiForgotPassword(email: string, locale?: string | null) {
  try {
    const res = await fetch(`${API_BASE_URL}/api/auth/forgot-password`, {
      method: "POST",
      credentials: "include",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        email,
        locale: normalizeLocale(locale) || undefined,
      }),
    });

    const body = await res.json().catch(() => ({}));
    return {
      success: res.ok,
      message: body?.message,
    };
  } catch (err) {
    console.error("❌ apiForgotPassword error:", err);
    return {
      success: false,
      message: null,
    };
  }
}

export async function apiValidateResetPasswordToken(token: string) {
  try {
    const url = new URL(`${API_BASE_URL}/api/auth/reset-password/validate`);
    url.searchParams.set("token", token);
    const res = await fetch(url.toString(), {
      method: "GET",
      credentials: "include",
      headers: {
        "Content-Type": "application/json",
      },
    });

    if (!res.ok) return { success: false, valid: false };

    const body = await res.json().catch(() => ({}));
    return { success: true, valid: Boolean(body?.valid) };
  } catch (err) {
    console.error("❌ apiValidateResetPasswordToken error:", err);
    return { success: false, valid: false };
  }
}

export async function apiResetPassword(token: string, password: string) {
  try {
    const res = await fetch(`${API_BASE_URL}/api/auth/reset-password`, {
      method: "POST",
      credentials: "include",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ token, password }),
    });

    const body = await res.json().catch(() => ({}));
    return {
      success: res.ok,
      message: body?.detail || null,
    };
  } catch (err) {
    console.error("❌ apiResetPassword error:", err);
    return {
      success: false,
      message: null,
    };
  }
}

/* =======================================================
   👤 ME
======================================================= */

export async function apiMe() {
  try {
    const res = await fetch(`${API_BASE_URL}/api/auth/me`, {
      method: "GET",
      credentials: "include",
      headers: {
        "Content-Type": "application/json",
        ...Object.fromEntries(buildAuthHeaders(undefined, "GET").entries()),
      },
    });

    if (!res.ok) {
      clearStoredAuth();
      return { success: false, user: null };
    }

    const user = await res.json();
    saveUserLocal(user);

    return { success: true, user };
  } catch (err) {
    console.error("❌ apiMe error:", err);
    return { success: false, user: null };
  }
}
