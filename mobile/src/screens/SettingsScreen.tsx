import { useNavigation } from '@react-navigation/native';
import type { NavigationProp } from '@react-navigation/native';
import { useCallback, useEffect, useState } from 'react';
import { ActivityIndicator, Linking, Pressable, StyleSheet, Text, View } from 'react-native';

import { useAuth } from '../auth/AuthProvider';
import { CardShell } from '../components/cards/CardShell';
import { ScreenContainer } from '../components/layout/ScreenContainer';
import { SectionHeader } from '../components/layout/SectionHeader';
import { StatusChip } from '../components/layout/StatusChip';
import { BottomSheet } from '../components/sheets/BottomSheet';
import { theme } from '../constants/theme';
import { useApiResource } from '../hooks/useApiResource';
import type { MainTabParamList } from '../navigation/MainTabNavigator';
import { AppAppearance, AppLanguage, preferenceColors, preferenceLabels, useAppPreferences } from '../preferences/AppPreferencesProvider';
import { authApi } from '../services/authApi';
import {
  getStoredPushToken,
  registerMobilePushToken,
  unregisterMobilePushToken,
} from '../services/pushNotifications';
import { triggerHaptic } from '../utils/haptics';
import { useFinnOverlay } from '../contexts/FinnOverlayContext';

type SettingsSheet = 'profile' | 'language' | 'theme' | 'push' | 'session' | null;

export function SettingsScreen() {
  const navigation = useNavigation<NavigationProp<MainTabParamList>>();
  const { openFinn } = useFinnOverlay();
  const { loading, logout, refreshUser, user } = useAuth();
  const { appearance, language, setAppearance, setLanguage } = useAppPreferences();
  const [sheet, setSheet] = useState<SettingsSheet>(null);
  const [pushToken, setPushToken] = useState<string | null>(null);
  const [pushStatus, setPushStatus] = useState('');
  const [pushLoading, setPushLoading] = useState(false);
  const labels = preferenceLabels(language);
  const colors = preferenceColors(appearance);
  const fetchHealth = useCallback(() => authApi.health(), []);
  const healthResource = useApiResource({
    fallbackData: undefined,
    fetcher: fetchHealth,
  });

  useEffect(() => {
    getStoredPushToken().then(setPushToken).catch(() => undefined);
  }, []);

  async function handleLogout() {
    await triggerHaptic('impact');
    await logout();
  }

  async function handleEnablePush() {
    if (!user?.id) return;
    setPushLoading(true);
    setPushStatus('');
    try {
      const result = await registerMobilePushToken(user.id);
      if (result.status === 'registered') {
        setPushToken(result.token);
        setPushStatus(language === 'nl' ? 'Pushmeldingen zijn gekoppeld aan dit device.' : 'Push notifications are connected to this device.');
      } else {
        setPushStatus(result.reason);
      }
    } catch (error) {
      setPushStatus(error instanceof Error ? error.message : 'Push registration failed.');
    } finally {
      setPushLoading(false);
    }
  }

  async function handleDisablePush() {
    setPushLoading(true);
    setPushStatus('');
    try {
      await unregisterMobilePushToken();
      setPushToken(null);
      setPushStatus(language === 'nl' ? 'Pushmeldingen zijn losgekoppeld.' : 'Push notifications are disconnected.');
    } catch (error) {
      setPushStatus(error instanceof Error ? error.message : 'Push unsubscribe failed.');
    } finally {
      setPushLoading(false);
    }
  }

  return (
    <ScreenContainer
      refreshing={healthResource.refreshing}
      onRefresh={() => {
        healthResource.refresh();
        refreshUser();
      }}
    >
      <View style={styles.topBar}>
        <Pressable
          onPress={async () => {
            await triggerHaptic('selection');
            openFinn();
          }}
          style={({ pressed }) => [styles.backButton, pressed && styles.pressed]}
        >
          <Text style={styles.backText}>{labels.back}</Text>
        </Pressable>
        <StatusChip
          label={healthResource.isStale ? 'API stale' : 'API live'}
          tone={healthResource.isStale ? 'warning' : 'success'}
        />
      </View>

      <SectionHeader
        label={labels.profileLabel}
        title={labels.accountTitle}
        description={labels.accountDescription}
      />

      <ProfileCard colors={colors} labels={labels} user={user} />

      <CardShell>
        <Text style={styles.cardLabel}>{labels.profileMenu}</Text>
        <MenuRow
          colors={colors}
          icon="PR"
          title={labels.profile}
          subtitle={user?.email || labels.emailFallback}
          onPress={() => setSheet('profile')}
        />
        <MenuRow
          colors={colors}
          icon="NL"
          title={labels.languageTitle}
          subtitle={languageLabel(language)}
          onPress={() => setSheet('language')}
        />
        <MenuRow
          colors={colors}
          icon="DM"
          title={labels.appearanceTitle}
          subtitle={appearanceLabel(appearance, labels)}
          onPress={() => setSheet('theme')}
        />
        <MenuRow
          colors={colors}
          icon="PS"
          title={labels.pushTitle}
          subtitle={pushToken ? (language === 'nl' ? 'Ingeschakeld op dit device' : 'Enabled on this device') : labels.pushSubtitle}
          onPress={() => setSheet('push')}
        />
        <MenuRow
          colors={colors}
          icon="SE"
          title={labels.session}
          subtitle={healthResource.isStale ? labels.sessionChecking : labels.sessionActive}
          onPress={() => setSheet('session')}
        />
      </CardShell>

      <BottomSheet visible={sheet === 'profile'} title={labels.profile} onClose={() => setSheet(null)}>
        <ProfileDetail colors={colors} labels={labels} user={user} />
      </BottomSheet>

      <BottomSheet visible={sheet === 'language'} title={labels.languageTitle} onClose={() => setSheet(null)}>
        <OptionList
          colors={colors}
          labels={labels}
          selected={language}
          options={[
            { label: labels.nederlands, value: 'nl' },
            { label: labels.english, value: 'en' },
          ]}
          onSelect={async (nextValue) => {
            await setLanguage(nextValue);
            setSheet(null);
          }}
        />
      </BottomSheet>

      <BottomSheet visible={sheet === 'theme'} title={labels.appearanceTitle} onClose={() => setSheet(null)}>
        <OptionList
          colors={colors}
          labels={labels}
          selected={appearance}
          options={[
            { label: labels.systemDefault, value: 'system' },
            { label: labels.dark, value: 'dark' },
            { label: labels.light, value: 'light' },
          ]}
          onSelect={async (nextValue) => {
            await setAppearance(nextValue);
            setSheet(null);
          }}
        />
      </BottomSheet>

      <BottomSheet visible={sheet === 'push'} title={labels.pushTitle} onClose={() => setSheet(null)}>
        <Text style={[styles.sheetCopy, { color: colors.textMuted }]}>{labels.pushCopy}</Text>
        {pushStatus ? <Text style={[styles.pushStatus, { color: colors.textSoft }]}>{pushStatus}</Text> : null}
        <Pressable
          disabled={pushLoading}
          onPress={pushToken ? handleDisablePush : handleEnablePush}
          style={({ pressed }) => [
            styles.secondaryButton,
            pushToken && styles.warningButton,
            pushLoading && styles.disabled,
            pressed && styles.pressed,
          ]}
        >
          {pushLoading ? (
            <ActivityIndicator color={theme.colors.white} />
          ) : (
            <Text style={styles.secondaryButtonText}>
              {pushToken
                ? language === 'nl'
                  ? 'Push uitschakelen'
                  : 'Disable push'
                : language === 'nl'
                  ? 'Push inschakelen'
                  : 'Enable push'}
            </Text>
          )}
        </Pressable>
        <Pressable
          onPress={async () => {
            await triggerHaptic('selection');
            Linking.openSettings();
          }}
          style={({ pressed }) => [styles.secondaryButton, pressed && styles.pressed]}
        >
          <Text style={styles.secondaryButtonText}>{labels.deviceSettings}</Text>
        </Pressable>
      </BottomSheet>

      <BottomSheet visible={sheet === 'session'} title={labels.session} onClose={() => setSheet(null)}>
        <Text style={[styles.sheetCopy, { color: colors.textMuted }]}>{labels.sessionCopy}</Text>
        <Pressable
          disabled={loading}
          onPress={handleLogout}
          style={({ pressed }) => [styles.logoutButton, loading && styles.disabled, pressed && styles.pressed]}
        >
          {loading ? <ActivityIndicator color={theme.colors.white} /> : <Text style={styles.logoutText}>{labels.logout}</Text>}
        </Pressable>
      </BottomSheet>
    </ScreenContainer>
  );
}

type PreferenceColors = ReturnType<typeof preferenceColors>;
type PreferenceLabels = ReturnType<typeof preferenceLabels>;

function ProfileCard({ colors, labels, user }: { colors: PreferenceColors; labels: PreferenceLabels; user: ReturnType<typeof useAuth>['user'] }) {
  const initials = userInitials(user?.first_name, user?.last_name, user?.email);
  const fullName = [user?.first_name, user?.last_name].filter(Boolean).join(' ') || 'Mobile user';

  return (
    <CardShell emphasis="primary">
      <View style={styles.profileRow}>
        <View style={[styles.avatarLarge, { backgroundColor: colors.surfaceMuted, borderColor: theme.colors.accent }]}>
          <Text style={styles.avatarLargeText}>{initials}</Text>
        </View>
        <View style={styles.profileCopy}>
          <Text style={[styles.profileName, { color: colors.text }]}>{fullName}</Text>
          <Text style={[styles.profileEmail, { color: colors.textDim }]}>{user?.email || labels.emailFallback}</Text>
          <View style={styles.profileChips}>
            <StatusChip compact label={user?.is_active ? labels.active : 'Inactive'} tone={user?.is_active ? 'success' : 'warning'} />
            <StatusChip compact label={labels.mobileSession} tone="accent" />
          </View>
        </View>
      </View>
    </CardShell>
  );
}

function MenuRow({
  colors,
  icon,
  title,
  subtitle,
  onPress,
}: {
  colors: PreferenceColors;
  icon: string;
  title: string;
  subtitle: string;
  onPress: () => void;
}) {
  return (
    <Pressable
      onPress={async () => {
        await triggerHaptic('selection');
        onPress();
      }}
      style={({ pressed }) => [styles.menuRow, pressed && styles.pressed]}
    >
      <View style={[styles.menuIcon, { backgroundColor: colors.backgroundSoft, borderColor: colors.border }]}>
        <Text style={styles.menuIconText}>{icon}</Text>
      </View>
      <View style={styles.menuCopy}>
        <Text style={[styles.menuTitle, { color: colors.text }]}>{title}</Text>
        <Text style={[styles.menuSubtitle, { color: colors.textDim }]}>{subtitle}</Text>
      </View>
      <Text style={[styles.chevron, { color: colors.textDim }]}>›</Text>
    </Pressable>
  );
}

function ProfileDetail({ colors, labels, user }: { colors: PreferenceColors; labels: PreferenceLabels; user: ReturnType<typeof useAuth>['user'] }) {
  const fullName = [user?.first_name, user?.last_name].filter(Boolean).join(' ') || 'Mobile user';

  return (
    <View style={styles.detailStack}>
      <DetailRow colors={colors} label={labels.name} value={fullName} />
      <DetailRow colors={colors} label="Email" value={user?.email || labels.emailFallback} />
      <DetailRow colors={colors} label={labels.status} value={user?.is_active ? labels.active : 'Inactive'} />
    </View>
  );
}

function DetailRow({ colors, label, value }: { colors: PreferenceColors; label: string; value: string }) {
  return (
    <View style={[styles.detailRow, { backgroundColor: colors.backgroundSoft, borderColor: colors.border }]}>
      <Text style={[styles.detailLabel, { color: colors.textDim }]}>{label}</Text>
      <Text style={[styles.detailValue, { color: colors.text }]}>{value}</Text>
    </View>
  );
}

function OptionList<TValue extends string>({
  colors,
  labels,
  options,
  selected,
  onSelect,
}: {
  colors: PreferenceColors;
  labels: PreferenceLabels;
  options: { label: string; value: TValue }[];
  selected: TValue;
  onSelect: (value: TValue) => Promise<void>;
}) {
  return (
    <View style={styles.detailStack}>
      {options.map((option) => {
        const active = option.value === selected;
        return (
          <Pressable
            key={option.value}
            onPress={async () => {
              await triggerHaptic('selection');
              await onSelect(option.value);
            }}
            style={({ pressed }) => [
              styles.optionRow,
              { backgroundColor: colors.backgroundSoft, borderColor: colors.border },
              active && styles.optionRowActive,
              pressed && styles.pressed,
            ]}
          >
            <Text style={[styles.optionText, { color: colors.text }, active && styles.optionTextActive]}>{option.label}</Text>
            <Text style={[styles.optionMarker, { color: colors.textDim }, active && styles.optionTextActive]}>
              {active ? labels.selected : labels.select}
            </Text>
          </Pressable>
        );
      })}
    </View>
  );
}

function languageLabel(language: AppLanguage) {
  return language === 'nl' ? 'Nederlands' : 'English';
}

function appearanceLabel(appearance: AppAppearance, labels: PreferenceLabels) {
  if (appearance === 'light') return labels.light;
  if (appearance === 'dark') return labels.dark;
  return labels.systemDefault;
}

function userInitials(firstName?: string | null, lastName?: string | null, email?: string | null) {
  const first = firstName?.trim().charAt(0);
  const last = lastName?.trim().charAt(0);
  if (first || last) return `${first ?? ''}${last ?? ''}`.toUpperCase();
  return (email?.trim().charAt(0) || 'U').toUpperCase();
}

const styles = StyleSheet.create({
  avatarLarge: {
    alignItems: 'center',
    backgroundColor: theme.colors.accentSoft,
    borderColor: '#1D4ED880',
    borderRadius: theme.radius.pill,
    borderWidth: 1,
    height: 64,
    justifyContent: 'center',
    width: 64,
  },
  avatarLargeText: {
    color: theme.colors.text,
    fontSize: 22,
    fontWeight: '900',
  },
  backButton: {
    alignItems: 'center',
    backgroundColor: theme.colors.surface,
    borderColor: theme.colors.border,
    borderRadius: theme.radius.button,
    borderWidth: 1,
    minHeight: 40,
    paddingHorizontal: theme.spacing.md,
  },
  backText: {
    color: theme.colors.textSoft,
    fontSize: 12,
    fontWeight: '900',
    lineHeight: 38,
    textTransform: 'uppercase',
  },
  cardLabel: {
    color: theme.colors.accent,
    fontSize: theme.typography.label,
    fontWeight: '900',
    letterSpacing: 1.7,
    textTransform: 'uppercase',
  },
  disabled: {
    opacity: 0.45,
  },
  chevron: {
    color: theme.colors.textDim,
    fontSize: 28,
    fontWeight: '700',
    lineHeight: 28,
  },
  detailLabel: {
    color: theme.colors.textDim,
    fontSize: theme.typography.label,
    fontWeight: '900',
    letterSpacing: 1.1,
    textTransform: 'uppercase',
  },
  detailRow: {
    backgroundColor: theme.colors.backgroundSoft,
    borderColor: theme.colors.border,
    borderRadius: theme.radius.md,
    borderWidth: 1,
    gap: 5,
    padding: theme.spacing.md,
  },
  detailStack: {
    gap: theme.spacing.sm,
  },
  detailValue: {
    color: theme.colors.text,
    fontSize: theme.typography.body,
    fontWeight: '900',
    lineHeight: 22,
  },
  logoutButton: {
    alignItems: 'center',
    backgroundColor: theme.colors.danger,
    borderRadius: theme.radius.button,
    justifyContent: 'center',
    marginTop: theme.spacing.lg,
    minHeight: 50,
  },
  logoutText: {
    color: theme.colors.white,
    fontSize: 12,
    fontWeight: '900',
    letterSpacing: 1.2,
    textTransform: 'uppercase',
  },
  menuCopy: {
    flex: 1,
  },
  menuIcon: {
    alignItems: 'center',
    backgroundColor: theme.colors.backgroundSoft,
    borderColor: theme.colors.border,
    borderRadius: theme.radius.md,
    borderWidth: 1,
    height: 42,
    justifyContent: 'center',
    width: 42,
  },
  menuIconText: {
    color: theme.colors.accent,
    fontSize: 11,
    fontWeight: '900',
  },
  menuRow: {
    alignItems: 'center',
    borderBottomColor: theme.colors.borderSubtle,
    borderBottomWidth: 1,
    flexDirection: 'row',
    gap: theme.spacing.md,
    minHeight: 68,
    paddingVertical: theme.spacing.md,
  },
  menuSubtitle: {
    color: theme.colors.textDim,
    fontSize: theme.typography.small,
    fontWeight: '800',
    marginTop: 2,
  },
  menuTitle: {
    color: theme.colors.text,
    fontSize: theme.typography.body,
    fontWeight: '900',
  },
  pressed: {
    opacity: 0.84,
    transform: [{ scale: 0.99 }],
  },
  optionMarker: {
    color: theme.colors.textDim,
    fontSize: theme.typography.label,
    fontWeight: '900',
    textTransform: 'uppercase',
  },
  optionRow: {
    alignItems: 'center',
    backgroundColor: theme.colors.backgroundSoft,
    borderColor: theme.colors.border,
    borderRadius: theme.radius.md,
    borderWidth: 1,
    flexDirection: 'row',
    justifyContent: 'space-between',
    minHeight: 54,
    paddingHorizontal: theme.spacing.md,
  },
  optionRowActive: {
    backgroundColor: theme.colors.accentSoft,
    borderColor: theme.colors.accent,
  },
  optionText: {
    color: theme.colors.text,
    fontSize: theme.typography.body,
    fontWeight: '900',
  },
  optionTextActive: {
    color: theme.colors.accent,
  },
  profileChips: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: theme.spacing.xs,
    marginTop: theme.spacing.sm,
  },
  profileCopy: {
    flex: 1,
    gap: 2,
  },
  profileEmail: {
    color: theme.colors.textDim,
    fontSize: theme.typography.small,
    fontWeight: '700',
  },
  profileName: {
    color: theme.colors.text,
    fontSize: theme.typography.title,
    fontWeight: '900',
    lineHeight: 27,
  },
  profileRow: {
    alignItems: 'center',
    flexDirection: 'row',
    gap: theme.spacing.md,
  },
  sessionCopy: {
    color: theme.colors.textMuted,
    fontSize: theme.typography.body,
    fontWeight: '600',
    lineHeight: 22,
    marginTop: theme.spacing.md,
  },
  secondaryButton: {
    alignItems: 'center',
    backgroundColor: theme.colors.accent,
    borderRadius: theme.radius.button,
    justifyContent: 'center',
    marginTop: theme.spacing.lg,
    minHeight: 50,
  },
  pushStatus: {
    backgroundColor: theme.colors.surfaceMuted,
    borderColor: theme.colors.borderStrong,
    borderRadius: theme.radius.md,
    borderWidth: 1,
    fontSize: theme.typography.small,
    fontWeight: '800',
    lineHeight: 19,
    marginTop: theme.spacing.sm,
    padding: theme.spacing.md,
  },
  secondaryButtonText: {
    color: theme.colors.white,
    fontSize: 12,
    fontWeight: '900',
    letterSpacing: 1.2,
    textTransform: 'uppercase',
  },
  sheetCopy: {
    color: theme.colors.textMuted,
    fontSize: theme.typography.body,
    fontWeight: '600',
    lineHeight: 22,
  },
  warningButton: {
    backgroundColor: theme.colors.warning,
  },
  topBar: {
    alignItems: 'center',
    flexDirection: 'row',
    justifyContent: 'space-between',
  },
});
