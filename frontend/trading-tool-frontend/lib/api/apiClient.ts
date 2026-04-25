import { API_BASE_URL } from "@/lib/config";

//----------------------------------------------------------
// 📡 GET
//----------------------------------------------------------

export async function apiGet<T>(path: string, init?: RequestInit): Promise<T> {
  const url = `${API_BASE_URL}${path}`;

  const res = await fetch(url, {
    ...init,
    method: "GET",
    credentials: "include",       // ⬅️ COOKIE MEEGEVEN
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers || {}),
    },
    cache: "no-store",
  });

  if (!res.ok) {
    const text = await res.text().catch(() => "");
    console.error(`❌ API GET ${url} failed:`, res.status, text);
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
  init?: RequestInit
): Promise<T> {
  const url = `${API_BASE_URL}${path}`;

  const res = await fetch(url, {
    ...init,
    method: "POST",
    credentials: "include",        // ⬅️ COOKIE MEEGEVEN
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers || {}),
    },
    body: body ? JSON.stringify(body) : undefined,
  });

  if (!res.ok) {
    const text = await res.text().catch(() => "");
    console.error(`❌ API POST ${url} failed:`, res.status, text);
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
  init?: RequestInit
): Promise<T> {
  const url = `${API_BASE_URL}${path}`;

  const res = await fetch(url, {
    ...init,
    method: "PUT",
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers || {}),
    },
    body: body ? JSON.stringify(body) : undefined,
  });

  if (!res.ok) {
    const text = await res.text().catch(() => "");
    console.error(`❌ API PUT ${url} failed:`, res.status, text);
    throw new Error(`API PUT failed (${res.status})`);
  }

  return res.json();
}

//----------------------------------------------------------
// 📡 DELETE
//----------------------------------------------------------

export async function apiDelete<T>(path: string, init?: RequestInit): Promise<T> {
  const url = `${API_BASE_URL}${path}`;

  const res = await fetch(url, {
    ...init,
    method: "DELETE",
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers || {}),
    },
  });

  if (!res.ok) {
    const text = await res.text().catch(() => "");
    console.error(`❌ API DELETE ${url} failed:`, res.status, text);
    throw new Error(`API DELETE failed (${res.status})`);
  }

  // Sommige deletes hebben geen JSON body
  try {
    return await res.json();
  } catch {
    return {} as T;
  }
}
