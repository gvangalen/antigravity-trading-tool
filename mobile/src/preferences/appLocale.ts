import { getItemAsync, setItemAsync } from '../services/secureStore';

export type AppLanguage = 'nl' | 'en' | 'de';

export const DEFAULT_APP_LANGUAGE: AppLanguage = 'nl';
export const LANGUAGE_KEY = 'tradamind_mobile_language';
const appLanguageListeners = new Set<(language: AppLanguage) => void>();

export function normalizeAppLanguage(value: string | null | undefined): AppLanguage {
  const normalized = value?.trim().toLowerCase();
  if (!normalized) {
    return DEFAULT_APP_LANGUAGE;
  }

  if (normalized === 'nl' || normalized.startsWith('nl-')) {
    return 'nl';
  }

  if (normalized === 'en' || normalized.startsWith('en-')) {
    return 'en';
  }

  if (normalized === 'de' || normalized.startsWith('de-')) {
    return 'de';
  }

  return DEFAULT_APP_LANGUAGE;
}

export function extractBackendAppLanguage(input: unknown, fallback: AppLanguage = DEFAULT_APP_LANGUAGE): AppLanguage {
  const direct = normalizeLocaleCandidate(input);
  if (direct) {
    return direct;
  }

  if (!input || typeof input !== 'object') {
    return fallback;
  }

  const record = input as Record<string, unknown>;
  const nestedCandidates = [
    record.locale,
    record.language,
    record.preferences,
    record.ai_preferences,
    record.user,
    record.account,
    record.profile,
  ];

  for (const candidate of nestedCandidates) {
    const resolved = extractBackendAppLanguage(candidate, fallback);
    if (resolved !== fallback) {
      return resolved;
    }
  }

  return fallback;
}

export async function getStoredAppLanguage() {
  return normalizeAppLanguage(await getItemAsync(LANGUAGE_KEY));
}

export async function setStoredAppLanguage(value: AppLanguage) {
  await setItemAsync(LANGUAGE_KEY, value);
  appLanguageListeners.forEach((listener) => listener(value));
}

export function subscribeAppLanguage(listener: (language: AppLanguage) => void) {
  appLanguageListeners.add(listener);
  return () => {
    appLanguageListeners.delete(listener);
  };
}

function normalizeLocaleCandidate(value: unknown): AppLanguage | null {
  if (typeof value !== 'string' || !value.trim()) {
    return null;
  }

  return normalizeAppLanguage(value);
}
