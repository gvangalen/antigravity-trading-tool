// -----------------------------------------------------
// lib/user.ts — JWT-compatible version
// -----------------------------------------------------

/**
 * Waar we de ingelogde user opslaan in localStorage
 * (profiel info, niet voor security!)
 */
const LOCAL_USER_KEY = "tt_current_user";
const LOCAL_ACCESS_TOKEN_KEY = "tt_access_token";
const LOCAL_REFRESH_TOKEN_KEY = "tt_refresh_token";

/**
 * User lokaal opslaan (UI only)
 */
export function saveUserLocal(user: any) {
  if (!user) return;
  if (typeof window === "undefined") return;
  localStorage.setItem(LOCAL_USER_KEY, JSON.stringify(user));
}

/**
 * User laden uit localStorage
 */
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

/**
 * User verwijderen (logout)
 */
export function clearUserLocal() {
  if (typeof window === "undefined") return;
  localStorage.removeItem(LOCAL_USER_KEY);
}

export function saveAccessTokenLocal(token?: string | null) {
  if (typeof window === "undefined") return;
  if (!token) {
    localStorage.removeItem(LOCAL_ACCESS_TOKEN_KEY);
    return;
  }
  localStorage.setItem(LOCAL_ACCESS_TOKEN_KEY, token);
}

export function loadAccessTokenLocal() {
  if (typeof window === "undefined") return null;
  return localStorage.getItem(LOCAL_ACCESS_TOKEN_KEY);
}

export function saveRefreshTokenLocal(token?: string | null) {
  if (typeof window === "undefined") return;
  if (!token) {
    localStorage.removeItem(LOCAL_REFRESH_TOKEN_KEY);
    return;
  }
  localStorage.setItem(LOCAL_REFRESH_TOKEN_KEY, token);
}

export function loadRefreshTokenLocal() {
  if (typeof window === "undefined") return null;
  return localStorage.getItem(LOCAL_REFRESH_TOKEN_KEY);
}

export function clearTokenLocal() {
  if (typeof window === "undefined") return;
  localStorage.removeItem(LOCAL_ACCESS_TOKEN_KEY);
  localStorage.removeItem(LOCAL_REFRESH_TOKEN_KEY);
}
