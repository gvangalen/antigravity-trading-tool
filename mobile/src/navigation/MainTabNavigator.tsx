import { createBottomTabNavigator } from '@react-navigation/bottom-tabs';
import { StyleSheet, Text, View } from 'react-native';

import { theme } from '../constants/theme';
import { FinnScreen } from '../screens/FinnScreen';
import { PortfolioScreen } from '../screens/PortfolioScreen';
import { ReportScreen } from '../screens/ReportScreen';
import { SettingsScreen } from '../screens/SettingsScreen';
import { SetupScreen } from '../screens/SetupScreen';
import { WatchlistScreen } from '../screens/WatchlistScreen';

export type MainTabParamList = {
  FINN: { prefill?: string; source?: string } | undefined;
  Watchlist: undefined;
  Setup: { notificationType?: string; symbol?: string } | undefined;
  Portfolio: undefined;
  Report: { notificationType?: string; symbol?: string } | undefined;
  Settings: undefined;
};

const Tab = createBottomTabNavigator<MainTabParamList>();

const tabIcons: Record<keyof MainTabParamList, string> = {
  FINN: 'FN',
  Watchlist: 'WL',
  Setup: 'SU',
  Portfolio: 'PF',
  Report: 'RP',
  Settings: 'ST',
};

import { preferenceColors, useAppPreferences } from '../preferences/AppPreferencesProvider';

export function MainTabNavigator() {
  const { appearance } = useAppPreferences();
  const colors = preferenceColors(appearance);

  return (
    <Tab.Navigator
      initialRouteName="FINN"
      screenOptions={({ route }) => ({
        headerShown: false,
        tabBarActiveTintColor: theme.colors.accent,
        tabBarInactiveTintColor: colors.textDim,
        tabBarIcon: ({ color, focused }) => (
          <View
            style={[
              styles.iconBadge,
              focused && { backgroundColor: appearance === 'light' ? '#EFF6FF' : theme.colors.accentSoft },
              focused && { borderColor: theme.colors.accent },
            ]}
          >
            <Text style={[styles.iconText, { color }]}>{tabIcons[route.name]}</Text>
          </View>
        ),
        tabBarLabelStyle: {
          fontSize: 11,
          fontWeight: '900',
          letterSpacing: 0,
        },
        tabBarStyle: {
          backgroundColor: colors.surface,
          borderTopColor: colors.border,
          borderTopWidth: 1,
          height: 84,
          paddingBottom: 12,
          paddingTop: 10,
        },
        tabBarItemStyle: {
          paddingVertical: 2,
        },
      })}
    >
      <Tab.Screen name="FINN" component={FinnScreen} />
      <Tab.Screen name="Watchlist" component={WatchlistScreen} />
      <Tab.Screen name="Setup" component={SetupScreen} />
      <Tab.Screen name="Portfolio" component={PortfolioScreen} />
      <Tab.Screen name="Report" component={ReportScreen} />
      <Tab.Screen
        name="Settings"
        component={SettingsScreen}
        options={{
          tabBarButton: () => null,
          tabBarItemStyle: { display: 'none' },
        }}
      />
    </Tab.Navigator>
  );
}

const styles = StyleSheet.create({
  iconBadge: {
    alignItems: 'center',
    borderColor: 'transparent',
    borderRadius: theme.radius.sm,
    borderWidth: 1,
    height: 28,
    justifyContent: 'center',
    width: 34,
  },
  iconBadgeActive: {
    backgroundColor: theme.colors.accentSoft,
  },
  iconText: {
    fontSize: 10,
    fontWeight: '900',
  },
});
