import { Pressable, StyleSheet, Text, View } from 'react-native';

import { preferenceColors, useAppPreferences } from '../../preferences/AppPreferencesProvider';
import { StatusTone, statusTones, theme } from '../../constants/theme';
import { triggerHaptic } from '../../utils/haptics';
import { CardShell } from './CardShell';

type InsightCardProps = {
  label: string;
  title: string;
  body: string;
  tone?: StatusTone;
  cta?: string;
  onPress?: () => void;
};

export function InsightCard({ label, title, body, tone = 'neutral', cta, onPress }: InsightCardProps) {
  const { appearance } = useAppPreferences();
  const colors = preferenceColors(appearance);
  const palette = statusTones[tone];

  return (
    <Pressable
      onPress={async () => {
        await triggerHaptic('selection');
        onPress?.();
      }}
      style={({ pressed }) => pressed && styles.pressed}
    >
      <View style={{ borderBottomWidth: 0.5, borderColor: colors.border, padding: theme.spacing.md }}>
        <View style={styles.header}>
          <Text style={[styles.label, { color: palette.color }]}>{label}</Text>
          <View style={[styles.badge, { backgroundColor: palette.background, borderColor: palette.border }]} />
        </View>
        <Text style={[styles.title, { color: colors.text }]}>{title}</Text>
        <Text style={[styles.body, { color: colors.textMuted }]}>{body}</Text>
        {cta ? <Text style={[styles.cta, { color: palette.color }]}>{cta}</Text> : null}
      </View>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  badge: {
    borderRadius: theme.radius.pill,
    borderWidth: 1,
    height: 18,
    width: 18,
  },
  body: {
    color: theme.colors.textMuted,
    fontSize: theme.typography.body,
    fontWeight: '600',
    lineHeight: 22,
    marginTop: theme.spacing.sm,
  },
  cta: {
    fontSize: 12,
    fontWeight: '900',
    letterSpacing: 1.3,
    marginTop: theme.spacing.md,
    textTransform: 'uppercase',
  },
  header: {
    alignItems: 'center',
    flexDirection: 'row',
    justifyContent: 'space-between',
  },
  label: {
    fontSize: theme.typography.label,
    fontWeight: '900',
    letterSpacing: 1.8,
    textTransform: 'uppercase',
  },
  pressed: {
    opacity: 0.86,
  },
  title: {
    color: theme.colors.text,
    fontSize: theme.typography.cardTitle,
    fontWeight: '900',
    lineHeight: 23,
    marginTop: theme.spacing.sm,
  },
});
