import { StyleSheet, Text, View } from 'react-native';
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
  { descriptionKey: TranslationKey; labelKey: TranslationKey }
> = {
  Watchlist: {
    labelKey: 'workspace.analysis',
    descriptionKey: 'workspace.analysisDescription',
  },
  Setup: {
    labelKey: 'workspace.myPlan',
    descriptionKey: 'workspace.myPlanDescription',
  },
  Automation: {
    labelKey: 'workspace.automation',
    descriptionKey: 'workspace.automationDescription',
  },
  Portfolio: {
    labelKey: 'workspace.portfolio',
    descriptionKey: 'workspace.portfolioDescription',
  },
  Report: {
    labelKey: 'workspace.reflection',
    descriptionKey: 'workspace.reflectionDescription',
  },
  Settings: {
    labelKey: 'workspace.settings',
    descriptionKey: 'workspace.settingsDescription',
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
  const contextOwner = user?.first_name?.trim() || 'FINN';

  return (
    <View
      style={[
        styles.container,
        {
          backgroundColor: colors.surface,
          borderBottomColor: colors.border,
          paddingTop: Math.max(insets.top - 26, 2),
        },
      ]}
    >
      <View style={styles.topRow}>
        <View style={styles.identityBlock}>
          <View style={styles.logo}>
            <Text style={styles.logoText}>F</Text>
          </View>
          <View style={styles.copyBlock}>
            <Text style={[styles.brand, { color: colors.text }]}>FINN Workspace</Text>
            <Text style={[styles.contextLine, { color: colors.textDim }]}>
              {label.toUpperCase()} · {context.asset}
            </Text>
          </View>
        </View>

        <View style={styles.actions}>
          <View style={[styles.avatar, { backgroundColor: colors.surfaceMuted, borderColor: colors.borderStrong }]}>
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
    height: 40,
    justifyContent: 'center',
    width: 40,
  },
  avatarText: {
    fontSize: 15,
    fontWeight: '900',
  },
  brand: {
    fontSize: 16,
    fontWeight: '900',
    letterSpacing: -0.6,
  },
  container: {
    borderBottomWidth: 0.5,
    gap: 0,
    paddingHorizontal: 14,
    paddingBottom: 6,
    paddingTop: 0,
  },
  contextLine: {
    fontSize: 11,
    fontWeight: '800',
    letterSpacing: 1.4,
    marginTop: 1,
    textTransform: 'uppercase',
  },
  copyBlock: {
    flex: 1,
  },
  identityBlock: {
    alignItems: 'center',
    flex: 1,
    flexDirection: 'row',
    gap: 12,
  },
  logo: {
    alignItems: 'center',
    backgroundColor: theme.colors.accent,
    borderRadius: 14,
    height: 44,
    justifyContent: 'center',
    width: 44,
  },
  logoText: {
    color: '#ffffff',
    fontSize: 23,
    fontWeight: '900',
  },
  pressed: {
    opacity: 0.84,
    transform: [{ scale: 0.98 }],
  },
  topRow: {
    alignItems: 'center',
    flexDirection: 'row',
    gap: 8,
  },
});
