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

export function buildAuthHeaders(headers?: HeadersInit) {
  const merged = new Headers(headers || {});
  const accessToken = loadAccessToken();

  if (accessToken && !merged.has("Authorization")) {
    merged.set("Authorization", `Bearer ${accessToken}`);
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
  forceFresh?: boolean;
};

async function fetchAuthInternal(
  path: string,
  options: FetchAuthOptions = {}
): Promise<any> {
  const method = String(options.method || "GET").toUpperCase();
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
      ...Object.fromEntries(buildAuthHeaders(options.headers).entries()),
    },
  });

  if (!res.ok) {
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
         if (typeof window !== "undefined") {
            window.location.href = "/login";
         }
      }
    }

    const text = await res.text().catch(() => "");
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

export async function apiLogin(email: string, password: string) {
  try {
    const res = await fetch(`${API_BASE_URL}/api/auth/login`, {
      method: "POST",
      credentials: "include",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, password }),
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
        ...Object.fromEntries(buildAuthHeaders().entries()),
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
        ...Object.fromEntries(buildAuthHeaders().entries()),
      },
      body: tokenForRequest
        ? JSON.stringify({ refresh_token: tokenForRequest })
        : undefined,
    });

    if (!res.ok) return { success: false };

    const data = await res.json().catch(() => ({}));
    storeAuthTokens({
      access_token: data.access_token,
      refresh_token: tokenForRequest,
    });
    return { success: true, ...data };
  } catch (err) {
    console.error("❌ apiRefresh error:", err);
    return { success: false };
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
        ...Object.fromEntries(buildAuthHeaders().entries()),
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
