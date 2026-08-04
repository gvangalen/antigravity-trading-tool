import { Platform, StyleSheet, Text, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { useAuth } from '../../auth/AuthProvider';
import { theme } from '../../constants/theme';
import type { MainTabParamList } from '../../navigation/MainTabNavigator';
import { preferenceColors, useAppPreferences } from '../../preferences/AppPreferencesProvider';
import { useIntelligenceContext } from '../../contexts/ActiveIntelligenceContext';
import { translate, type TranslationKey } from '../../i18n';

type WorkspaceHeaderProps = {
  routeName: keyof MainTabParamList;
};

const ROUTE_META: Record<
  keyof MainTabParamList,
  { labelKey: TranslationKey }
> = {
  Watchlist: {
    labelKey: 'workspace.analysis',
  },
  Setup: {
    labelKey: 'workspace.myPlan',
  },
  Automation: {
    labelKey: 'workspace.automation',
  },
  Portfolio: {
    labelKey: 'workspace.portfolio',
  },
  Report: {
    labelKey: 'workspace.reflection',
  },
  Settings: {
    labelKey: 'workspace.settings',
  },
};

export function WorkspaceHeader({ routeName }: WorkspaceHeaderProps) {
  const insets = useSafeAreaInsets();
  const { appearance, language } = useAppPreferences();
  const colors = preferenceColors(appearance);
  const { user } = useAuth();
  const { context } = useIntelligenceContext();
  const routeMeta = ROUTE_META[routeName];
  const label = translate(language, routeMeta.labelKey);
  const initials = userInitials(user?.first_name, user?.last_name, user?.email);
  const glassBackground = appearance === 'light' ? 'rgba(251, 252, 255, 0.64)' : 'rgba(9, 14, 26, 0.72)';
  const glassBorder = appearance === 'light' ? 'rgba(20, 35, 65, 0.04)' : 'rgba(226, 232, 240, 0.05)';
  const glassShadow = appearance === 'light' ? 'rgba(20, 35, 65, 0.02)' : 'rgba(2, 6, 23, 0.18)';

  return (
    <View
      style={[
        styles.container,
        {
          backgroundColor: glassBackground,
          borderBottomColor: glassBorder,
          paddingTop: Math.max(insets.top - 14, 4),
          shadowColor: glassShadow,
        },
      ]}
    >
      <View style={styles.topRow}>
        <View style={styles.identityBlock}>
          <View style={styles.logo}>
            <Text style={styles.logoText}>F</Text>
          </View>
          <View style={styles.copyBlock}>
            <Text style={[styles.brand, { color: colors.text }]}>FINN</Text>
            <Text style={[styles.contextLine, { color: colors.textDim }]}>
              {label.toUpperCase()} · {context.asset}
            </Text>
          </View>
        </View>

        <View style={styles.actions}>
          <View style={[styles.avatar, { backgroundColor: 'transparent', borderColor: colors.border }]}>
            <Text style={[styles.avatarText, { color: colors.text }]}>{initials}</Text>
          </View>
        </View>
      </View>
    </View>
  );
}

function userInitials(firstName?: string | null, lastName?: string | null, email?: string | null) {
  const first = firstName?.trim().charAt(0);
  const last = lastName?.trim().charAt(0);
  if (first || last) return `${first ?? ''}${last ?? ''}`.toUpperCase();
  return (email?.trim().charAt(0) || 'U').toUpperCase();
}

const styles = StyleSheet.create({
  actions: {
    alignItems: 'center',
    flexDirection: 'row',
    gap: theme.spacing.sm,
  },
  avatar: {
    alignItems: 'center',
    borderRadius: theme.radius.pill,
    borderWidth: 1,
    height: 34,
    justifyContent: 'center',
    width: 34,
  },
  avatarText: {
    fontSize: 14,
    fontWeight: '900',
  },
  brand: {
    fontSize: 13,
    fontWeight: '900',
    letterSpacing: -0.1,
  },
  container: {
    borderBottomWidth: 0.5,
    gap: 0,
    paddingHorizontal: theme.spacing.md,
    paddingBottom: 6,
    paddingTop: 0,
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: Platform.OS === 'ios' ? 1 : 0,
    shadowRadius: 10,
  },
  contextLine: {
    fontSize: 9,
    fontWeight: '800',
    letterSpacing: 1.1,
    marginTop: 0,
    textTransform: 'uppercase',
  },
  copyBlock: {
    flex: 1,
  },
  identityBlock: {
    alignItems: 'center',
    flex: 1,
    flexDirection: 'row',
    gap: 8,
  },
  logo: {
    alignItems: 'center',
    backgroundColor: theme.colors.accent,
    borderRadius: 9,
    height: 30,
    justifyContent: 'center',
    width: 30,
  },
  logoText: {
    color: '#ffffff',
    fontSize: 17,
    fontWeight: '900',
  },
  pressed: {
    opacity: 0.84,
    transform: [{ scale: 0.98 }],
  },
  topRow: {
    alignItems: 'center',
    flexDirection: 'row',
    gap: theme.spacing.xs,
  },
});
