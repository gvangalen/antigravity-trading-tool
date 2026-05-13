import { Pressable, StyleSheet, Text, View } from 'react-native';

import { theme } from '../../constants/theme';
import { triggerHaptic } from '../../utils/haptics';
import { DataFreshnessIndicator } from './DataFreshnessIndicator';

type AssetContextHeaderProps = {
  asset: string;
  context: string;
  updatedAt: string;
};

export function AssetContextHeader({ asset, context, updatedAt }: AssetContextHeaderProps) {
  return (
    <View style={styles.container}>
      <View>
        <Text style={styles.label}>Active context</Text>
        <Text style={styles.title}>{context}</Text>
      </View>
      <Pressable
        onPress={() => triggerHaptic('selection')}
        style={({ pressed }) => [styles.assetButton, pressed && styles.pressed]}
      >
        <Text style={styles.asset}>{asset}</Text>
      </Pressable>
      <View style={styles.freshness}>
        <DataFreshnessIndicator updatedAt={updatedAt} />
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
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
});
