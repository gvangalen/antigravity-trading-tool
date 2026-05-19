import { API_BASE_URL } from "@/lib/config";
import { apiRefresh, clearStoredAuth, buildAuthHeaders } from "@/lib/api/auth";

//----------------------------------------------------------
// 📡 GET
//----------------------------------------------------------

export async function apiGet<T>(path: string, init?: RequestInit & { _retry?: boolean }): Promise<T> {
  const url = `${API_BASE_URL}${path}`;

  const res = await fetch(url, {
    ...init,
    method: "GET",
    credentials: "include",
    headers: Object.fromEntries(
      buildAuthHeaders({
        "Content-Type": "application/json",
        ...(init?.headers || {}),
      }).entries()
    ),
    cache: "no-store",
  });

  if (!res.ok) {
    if (res.status === 401 && !init?._retry) {
      console.warn(`⚠️ 401 Unauthorized op apiGet(${path}). Probeer token te refreshen...`);
      const refreshResult = await apiRefresh();
      if (refreshResult.success) {
        return apiGet(path, { ...init, _retry: true });
      } else {
        clearStoredAuth();
        if (typeof window !== "undefined") {
          window.location.href = "/login";
        }
      }
    }

    const text = await res.text().catch(() => "");
    if (res.status !== 401) {
      console.error(`❌ API GET ${url} failed:`, res.status, text);
    }
    throw new Error(`API GET failed (${res.status})`);
  }

  return res.json();
}

//----------------------------------------------------------
// 📡 POST
//----------------------------------------------------------

export async function apiPost<T>(
  path: string,
  body?: any,
  init?: RequestInit & { _retry?: boolean }
): Promise<T> {
  const url = `${API_BASE_URL}${path}`;

  const res = await fetch(url, {
    ...init,
    method: "POST",
    credentials: "include",
    headers: Object.fromEntries(
      buildAuthHeaders({
        "Content-Type": "application/json",
        ...(init?.headers || {}),
      }).entries()
    ),
    body: body ? JSON.stringify(body) : undefined,
  });

  if (!res.ok) {
    if (res.status === 401 && !init?._retry) {
      console.warn(`⚠️ 401 Unauthorized op apiPost(${path}). Probeer token te refreshen...`);
      const refreshResult = await apiRefresh();
      if (refreshResult.success) {
        return apiPost(path, body, { ...init, _retry: true });
      } else {
        clearStoredAuth();
        if (typeof window !== "undefined") {
          window.location.href = "/login";
        }
      }
    }

    const text = await res.text().catch(() => "");
    if (res.status !== 401) {
      console.error(`❌ API POST ${url} failed:`, res.status, text);
    }
    throw new Error(`API POST failed (${res.status})`);
  }

  return res.json();
}

//----------------------------------------------------------
// 📡 PUT
//----------------------------------------------------------

export async function apiPut<T>(
  path: string,
  body?: any,
  init?: RequestInit & { _retry?: boolean }
): Promise<T> {
  const url = `${API_BASE_URL}${path}`;

  const res = await fetch(url, {
    ...init,
    method: "PUT",
    credentials: "include",
    headers: Object.fromEntries(
      buildAuthHeaders({
        "Content-Type": "application/json",
        ...(init?.headers || {}),
      }).entries()
    ),
    body: body ? JSON.stringify(body) : undefined,
  });

  if (!res.ok) {
    if (res.status === 401 && !init?._retry) {
      console.warn(`⚠️ 401 Unauthorized op apiPut(${path}). Probeer token te refreshen...`);
      const refreshResult = await apiRefresh();
      if (refreshResult.success) {
        return apiPut(path, body, { ...init, _retry: true });
      } else {
        clearStoredAuth();
        if (typeof window !== "undefined") {
          window.location.href = "/login";
        }
      }
    }

    const text = await res.text().catch(() => "");
    if (res.status !== 401) {
      console.error(`❌ API PUT ${url} failed:`, res.status, text);
    }
    throw new Error(`API PUT failed (${res.status})`);
  }

  return res.json();
}

//----------------------------------------------------------
// 📡 DELETE
//----------------------------------------------------------

export async function apiDelete<T>(path: string, init?: RequestInit & { _retry?: boolean }): Promise<T> {
  const url = `${API_BASE_URL}${path}`;

  const res = await fetch(url, {
    ...init,
    method: "DELETE",
    credentials: "include",
    headers: Object.fromEntries(
      buildAuthHeaders({
        "Content-Type": "application/json",
        ...(init?.headers || {}),
      }).entries()
    ),
  });

  if (!res.ok) {
    if (res.status === 401 && !init?._retry) {
      console.warn(`⚠️ 401 Unauthorized op apiDelete(${path}). Probeer token te refreshen...`);
      const refreshResult = await apiRefresh();
      if (refreshResult.success) {
        return apiDelete(path, { ...init, _retry: true });
      } else {
        clearStoredAuth();
        if (typeof window !== "undefined") {
          window.location.href = "/login";
        }
      }
    }

    const text = await res.text().catch(() => "");
    if (res.status !== 401) {
      console.error(`❌ API DELETE ${url} failed:`, res.status, text);
    }
    throw new Error(`API DELETE failed (${res.status})`);
  }

  try {
    return await res.json();
  } catch {
    return {} as T;
  }
}
