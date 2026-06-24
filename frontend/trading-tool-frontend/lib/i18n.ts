export const SUPPORTED_LOCALES = ["en", "nl"] as const;
export type Locale = (typeof SUPPORTED_LOCALES)[number];

export const DEFAULT_LOCALE: Locale = "nl";
export const LOCALE_STORAGE_KEY = "antigravity_locale";
export const LOCALE_COOKIE_KEY = "antigravity_locale";

export function normalizeLocale(value?: string | null): Locale | null {
  if (!value) return null;
  const lowered = String(value).trim().toLowerCase();

  if (lowered.startsWith("nl")) return "nl";
  if (lowered.startsWith("en")) return "en";

  return null;
}

export function readLocaleFromCookie(cookieString?: string | null): Locale | null {
  if (!cookieString) return null;

  const match = cookieString.match(
    new RegExp(`(?:^|; )${LOCALE_COOKIE_KEY}=([^;]+)`),
  );

  if (!match?.[1]) return null;
  return normalizeLocale(decodeURIComponent(match[1]));
}

export function readStoredLocale(win: Window): Locale | null {
  try {
    const stored = win.localStorage.getItem(LOCALE_STORAGE_KEY);
    const normalizedStored = normalizeLocale(stored);
    if (normalizedStored) return normalizedStored;
  } catch {
    // Ignore storage access issues and continue with other fallbacks.
  }

  return readLocaleFromCookie(win.document?.cookie);
}

export function detectBrowserLocale(win: Window): Locale {
  const preferred = [
    ...(Array.isArray(win.navigator?.languages) ? win.navigator.languages : []),
    win.navigator?.language,
  ];

  for (const candidate of preferred) {
    const normalized = normalizeLocale(candidate);
    if (normalized) return normalized;
  }

  return DEFAULT_LOCALE;
}

export function resolveInitialLocale(win: Window): Locale {
  return (
    readStoredLocale(win) ||
    normalizeLocale((win as Window & { __ANTIGRAVITY_LOCALE__?: string }).__ANTIGRAVITY_LOCALE__) ||
    normalizeLocale(win.document?.documentElement?.dataset?.locale) ||
    normalizeLocale(win.document?.documentElement?.lang) ||
    detectBrowserLocale(win)
  );
}

export function applyLocaleToDocument(locale: Locale, doc: Document) {
  doc.documentElement.lang = locale;
  doc.documentElement.dataset.locale = locale;
}

export function persistLocale(locale: Locale, win: Window) {
  try {
    win.localStorage.setItem(LOCALE_STORAGE_KEY, locale);
  } catch {
    // Ignore storage write failures.
  }

  win.document.cookie = `${LOCALE_COOKIE_KEY}=${encodeURIComponent(locale)}; path=/; max-age=31536000; samesite=lax`;
  (win as Window & { __ANTIGRAVITY_LOCALE__?: Locale }).__ANTIGRAVITY_LOCALE__ = locale;
}

export function resolveServerFallbackLocale(): Locale {
  return DEFAULT_LOCALE;
}

export function getLocaleBootScript() {
  return `
    (function () {
      try {
        var STORAGE_KEY = ${JSON.stringify(LOCALE_STORAGE_KEY)};
        var COOKIE_KEY = ${JSON.stringify(LOCALE_COOKIE_KEY)};
        var DEFAULT_LOCALE = ${JSON.stringify(DEFAULT_LOCALE)};

        function normalizeLocale(value) {
          if (!value) return null;
          var lowered = String(value).trim().toLowerCase();
          if (lowered.indexOf("nl") === 0) return "nl";
          if (lowered.indexOf("en") === 0) return "en";
          return null;
        }

        function readCookieLocale() {
          var match = document.cookie.match(new RegExp("(?:^|; )" + COOKIE_KEY + "=([^;]+)"));
          return normalizeLocale(match && match[1] ? decodeURIComponent(match[1]) : null);
        }

        var stored = null;
        try {
          stored = normalizeLocale(window.localStorage.getItem(STORAGE_KEY));
        } catch (error) {}

        var browserLocales = Array.isArray(navigator.languages) ? navigator.languages : [];
        var browserLocale = normalizeLocale(browserLocales[0]) || normalizeLocale(navigator.language);
        var locale = stored || readCookieLocale() || browserLocale || DEFAULT_LOCALE;

        window.__ANTIGRAVITY_LOCALE__ = locale;
        document.documentElement.lang = locale;
        document.documentElement.dataset.locale = locale;
        document.cookie = COOKIE_KEY + "=" + encodeURIComponent(locale) + "; path=/; max-age=31536000; samesite=lax";
      } catch (error) {}
    })();
  `;
}
