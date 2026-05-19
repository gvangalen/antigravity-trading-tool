import { Pressable, StyleSheet, Text, View } from 'react-native';

import { preferenceColors, useAppPreferences } from '../../preferences/AppPreferencesProvider';
import { theme } from '../../constants/theme';
import { triggerHaptic } from '../../utils/haptics';
import { StatusChip } from '../layout/StatusChip';

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
    <View style={{ paddingVertical: theme.spacing.md, paddingHorizontal: theme.spacing.lg }}>
      <StatusChip label={severity} tone="warning" />
      <Text style={[styles.title, { color: colors.text }]}>{title}</Text>
      <Text style={[styles.body, { color: colors.textMuted }]}>{body}</Text>
      
      <View style={{ marginTop: theme.spacing.md, gap: 4 }}>
        <Text style={{ fontSize: 11, color: colors.warning, fontWeight: '700', letterSpacing: 0.5 }}>SAFE NEXT STEP</Text>
        <Text style={{ fontSize: 13, color: colors.textSoft, fontWeight: '600' }}>{nextStep}</Text>
      </View>
    </View>
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
    justifyContent: 'center',
    paddingVertical: 8,
    paddingHorizontal: 16,
    borderRadius: theme.radius.pill,
    borderWidth: 0.5,
    borderColor: theme.colors.border,
    backgroundColor: 'transparent',
    marginTop: theme.spacing.lg,
  },
  buttonText: {
    color: theme.colors.textSoft,
    fontSize: 12,
    fontWeight: '700',
    letterSpacing: 0.5,
    textTransform: 'uppercase',
  },
  pressed: {
    opacity: 0.86,
  },
  title: {
    color: theme.colors.text,
    fontSize: 20,
    fontWeight: '700',
    lineHeight: 24,
    marginTop: theme.spacing.md,
  },
});
