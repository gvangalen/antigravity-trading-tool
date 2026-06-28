"use client";

import React, { createContext, useContext, useState, useEffect, ReactNode, useRef } from "react";
import en from "@/dictionaries/en.json";
import de from "@/dictionaries/de.json";
import nl from "@/dictionaries/nl.json";
import { useAuth } from "@/components/auth/AuthProvider";
import { updateAssistantPreferences } from "@/lib/api/ai";
import {
  applyLocaleToDocument,
  DEFAULT_LOCALE,
  normalizeLocale,
  persistLocale,
  resolveInitialLocale,
  SUPPORTED_LOCALES,
} from "@/lib/i18n";
import type { Locale } from "@/lib/i18n";

export const dictionaries = {
  nl,
  en,
  de,
} as const satisfies Record<Locale, typeof en>;

export function getDictionary(locale?: string | null) {
  return dictionaries[normalizeLocale(locale) || DEFAULT_LOCALE];
}

type I18nContextValue = {
  locale: Locale;
  setLocale: (l: Locale) => void;
  t: typeof en;
  supportedLocales: readonly Locale[];
};

export const I18nContext = createContext<I18nContextValue | null>(null);

export function useTranslation() {
  const ctx = useContext(I18nContext);
  if (!ctx) throw new Error("❌ useTranslation must be used within I18nProvider");
  return ctx;
}

export function I18nProvider({ children }: { children: ReactNode }) {
  const { user, sessionChecked } = useAuth();
  const [locale, setLocaleState] = useState<Locale>(() => {
    if (typeof window !== "undefined") {
      return resolveInitialLocale(window);
    }
    return DEFAULT_LOCALE;
  });
  const pendingAccountLocaleRef = useRef<Locale | null>(null);
  const seededAccountLocaleRef = useRef<string | null>(null);

  useEffect(() => {
    if (typeof document !== "undefined") {
      applyLocaleToDocument(locale, document);
    }
    if (typeof window !== "undefined") {
      persistLocale(locale, window);
    }
  }, [locale]);

  useEffect(() => {
    if (!sessionChecked || !user) return;

    const accountLocale = normalizeLocale(user?.ai_preferences?.locale);
    const effectiveAccountLocale = pendingAccountLocaleRef.current || accountLocale;

    if (effectiveAccountLocale) {
      if (locale !== effectiveAccountLocale) {
        setLocaleState(effectiveAccountLocale);
      }
      return;
    }

    if (seededAccountLocaleRef.current === `${user.id}:${locale}`) {
      return;
    }

    seededAccountLocaleRef.current = `${user.id}:${locale}`;
    pendingAccountLocaleRef.current = locale;

    void updateAssistantPreferences({ locale })
      .catch(() => {
        if (pendingAccountLocaleRef.current === locale) {
          pendingAccountLocaleRef.current = null;
        }
        seededAccountLocaleRef.current = null;
      });
  }, [locale, sessionChecked, user]);

  const setLocale = (l: Locale) => {
    setLocaleState(l);

    if (user?.id && sessionChecked) {
      pendingAccountLocaleRef.current = l;
      seededAccountLocaleRef.current = `${user.id}:${l}`;

      void updateAssistantPreferences({ locale: l }).catch(() => {
        if (pendingAccountLocaleRef.current === l) {
          pendingAccountLocaleRef.current = null;
        }
        seededAccountLocaleRef.current = null;
      });
    }
  };

  const t = getDictionary(locale);

  return (
    <I18nContext.Provider value={{ locale, setLocale, t, supportedLocales: SUPPORTED_LOCALES }}>
      {children}
    </I18nContext.Provider>
  );
}
