import { useNavigation } from '@react-navigation/native';
import type { NavigationProp } from '@react-navigation/native';
import { Pressable, StyleSheet, Text, View } from 'react-native';

import { useAuth } from '../../auth/AuthProvider';
import { preferenceColors, useAppPreferences } from '../../preferences/AppPreferencesProvider';
import { theme } from '../../constants/theme';
import type { MainTabParamList } from '../../navigation/MainTabNavigator';
import { triggerHaptic } from '../../utils/haptics';
import { DataFreshnessIndicator } from './DataFreshnessIndicator';

type AssetContextHeaderProps = {
  asset: string;
  context: string;
  updatedAt: string;
};

export function AssetContextHeader({ asset, context, updatedAt }: AssetContextHeaderProps) {
  const navigation = useNavigation<NavigationProp<MainTabParamList>>();
  const { user } = useAuth();
  const { appearance } = useAppPreferences();
  const colors = preferenceColors(appearance);
  const initials = userInitials(user?.first_name, user?.last_name, user?.email);

  return (
    <View style={[styles.container, { backgroundColor: colors.surface, borderColor: colors.border }]}>
      <View style={styles.titleBlock}>
        <Text style={styles.label}>Active context</Text>
        <Text style={[styles.title, { color: colors.text }]}>{context}</Text>
      </View>
      <View style={styles.actions}>
        <Pressable
          onPress={() => triggerHaptic('selection')}
          style={({ pressed }) => [styles.assetButton, pressed && styles.pressed]}
        >
          <Text style={[styles.asset, { color: colors.text }]}>{asset}</Text>
        </Pressable>
        <Pressable
          accessibilityLabel="Open profile settings"
          onPress={async () => {
            await triggerHaptic('selection');
            navigation.navigate('Settings');
          }}
          style={({ pressed }) => [
            styles.avatarButton,
            { backgroundColor: colors.surfaceMuted, borderColor: colors.borderStrong },
            pressed && styles.pressed,
          ]}
        >
          <Text style={styles.avatarText}>{initials}</Text>
        </Pressable>
      </View>
      <View style={styles.freshness}>
        <DataFreshnessIndicator updatedAt={updatedAt} />
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
  asset: {
    color: theme.colors.text,
    fontSize: 15,
    fontWeight: '900',
  },
  assetButton: {
    backgroundColor: theme.colors.accentSoft,
    borderColor: '#1D4ED880',
    borderRadius: theme.radius.pill,
    borderWidth: 1,
    paddingHorizontal: theme.spacing.md,
    paddingVertical: theme.spacing.sm,
  },
  avatarButton: {
    alignItems: 'center',
    backgroundColor: theme.colors.surfaceMuted,
    borderColor: theme.colors.borderStrong,
    borderRadius: theme.radius.pill,
    borderWidth: 1,
    height: 40,
    justifyContent: 'center',
    width: 40,
  },
  avatarText: {
    color: theme.colors.textSoft,
    fontSize: 13,
    fontWeight: '900',
  },
  container: {
    alignItems: 'flex-start',
    backgroundColor: theme.colors.surface,
    borderColor: theme.colors.border,
    borderRadius: theme.radius.card,
    borderWidth: 1,
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: theme.spacing.md,
    justifyContent: 'space-between',
    padding: theme.spacing.md,
  },
  freshness: {
    flexBasis: '100%',
  },
  label: {
    color: theme.colors.textDim,
    fontSize: theme.typography.label,
    fontWeight: '900',
    letterSpacing: 1.6,
    textTransform: 'uppercase',
  },
  pressed: {
    opacity: 0.82,
    transform: [{ scale: 0.98 }],
  },
  title: {
    color: theme.colors.text,
    fontSize: theme.typography.cardTitle,
    fontWeight: '900',
    marginTop: 3,
  },
  titleBlock: {
    flex: 1,
    minWidth: 150,
  },
});
