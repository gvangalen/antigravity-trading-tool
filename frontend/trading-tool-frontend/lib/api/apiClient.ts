import { API_BASE_URL } from "@/lib/config";
import { apiRefresh, clearStoredAuth, buildAuthHeaders, ensureCsrfCookie } from "@/lib/api/auth";

type ApiRequestInit = RequestInit & {
  _retry?: boolean;
  forceFresh?: boolean;
};

function resolveCacheMode(method: string, init?: ApiRequestInit): RequestCache {
  if (init?.cache) return init.cache;
  if (init?.forceFresh || method !== "GET") return "no-store";
  return "default";
}

function buildJsonHeaders(method: string, init: ApiRequestInit | undefined, cacheMode: RequestCache) {
  const headers = new Headers(init?.headers || {});
  if (!headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }

  if (cacheMode === "no-store") {
    headers.set("Cache-Control", "no-store, no-cache, must-revalidate, proxy-revalidate");
    headers.set("Pragma", "no-cache");
    headers.set("Expires", "0");
  }

  return Object.fromEntries(buildAuthHeaders(headers, method).entries());
}

//----------------------------------------------------------
// 📡 GET
//----------------------------------------------------------

export async function apiGet<T>(path: string, init?: ApiRequestInit): Promise<T> {
  const url = `${API_BASE_URL}${path}`;
  const cacheMode = resolveCacheMode("GET", init);

  const res = await fetch(url, {
    ...init,
    method: "GET",
    credentials: "include",
    headers: buildJsonHeaders("GET", init, cacheMode),
    cache: cacheMode,
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
  init?: ApiRequestInit
): Promise<T> {
  await ensureCsrfCookie();
  const url = `${API_BASE_URL}${path}`;
  const cacheMode = resolveCacheMode("POST", init);

  const res = await fetch(url, {
    ...init,
    method: "POST",
    credentials: "include",
    headers: buildJsonHeaders("POST", init, cacheMode),
    cache: cacheMode,
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
  init?: ApiRequestInit
): Promise<T> {
  await ensureCsrfCookie();
  const url = `${API_BASE_URL}${path}`;
  const cacheMode = resolveCacheMode("PUT", init);

  const res = await fetch(url, {
    ...init,
    method: "PUT",
    credentials: "include",
    headers: buildJsonHeaders("PUT", init, cacheMode),
    cache: cacheMode,
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

export async function apiDelete<T>(path: string, init?: ApiRequestInit): Promise<T> {
  await ensureCsrfCookie();
  const url = `${API_BASE_URL}${path}`;
  const cacheMode = resolveCacheMode("DELETE", init);

  const res = await fetch(url, {
    ...init,
    method: "DELETE",
    credentials: "include",
    headers: buildJsonHeaders("DELETE", init, cacheMode),
    cache: cacheMode,
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
