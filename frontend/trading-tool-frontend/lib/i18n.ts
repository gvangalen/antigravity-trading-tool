export const SUPPORTED_LOCALES = ["nl", "en", "de"] as const;
export type Locale = (typeof SUPPORTED_LOCALES)[number];

export const DEFAULT_LOCALE: Locale = "nl";
export const LOCALE_STORAGE_KEY = "antigravity_locale";
export const LOCALE_COOKIE_KEY = "antigravity_locale";
export const LOCALE_LABELS: Record<Locale, string> = {
  nl: "Nederlands",
  en: "English",
  de: "Deutsch",
};
export const LOCALE_TO_INTL_LOCALE: Record<Locale, string> = {
  nl: "nl-NL",
  en: "en-US",
  de: "de-DE",
};
export const LOCALE_TO_FINN_LANGUAGE: Record<Locale, string> = {
  nl: "Dutch",
  en: "English",
  de: "German",
};

export function isSupportedLocale(value: string): value is Locale {
  return (SUPPORTED_LOCALES as readonly string[]).includes(value);
}

export function normalizeLocale(value?: string | null): Locale | null {
  if (!value) return null;
  const lowered = String(value).trim().toLowerCase();
  const directMatch = lowered.split(/[_-]/)[0];

  if (isSupportedLocale(lowered as Locale)) return lowered as Locale;
  if (isSupportedLocale(directMatch)) return directMatch;

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

export function getLocaleLabel(locale: Locale) {
  return LOCALE_LABELS[normalizeLocale(locale) || DEFAULT_LOCALE];
}

export function getIntlLocale(locale?: string | null) {
  return LOCALE_TO_INTL_LOCALE[normalizeLocale(locale) || DEFAULT_LOCALE];
}

export function getFinnLanguage(locale?: string | null) {
  return LOCALE_TO_FINN_LANGUAGE[normalizeLocale(locale) || DEFAULT_LOCALE];
}

export function getLocaleValue<T>(
  locale: string | null | undefined,
  values: Partial<Record<Locale, T>>,
  fallback?: T,
) {
  const normalizedLocale = normalizeLocale(locale) || DEFAULT_LOCALE;
  if (values[normalizedLocale] !== undefined) return values[normalizedLocale] as T;
  if (values[DEFAULT_LOCALE] !== undefined) return values[DEFAULT_LOCALE] as T;
  if (values.en !== undefined) return values.en as T;
  if (values.nl !== undefined) return values.nl as T;
  return fallback as T;
}

type FormatDateOptions = Intl.DateTimeFormatOptions;

export function formatDate(
  value: Date | number | string,
  locale?: string | null,
  options?: FormatDateOptions,
) {
  const date = value instanceof Date ? value : new Date(value);
  return new Intl.DateTimeFormat(getIntlLocale(locale), options).format(date);
}

export function formatDateTime(
  value: Date | number | string,
  locale?: string | null,
  options?: FormatDateOptions,
) {
  return formatDate(value, locale, options);
}

export function formatNumber(
  value: number,
  locale?: string | null,
  options?: Intl.NumberFormatOptions,
) {
  return new Intl.NumberFormat(getIntlLocale(locale), options).format(value);
}

export function formatPercent(
  value: number,
  locale?: string | null,
  options?: Intl.NumberFormatOptions,
) {
  return formatNumber(value, locale, {
    style: "percent",
    maximumFractionDigits: 2,
    ...options,
  });
}

export function formatCurrency(
  value: number,
  locale?: string | null,
  currency = "EUR",
  options?: Intl.NumberFormatOptions,
) {
  return formatNumber(value, locale, {
    style: "currency",
    currency,
    ...options,
  });
}

export function getLocaleBootScript() {
  return `
    (function () {
      try {
        var STORAGE_KEY = ${JSON.stringify(LOCALE_STORAGE_KEY)};
        var COOKIE_KEY = ${JSON.stringify(LOCALE_COOKIE_KEY)};
        var DEFAULT_LOCALE = ${JSON.stringify(DEFAULT_LOCALE)};
        var SUPPORTED_LOCALES = ${JSON.stringify([...SUPPORTED_LOCALES])};

        function normalizeLocale(value) {
          if (!value) return null;
          var lowered = String(value).trim().toLowerCase();
          var directMatch = lowered.split(/[_-]/)[0];
          if (SUPPORTED_LOCALES.indexOf(lowered) >= 0) return lowered;
          if (SUPPORTED_LOCALES.indexOf(directMatch) >= 0) return directMatch;
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
