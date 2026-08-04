import { NavigationContainer, useNavigationContainerRef } from '@react-navigation/native';
import * as Notifications from 'expo-notifications';
import { StatusBar } from 'expo-status-bar';
import { useEffect, useState } from 'react';
import { ActivityIndicator, StyleSheet, View } from 'react-native';
import { GestureHandlerRootView } from 'react-native-gesture-handler';
import { SafeAreaProvider } from 'react-native-safe-area-context';

import { AuthProvider, useAuth } from './src/auth/AuthProvider';
import { theme } from './src/constants/theme';
import { MainTabNavigator, MainTabParamList } from './src/navigation/MainTabNavigator';
import { AppPreferencesProvider, preferenceColors, useAppPreferences } from './src/preferences/AppPreferencesProvider';
import { extractBackendAppLanguage } from './src/preferences/appLocale';
import { LoginScreen } from './src/screens/LoginScreen';
import { assistantApi } from './src/services/tradamindApi';
import { normalizeNotificationData, routeForNotification } from './src/services/pushNotifications';
import { ActiveIntelligenceProvider } from './src/contexts/ActiveIntelligenceContext';
import { FinnOverlayProvider } from './src/contexts/FinnOverlayContext';

export default function App() {
  return (
    <GestureHandlerRootView style={styles.gestureRoot}>
      <SafeAreaProvider>
        <AppPreferencesProvider>
          <ActiveIntelligenceProvider>
            <AuthProvider>
              <FinnOverlayProvider>
                <AppShell />
              </FinnOverlayProvider>
            </AuthProvider>
          </ActiveIntelligenceProvider>
        </AppPreferencesProvider>
      </SafeAreaProvider>
    </GestureHandlerRootView>
  );
}

import { useFinnOverlay } from './src/contexts/FinnOverlayContext';

function AppShell() {
  const navigationRef = useNavigationContainerRef<MainTabParamList>();
  const { appearance, language, loadingPreferences, setLanguage } = useAppPreferences();
  const { user } = useAuth();
  const { openFinn } = useFinnOverlay();
  const colors = preferenceColors(appearance);
  const [localeSyncing, setLocaleSyncing] = useState(false);

  useEffect(() => {
    if (!user) {
      setLocaleSyncing(false);
      return;
    }

    let mounted = true;
    setLocaleSyncing(true);

    assistantApi
      .preferences()
      .then(async (preferences) => {
        const backendLocale = extractBackendAppLanguage(preferences, language);
        if (!mounted || backendLocale === language) return;
        await setLanguage(backendLocale);
      })
      .catch(() => undefined)
      .finally(() => {
        if (mounted) {
          setLocaleSyncing(false);
        }
      });

    return () => {
      mounted = false;
    };
  }, [language, setLanguage, user]);

  useEffect(() => {
    if (!user) return;

    const openNotification = (response: Notifications.NotificationResponse | null) => {
      if (!response || !navigationRef.isReady()) return;

      const rawData = response.notification.request.content.data as Record<string, unknown> | undefined;
      const route = routeForNotification(normalizeNotificationData(rawData));
      if (route.screen === 'FINN') {
        openFinn(route.params);
      } else if (route.screen === 'Automation') {
        navigationRef.navigate('Automation', route.params);
      } else if (route.screen === 'Setup') {
        navigationRef.navigate('Setup', route.params);
      } else if (route.screen === 'Report') {
        navigationRef.navigate('Report', route.params);
      } else {
        navigationRef.navigate('Watchlist');
      }
    };

    const subscription = Notifications.addNotificationResponseReceivedListener(openNotification);
    Notifications.getLastNotificationResponseAsync().then(openNotification).catch(() => undefined);

    return () => {
      subscription.remove();
    };
  }, [navigationRef, user]);

  if (loadingPreferences || localeSyncing) {
    return (
      <View style={[styles.loading, { backgroundColor: colors.background }]}>
        <ActivityIndicator color={theme.colors.accent} />
      </View>
    );
  }

  return (
    <NavigationContainer
      ref={navigationRef}
      theme={{
        colors: {
          background: colors.background,
          border: colors.border,
          card: colors.surface,
          notification: theme.colors.danger,
          primary: theme.colors.accent,
          text: colors.text,
        },
        dark: appearance !== 'light',
        fonts: {
          bold: { fontFamily: 'System', fontWeight: '700' },
          heavy: { fontFamily: 'System', fontWeight: '900' },
          medium: { fontFamily: 'System', fontWeight: '500' },
          regular: { fontFamily: 'System', fontWeight: '400' },
        },
      }}
    >
      <StatusBar style={appearance === 'light' ? 'dark' : 'light'} />
      <AuthGate />
    </NavigationContainer>
  );
}

function AuthGate() {
  const { initializing, user } = useAuth();

  if (initializing) {
    return (
      <View style={styles.loading}>
        <ActivityIndicator color={theme.colors.accent} />
      </View>
    );
  }

  return user ? <MainTabNavigator /> : <LoginScreen />;
}

const styles = StyleSheet.create({
  gestureRoot: {
    flex: 1,
  },
  loading: {
    alignItems: 'center',
    backgroundColor: theme.colors.background,
    flex: 1,
    justifyContent: 'center',
  },
});
