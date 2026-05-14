import * as SecureStore from 'expo-secure-store';
import { ReactNode, createContext, useContext, useEffect, useMemo, useState } from 'react';

export type AppLanguage = 'nl' | 'en';
export type AppAppearance = 'system' | 'dark' | 'light';

type AppPreferencesContextValue = {
  appearance: AppAppearance;
  language: AppLanguage;
  loadingPreferences: boolean;
  setAppearance: (value: AppAppearance) => Promise<void>;
  setLanguage: (value: AppLanguage) => Promise<void>;
};

const LANGUAGE_KEY = 'tradamind_mobile_language';
const APPEARANCE_KEY = 'tradamind_mobile_appearance';

const AppPreferencesContext = createContext<AppPreferencesContextValue | undefined>(undefined);

export function AppPreferencesProvider({ children }: { children: ReactNode }) {
  const [language, setLanguageState] = useState<AppLanguage>('nl');
  const [appearance, setAppearanceState] = useState<AppAppearance>('system');
  const [loadingPreferences, setLoadingPreferences] = useState(true);

  useEffect(() => {
    let mounted = true;

    async function load() {
      const [storedLanguage, storedAppearance] = await Promise.all([
        SecureStore.getItemAsync(LANGUAGE_KEY),
        SecureStore.getItemAsync(APPEARANCE_KEY),
      ]);

      if (!mounted) return;
      if (storedLanguage === 'nl' || storedLanguage === 'en') {
        setLanguageState(storedLanguage);
      }
      if (storedAppearance === 'system' || storedAppearance === 'dark' || storedAppearance === 'light') {
        setAppearanceState(storedAppearance);
      }
      setLoadingPreferences(false);
    }

    load();
    return () => {
      mounted = false;
    };
  }, []);

  const setLanguage = async (value: AppLanguage) => {
    setLanguageState(value);
    await SecureStore.setItemAsync(LANGUAGE_KEY, value);
  };

  const setAppearance = async (value: AppAppearance) => {
    setAppearanceState(value);
    await SecureStore.setItemAsync(APPEARANCE_KEY, value);
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
    };
  }

  return {
    background: '#F8FAFC',
    backgroundSoft: '#EFF6FF',
    border: '#CBD5E1',
    borderStrong: '#93A4B8',
    borderSubtle: '#E2E8F0',
    surface: '#FFFFFF',
    surfaceElevated: '#FFFFFF',
    surfaceMuted: '#EAF2FF',
    text: '#0F172A',
    textDim: '#64748B',
    textMuted: '#475569',
    textSoft: '#1E293B',
  };
}
