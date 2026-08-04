import { createBottomTabNavigator } from '@react-navigation/bottom-tabs';
import { StyleSheet, View } from 'react-native';

import { theme } from '../constants/theme';
import { Feather } from '@expo/vector-icons';
import { AutomationScreen } from '../screens/AutomationScreen';
import { FloatingFinnComposer } from '../components/layout/FloatingFinnComposer';
import { PortfolioScreen } from '../screens/PortfolioScreen';
import { ReportScreen } from '../screens/ReportScreen';
import { SettingsScreen } from '../screens/SettingsScreen';
import { SetupScreen } from '../screens/SetupScreen';
import { WatchlistScreen } from '../screens/WatchlistScreen';
import { preferenceColors, useAppPreferences } from '../preferences/AppPreferencesProvider';
import { WorkspaceHeader } from '../components/layout/WorkspaceHeader';
import { translate } from '../i18n';

export type MainTabParamList = {
  Watchlist: undefined;
  Setup: { notificationType?: string; symbol?: string } | undefined;
  Automation: { notificationType?: string; symbol?: string } | undefined;
  Portfolio: undefined;
  Report: { notificationType?: string; symbol?: string } | undefined;
  Settings: undefined;
};

const Tab = createBottomTabNavigator<MainTabParamList>();

export function MainTabNavigator() {
  const { appearance, language } = useAppPreferences();
  const colors = preferenceColors(appearance);

  return (
    <View style={styles.shell}>
      <Tab.Navigator
        initialRouteName="Watchlist"
        screenOptions={({ route }) => ({
          header: () => <WorkspaceHeader routeName={route.name} />,
          headerStatusBarHeight: 0,
          headerStyle: {
            height: 68,
          },
          tabBarActiveTintColor: colors.accent,
          tabBarInactiveTintColor: colors.textDim,
          tabBarIcon: ({ color, size }) => {
            let iconName: "bar-chart-2" | "sliders" | "briefcase" | "file-text" | "cpu" = 'bar-chart-2';
            if (route.name === 'Watchlist') iconName = 'bar-chart-2';
            else if (route.name === 'Setup') iconName = 'sliders';
            else if (route.name === 'Automation') iconName = 'cpu';
            else if (route.name === 'Portfolio') iconName = 'briefcase';
            else if (route.name === 'Report') iconName = 'file-text';

            return <Feather name={iconName} size={20} color={color} />;
          },
          tabBarLabel:
            route.name === 'Watchlist'
              ? translate(language, 'workspace.analysis')
              : route.name === 'Setup'
                ? translate(language, 'workspace.myPlan')
                : route.name === 'Automation'
                  ? translate(language, 'workspace.automation')
                  : route.name === 'Portfolio'
                    ? translate(language, 'workspace.portfolio')
                    : route.name === 'Report'
                      ? translate(language, 'workspace.reflection')
                      : translate(language, 'workspace.settings'),
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
            height: 84,
            paddingBottom: 24,
            paddingTop: 8,
          },
          tabBarItemStyle: {
            justifyContent: 'center',
          },
          sceneStyle: {
            backgroundColor: colors.background,
          },
        })}
      >
        <Tab.Screen name="Watchlist" component={WatchlistScreen} />
        <Tab.Screen name="Setup" component={SetupScreen} />
        <Tab.Screen name="Automation" component={AutomationScreen} />
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
      <FloatingFinnComposer />
    </View>
  );
}

const styles = StyleSheet.create({
  shell: {
    flex: 1,
  },
});
