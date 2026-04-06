// -----------------------------------------------------
// lib/user.ts — JWT-compatible version
// -----------------------------------------------------

/**
 * Waar we de ingelogde user opslaan in localStorage
 * (profiel info, niet voor security!)
 */
const LOCAL_USER_KEY = "tt_current_user";

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

