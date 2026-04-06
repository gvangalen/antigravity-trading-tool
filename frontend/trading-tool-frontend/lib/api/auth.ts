"use client";

import { API_BASE_URL } from "@/lib/config";

/* =======================================================
   📌 Local Storage Helpers
======================================================= */

const LOCAL_USER_KEY = "tt_current_user";

export function saveUserLocal(user: any) {
  if (!user) return;
  if (typeof window === "undefined") return;
  localStorage.setItem(LOCAL_USER_KEY, JSON.stringify(user));
}

export function loadUserLocal() {
  if (typeof window === "undefined") return null;

  const raw = localStorage.getItem(LOCAL_USER_KEY);
  if (!raw) return null;

  try {
    return JSON.parse(raw);
  } catch {
    return null;
  }
}

export function clearUserLocal() {
  if (typeof window === "undefined") return;
  localStorage.removeItem(LOCAL_USER_KEY);
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
   🌐 fetchAuth — NO CACHE + STATUS DOORGAVE (🔥 FIX)
======================================================= */

function withCacheBust(path: string) {
  // voorkomt dat je URL’s dubbel kapot gaan (als er al ? in zit)
  const sep = path.includes("?") ? "&" : "?";
  return `${path}${sep}_=${Date.now()}`;
}

async function fetchAuthInternal(
  path: string,
  options: RequestInit = {}
): Promise<any> {
  // ✅ default no-store (maar laat caller override toe)
  const cacheMode = (options as any)?.cache ?? "no-store";

  const res = await fetch(`${API_BASE_URL}${path}`, {
    ...options,
    credentials: "include",

    // 🔥 BELANGRIJK: voorkom cached responses (root cause van jouw issue)
    cache: cacheMode as RequestCache,

    headers: {
      // JSON default
      "Content-Type": "application/json",

      // 🔥 Extra harde no-cache headers (helpt bij proxies / sommige setups)
      "Cache-Control": "no-store, no-cache, must-revalidate, proxy-revalidate",
      Pragma: "no-cache",
      Expires: "0",

      ...(options.headers || {}),
    },
  });

  if (!res.ok) {
    const text = await res.text().catch(() => "");

    const error: any = new Error("API request failed");
    error.status = res.status; // ✅ jij had deze al: goed
    error.body = text;
    error.path = path;

    console.error(`❌ fetchAuth ${path} failed:`, res.status, text);
    throw error;
  }

  // ✅ JSON veilig parsen, maar als het geen JSON is: return response object
  const contentType = res.headers.get("content-type") || "";
  if (contentType.includes("application/json")) {
    try {
      return await res.json();
    } catch {
      return null;
    }
  }

  // bv. PDF endpoints / file downloads
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

    saveUserLocal(user);
    return { success: true, user };
  } catch (err) {
    console.error("❌ apiLogin error:", err);
    return { success: false, message: "Serverfout" };
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
      headers: { "Content-Type": "application/json" },
    });
    clearUserLocal();
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
    const res = await fetch(`${API_BASE_URL}/api/auth/refresh`, {
      method: "POST",
      credentials: "include",
      headers: { "Content-Type": "application/json" },
      body: refreshToken
        ? JSON.stringify({ refresh_token: refreshToken })
        : undefined,
    });

    if (!res.ok) return { success: false };

    const data = await res.json().catch(() => ({}));
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
      headers: { "Content-Type": "application/json" },
    });

    if (!res.ok) {
      clearUserLocal();
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
