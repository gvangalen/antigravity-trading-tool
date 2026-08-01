import { ReactNode, createContext, useContext, useEffect, useMemo, useState } from 'react';

import { getItemAsync, setItemAsync } from '../services/secureStore';
import { getAccessToken } from '../services/tokenStorage';
import { assistantApi } from '../services/tradamindApi';
import {
  AppLanguage,
  DEFAULT_APP_LANGUAGE,
  LANGUAGE_KEY,
  extractBackendAppLanguage,
  normalizeAppLanguage,
  setStoredAppLanguage,
  subscribeAppLanguage,
} from './appLocale';

export type { AppLanguage } from './appLocale';

export type AppAppearance = 'system' | 'dark' | 'light';

type AppPreferencesContextValue = {
  appearance: AppAppearance;
  language: AppLanguage;
  loadingPreferences: boolean;
  setAppearance: (value: AppAppearance) => Promise<void>;
  setLanguage: (value: AppLanguage) => Promise<void>;
};

const APPEARANCE_KEY = 'tradamind_mobile_appearance';

const AppPreferencesContext = createContext<AppPreferencesContextValue | undefined>(undefined);

export function AppPreferencesProvider({ children }: { children: ReactNode }) {
  const [language, setLanguageState] = useState<AppLanguage>(DEFAULT_APP_LANGUAGE);
  const [appearance, setAppearanceState] = useState<AppAppearance>('system');
  const [loadingPreferences, setLoadingPreferences] = useState(true);

  useEffect(() => {
    let mounted = true;

    async function load() {
      const [storedLanguage, storedAppearance] = await Promise.all([
        getItemAsync(LANGUAGE_KEY),
        getItemAsync(APPEARANCE_KEY),
      ]);

      if (!mounted) return;
      const nextLanguage = normalizeAppLanguage(storedLanguage);
      setLanguageState(nextLanguage);
      if (storedAppearance === 'system' || storedAppearance === 'dark' || storedAppearance === 'light') {
        setAppearanceState(storedAppearance);
      }

      const token = await getAccessToken();
      if (token) {
        try {
          const preferences = await assistantApi.preferences();
          const backendLocale = extractBackendAppLanguage(preferences, nextLanguage);
          if (!mounted) return;
          setLanguageState(backendLocale);
          await setStoredAppLanguage(backendLocale);
        } catch {
          // Keep local preference when backend locale lookup is unavailable.
        }
      }

      setLoadingPreferences(false);
    }

    load();
    return () => {
      mounted = false;
    };
  }, []);

  useEffect(() => {
    return subscribeAppLanguage((nextLanguage) => {
      setLanguageState(nextLanguage);
    });
  }, []);

  const setLanguage = async (value: AppLanguage) => {
    setLanguageState(value);
    await setStoredAppLanguage(value);
  };

  const setAppearance = async (value: AppAppearance) => {
    setAppearanceState(value);
    await setItemAsync(APPEARANCE_KEY, value);
  };

  const value = useMemo(
    () => ({
      appearance,
      language,
      loadingPreferences,
      setAppearance,
      setLanguage,
    }),
    [appearance, language, loadingPreferences],
  );

  return <AppPreferencesContext.Provider value={value}>{children}</AppPreferencesContext.Provider>;
}

export function useAppPreferences() {
  const context = useContext(AppPreferencesContext);
  if (!context) {
    throw new Error('useAppPreferences must be used within AppPreferencesProvider');
  }
  return context;
}

export function preferenceLabels(language: AppLanguage) {
  return {
    accountDescription:
      language === 'nl'
        ? 'Beheer je mobiele profiel, voorkeuren en sessie zonder de trading flow te onderbreken.'
        : 'Manage your mobile profile, preferences and session without interrupting the trading flow.',
    accountTitle: language === 'nl' ? 'Account & instellingen' : 'Account & settings',
    active: language === 'nl' ? 'Actief' : 'Active',
    appearanceTitle: language === 'nl' ? 'Dark Mode' : 'Dark Mode',
    back: language === 'nl' ? 'Terug' : 'Back',
    close: language === 'nl' ? 'Sluiten' : 'Close',
    dark: language === 'nl' ? 'Donker' : 'Dark',
    deviceSettings: language === 'nl' ? 'Open device instellingen' : 'Open device settings',
    emailFallback: language === 'nl' ? 'Geen e-mail geladen' : 'No email loaded',
    english: 'English',
    german: 'Deutsch',
    languageTitle: language === 'nl' ? 'Taal' : 'Language',
    light: language === 'nl' ? 'Licht' : 'Light',
    logout: language === 'nl' ? 'Uitloggen' : 'Log out',
    mobileSession: language === 'nl' ? 'Mobiele sessie' : 'Mobile session',
    name: language === 'nl' ? 'Naam' : 'Name',
    nederlands: 'Nederlands',
    profile: 'Profile',
    profileLabel: 'Profile',
    profileMenu: language === 'nl' ? 'Profile menu' : 'Profile menu',
    pushCopy:
      language === 'nl'
        ? 'Pushmeldingen openen straks altijd context, nooit direct een koop- of verkoopactie.'
        : 'Push notifications will open context, never direct buy or sell actions.',
    pushSubtitle: language === 'nl' ? 'Beheer op device' : 'Manage on device',
    pushTitle: language === 'nl' ? 'Pushmeldingen' : 'Push notifications',
    select: language === 'nl' ? 'Kiezen' : 'Select',
    selected: language === 'nl' ? 'Geselecteerd' : 'Selected',
    session: 'Session',
    sessionActive: language === 'nl' ? 'Ingelogd op dit device' : 'Signed in on this device',
    sessionChecking:
      language === 'nl' ? 'Connectie wordt opnieuw gecontroleerd' : 'Connection is being checked again',
    sessionCopy:
      language === 'nl'
        ? 'Uitloggen wist de lokale mobile tokens. Je desktop-cookie sessie blijft los daarvan beheerd door de webapp.'
        : 'Logging out clears local mobile tokens. Your desktop cookie session is managed separately by the web app.',
    status: 'Status',
    systemDefault: language === 'nl' ? 'Systeemstandaard' : 'System default',
  };
}

export function preferenceColors(appearance: AppAppearance) {
  if (appearance !== 'light') {
    return {
      background: '#020617',
      backgroundSoft: '#07111F',
      border: '#1E293B',
      borderStrong: '#334155',
      borderSubtle: '#162033',
      surface: '#0F172A',
      surfaceElevated: '#111C31',
      surfaceMuted: '#17233A',
      text: '#F8FAFC',
      textDim: '#94A3B8',
      textMuted: '#CBD5E1',
      textSoft: '#E2E8F0',
      accent: '#2563EB',
      success: '#10B981',
      warning: '#F59E0B',
      danger: '#F43F5E',
    };
  }

  return {
    background: '#FFFFFF',
    backgroundSoft: '#FFFFFF',
    border: '#D7E0EA',
    borderStrong: '#A5B4C7',
    borderSubtle: '#E9EEF5',
    surface: '#FFFFFF',
    surfaceElevated: '#FFFFFF',
    surfaceMuted: '#F7FAFC',
    text: '#0F172A',
    textDim: '#64748B',
    textMuted: '#526276',
    textSoft: '#1E293B',
    accent: '#2563EB',
    success: '#10B981',
    warning: '#F59E0B',
    danger: '#E11D48',
  };
}
