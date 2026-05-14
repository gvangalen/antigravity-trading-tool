import { Pressable, StyleSheet, Text, View } from 'react-native';

import { preferenceColors, useAppPreferences } from '../../preferences/AppPreferencesProvider';
import { theme } from '../../constants/theme';
import { triggerHaptic } from '../../utils/haptics';
import { StatusChip } from '../layout/StatusChip';
import { CardShell } from './CardShell';

type RiskWarningCardProps = {
  severity: string;
  title: string;
  body: string;
  nextStep: string;
  onExplain?: () => void;
};

export function RiskWarningCard({ severity, title, body, nextStep, onExplain }: RiskWarningCardProps) {
  const { appearance } = useAppPreferences();
  const colors = preferenceColors(appearance);

  return (
    <CardShell>
      <StatusChip label={severity} tone="warning" />
      <Text style={[styles.title, { color: colors.text }]}>{title}</Text>
      <Text style={[styles.body, { color: colors.textMuted }]}>{body}</Text>
      <View style={[styles.nextBox, { backgroundColor: appearance === 'light' ? '#FEF3C7' : theme.colors.warningSoft }]}>
        <Text style={styles.nextLabel}>Safe next step</Text>
        <Text style={[styles.nextText, { color: colors.textSoft }]}>{nextStep}</Text>
      </View>
      <Pressable
        onPress={async () => {
          await triggerHaptic('warning');
          onExplain?.();
        }}
        style={({ pressed }) => [styles.button, { backgroundColor: colors.surfaceMuted, borderColor: colors.borderStrong }, pressed && styles.pressed]}
      >
        <Text style={[styles.buttonText, { color: colors.textSoft }]}>Ask assistant why</Text>
      </Pressable>
    </CardShell>
  );
}

const styles = StyleSheet.create({
  body: {
    color: theme.colors.textMuted,
    fontSize: theme.typography.body,
    fontWeight: '600',
    lineHeight: 22,
    marginTop: theme.spacing.sm,
  },
  button: {
    alignItems: 'center',
    backgroundColor: theme.colors.surfaceMuted,
    borderColor: theme.colors.borderStrong,
    borderRadius: theme.radius.button,
    borderWidth: 1,
    marginTop: theme.spacing.lg,
    minHeight: 48,
    justifyContent: 'center',
  },
  buttonText: {
    color: theme.colors.textSoft,
    fontSize: 12,
    fontWeight: '900',
    letterSpacing: 1.2,
    textTransform: 'uppercase',
  },
  nextBox: {
    backgroundColor: theme.colors.warningSoft,
    borderColor: '#F59E0B55',
    borderRadius: theme.radius.md,
    borderWidth: 1,
    marginTop: theme.spacing.md,
    padding: theme.spacing.md,
  },
  nextLabel: {
    color: theme.colors.warning,
    fontSize: theme.typography.label,
    fontWeight: '900',
    letterSpacing: 1.4,
    textTransform: 'uppercase',
  },
  nextText: {
    color: theme.colors.textSoft,
    fontSize: theme.typography.small,
    fontWeight: '800',
    lineHeight: 20,
    marginTop: 4,
  },
  pressed: {
    opacity: 0.86,
  },
  title: {
    color: theme.colors.text,
    fontSize: theme.typography.title,
    fontWeight: '900',
    lineHeight: 27,
    marginTop: theme.spacing.md,
  },
});
