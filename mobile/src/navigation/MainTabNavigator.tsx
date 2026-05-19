import { createBottomTabNavigator } from '@react-navigation/bottom-tabs';
import { StyleSheet } from 'react-native';

import { theme } from '../constants/theme';
import { Feather } from '@expo/vector-icons';
import { PortfolioScreen } from '../screens/PortfolioScreen';
import { ReportScreen } from '../screens/ReportScreen';
import { SettingsScreen } from '../screens/SettingsScreen';
import { SetupScreen } from '../screens/SetupScreen';
import { WatchlistScreen } from '../screens/WatchlistScreen';
import { preferenceColors, useAppPreferences } from '../preferences/AppPreferencesProvider';

export type MainTabParamList = {
  Watchlist: undefined;
  Setup: { notificationType?: string; symbol?: string } | undefined;
  Portfolio: undefined;
  Report: { notificationType?: string; symbol?: string } | undefined;
  Settings: undefined;
};

const Tab = createBottomTabNavigator<MainTabParamList>();

export function MainTabNavigator() {
  const { appearance } = useAppPreferences();
  const colors = preferenceColors(appearance);

  return (
    <Tab.Navigator
      initialRouteName="Watchlist"
      screenOptions={({ route }) => ({
        headerShown: false,
        tabBarActiveTintColor: colors.text,
        tabBarInactiveTintColor: colors.textDim,
        tabBarIcon: ({ color, size }) => {
          let iconName: "list" | "sliders" | "briefcase" | "bar-chart-2" = 'list';
          if (route.name === 'Watchlist') iconName = 'list';
          else if (route.name === 'Setup') iconName = 'sliders';
          else if (route.name === 'Portfolio') iconName = 'briefcase';
          else if (route.name === 'Report') iconName = 'bar-chart-2';
          
          return <Feather name={iconName} size={20} color={color} />;
        },
        tabBarLabelStyle: {
          fontSize: 10,
          fontWeight: '700',
          letterSpacing: 0,
          marginTop: 2,
        },
        tabBarStyle: {
          backgroundColor: colors.surface,
          borderTopColor: colors.border,
          borderTopWidth: 1,
          height: 80,
          paddingBottom: 24,
          paddingTop: 8,
        },
        tabBarItemStyle: {
          justifyContent: 'center',
        },
      })}
    >
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

const styles = StyleSheet.create({});
