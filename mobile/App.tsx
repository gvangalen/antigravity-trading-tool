import { NavigationContainer, useNavigationContainerRef } from '@react-navigation/native';
import * as Notifications from 'expo-notifications';
import { StatusBar } from 'expo-status-bar';
import { useEffect } from 'react';
import { ActivityIndicator, StyleSheet, View } from 'react-native';
import { SafeAreaProvider } from 'react-native-safe-area-context';

import { AuthProvider, useAuth } from './src/auth/AuthProvider';
import { theme } from './src/constants/theme';
import { MainTabNavigator, MainTabParamList } from './src/navigation/MainTabNavigator';
import { AppPreferencesProvider, preferenceColors, useAppPreferences } from './src/preferences/AppPreferencesProvider';
import { LoginScreen } from './src/screens/LoginScreen';
import { normalizeNotificationData, routeForNotification } from './src/services/pushNotifications';

export default function App() {
  return (
    <SafeAreaProvider>
      <AppPreferencesProvider>
        <AuthProvider>
          <AppShell />
        </AuthProvider>
      </AppPreferencesProvider>
    </SafeAreaProvider>
  );
}

function AppShell() {
  const navigationRef = useNavigationContainerRef<MainTabParamList>();
  const { appearance } = useAppPreferences();
  const { user } = useAuth();
  const colors = preferenceColors(appearance);

  useEffect(() => {
    if (!user) return;

    const openNotification = (response: Notifications.NotificationResponse | null) => {
      if (!response || !navigationRef.isReady()) return;

      const rawData = response.notification.request.content.data as Record<string, unknown> | undefined;
      const route = routeForNotification(normalizeNotificationData(rawData));
      if (route.screen === 'FINN') {
        navigationRef.navigate('FINN', route.params);
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
  loading: {
    alignItems: 'center',
    backgroundColor: theme.colors.background,
    flex: 1,
    justifyContent: 'center',
  },
});
