"use client";

import React, { createContext, useContext, useState, useEffect, ReactNode } from "react";
import en from "@/dictionaries/en.json";
import nl from "@/dictionaries/nl.json";

const dictionaries = { en, nl };
type Locale = "en" | "nl";

type I18nContextValue = {
  locale: Locale;
  setLocale: (l: Locale) => void;
  t: typeof en;
};

const I18nContext = createContext<I18nContextValue | null>(null);

export function useTranslation() {
  const ctx = useContext(I18nContext);
  if (!ctx) throw new Error("❌ useTranslation must be used within I18nProvider");
  return ctx;
}

export function I18nProvider({ children }: { children: ReactNode }) {
  const [locale, setLocaleState] = useState<Locale>("en");

  // Load preference from localStorage or detect from browser
  useEffect(() => {
    const saved = localStorage.getItem("antigravity_locale") as Locale;
    if (saved && (saved === "en" || saved === "nl")) {
      setLocaleState(saved);
    } else {
      // Automatic detection
      const browserLang = navigator.language.toLowerCase();
      if (browserLang.startsWith("nl")) {
        setLocaleState("nl");
      } else {
        setLocaleState("en");
      }
    }
  }, []);

  const setLocale = (l: Locale) => {
    setLocaleState(l);
    localStorage.setItem("antigravity_locale", l);
  };

  const t = dictionaries[locale];

  return (
    <I18nContext.Provider value={{ locale, setLocale, t }}>
      {children}
    </I18nContext.Provider>
  );
}
