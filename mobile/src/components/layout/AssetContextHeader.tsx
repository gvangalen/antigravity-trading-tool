import { Pressable, StyleSheet, Text, View } from 'react-native';

import { preferenceColors, useAppPreferences } from '../../preferences/AppPreferencesProvider';
import { theme } from '../../constants/theme';
import { triggerHaptic } from '../../utils/haptics';
import { DataFreshnessIndicator } from './DataFreshnessIndicator';

type AssetContextHeaderProps = {
  asset: string;
  context: string;
  updatedAt: string;
};

export function AssetContextHeader({ asset, context, updatedAt }: AssetContextHeaderProps) {
  const { appearance } = useAppPreferences();
  const colors = preferenceColors(appearance);

  return (
    <View
      style={[
        styles.container,
        {
          backgroundColor: colors.surface,
          borderColor: colors.border,
          shadowColor: appearance === 'light' ? '#0F172A' : '#000000',
          shadowOpacity: appearance === 'light' ? 0.04 : 0,
          shadowRadius: appearance === 'light' ? 16 : 0,
          shadowOffset: { width: 0, height: 8 },
          elevation: appearance === 'light' ? 1 : 0,
        },
      ]}
    >
      <View style={styles.contextBlock}>
        <Text style={styles.label}>Live context</Text>
        <Text style={[styles.contextText, { color: colors.textDim }]} numberOfLines={1}>
          {context}
        </Text>
      </View>
      <View style={styles.metaRow}>
        <Pressable
          onPress={() => triggerHaptic('selection')}
          style={({ pressed }) => [
            styles.assetButton,
            { backgroundColor: colors.backgroundSoft, borderColor: colors.border },
            pressed && styles.pressed,
          ]}
        >
          <Text style={[styles.asset, { color: colors.text }]}>{asset}</Text>
        </Pressable>
        <View style={styles.freshness}>
          <DataFreshnessIndicator updatedAt={updatedAt} />
        </View>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  asset: {
    color: theme.colors.text,
    fontSize: 12,
    fontWeight: '700',
  },
  assetButton: {
    backgroundColor: theme.colors.backgroundSoft,
    borderColor: theme.colors.border,
    borderRadius: theme.radius.pill,
    borderWidth: 0.5,
    paddingHorizontal: 12,
    paddingVertical: 4,
  },
  container: {
    alignItems: 'center',
    borderRadius: 24,
    borderWidth: 1,
    flexDirection: 'row',
    gap: theme.spacing.md,
    justifyContent: 'space-between',
    marginBottom: theme.spacing.md,
    paddingHorizontal: 18,
    paddingVertical: 14,
  },
  contextBlock: {
    flex: 1,
    gap: 2,
    minWidth: 120,
  },
  contextText: {
    fontSize: 12,
    fontWeight: '700',
  },
  freshness: {
    flexShrink: 1,
  },
  label: {
    color: theme.colors.textDim,
    fontSize: 10,
    fontWeight: '900',
    letterSpacing: 1.2,
    textTransform: 'uppercase',
  },
  metaRow: {
    alignItems: 'center',
    flexDirection: 'row',
    gap: theme.spacing.sm,
  },
  pressed: {
    opacity: 0.82,
    transform: [{ scale: 0.98 }],
  },
});
