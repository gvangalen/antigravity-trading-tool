import { createBottomTabNavigator } from '@react-navigation/bottom-tabs';
import { Text } from 'react-native';

import { theme } from '../constants/theme';
import { AssistantScreen } from '../screens/AssistantScreen';
import { SettingsScreen } from '../screens/SettingsScreen';
import { StrategyScreen } from '../screens/StrategyScreen';
import { TodayScreen } from '../screens/TodayScreen';

export type MainTabParamList = {
  Assistant: undefined;
  Today: undefined;
  Strategy: undefined;
  Settings: undefined;
};

const Tab = createBottomTabNavigator<MainTabParamList>();

const tabIcons: Record<keyof MainTabParamList, string> = {
  Assistant: 'AI',
  Today: 'TD',
  Strategy: 'ST',
  Settings: 'SE',
};

export function MainTabNavigator() {
  return (
    <Tab.Navigator
      initialRouteName="Assistant"
      screenOptions={({ route }) => ({
        headerShown: false,
        tabBarActiveTintColor: theme.colors.accent,
        tabBarInactiveTintColor: theme.colors.textMuted,
        tabBarIcon: ({ color }) => (
          <Text style={{ color, fontSize: 11, fontWeight: '900' }}>{tabIcons[route.name]}</Text>
        ),
        tabBarLabelStyle: {
          fontSize: 12,
          fontWeight: '800',
        },
        tabBarStyle: {
          backgroundColor: theme.colors.surface,
          borderTopColor: theme.colors.border,
          height: 76,
          paddingBottom: 12,
          paddingTop: 8,
        },
      })}
    >
      <Tab.Screen name="Assistant" component={AssistantScreen} />
      <Tab.Screen name="Today" component={TodayScreen} />
      <Tab.Screen name="Strategy" component={StrategyScreen} />
      <Tab.Screen name="Settings" component={SettingsScreen} />
    </Tab.Navigator>
  );
}
