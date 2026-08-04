import { Feather } from '@expo/vector-icons';
import { ScrollView, StyleSheet, Text, View } from 'react-native';

import { StatusTone, theme } from '../../constants/theme';
import { preferenceColors, useAppPreferences } from '../../preferences/AppPreferencesProvider';
import { StatusChip } from '../layout/StatusChip';

type IntroStep = {
  icon: keyof typeof Feather.glyphMap;
  key: string;
  title: string;
};

type CompactWorkspaceIntroProps = {
  eyebrow: string;
  title: string;
  subtitle: string;
  statusLabel?: string;
  statusTone?: StatusTone;
  steps: ReadonlyArray<IntroStep>;
  children?: React.ReactNode;
};

export function CompactWorkspaceIntro({
  eyebrow,
  title,
  subtitle,
  statusLabel,
  statusTone = 'success',
  steps,
  children,
}: CompactWorkspaceIntroProps) {
  const { appearance } = useAppPreferences();
  const colors = preferenceColors(appearance);

  return (
    <View style={[styles.panel, { backgroundColor: colors.surface, borderColor: colors.borderSubtle }]}>
      <View style={styles.header}>
        <View style={styles.copy}>
          <Text style={[styles.eyebrow, { color: colors.textDim }]}>{eyebrow}</Text>
          <Text style={[styles.title, { color: colors.text }]}>{title}</Text>
          <Text style={[styles.subtitle, { color: colors.textMuted }]}>{subtitle}</Text>
        </View>
        {statusLabel ? <StatusChip compact label={statusLabel} tone={statusTone} /> : null}
      </View>

      <ScrollView
        horizontal
        showsHorizontalScrollIndicator={false}
        style={styles.rail}
        contentContainerStyle={styles.railContent}
      >
        {steps.map((step, index) => (
          <View
            key={step.key}
            style={[
              styles.stepCard,
              {
                backgroundColor: colors.surfaceMuted,
                borderColor: colors.borderSubtle,
                marginRight: index === steps.length - 1 ? 0 : 6,
              },
            ]}
          >
            <View style={[styles.iconWrap, { backgroundColor: colors.surface }]}>
              <Feather color={colors.accent} name={step.icon} size={14} />
            </View>
            <Text numberOfLines={1} style={[styles.stepTitle, { color: colors.accent }]}>
              {step.title}
            </Text>
          </View>
        ))}
      </ScrollView>

      {children}
    </View>
  );
}

const styles = StyleSheet.create({
  copy: {
    flex: 1,
  },
  eyebrow: {
    fontSize: 11,
    fontWeight: '900',
    letterSpacing: 2.2,
    textTransform: 'uppercase',
  },
  header: {
    alignItems: 'flex-start',
    flexDirection: 'row',
    gap: theme.spacing.sm,
    justifyContent: 'space-between',
  },
  iconWrap: {
    alignItems: 'center',
    borderRadius: 10,
    height: 28,
    justifyContent: 'center',
    width: 28,
  },
  panel: {
    borderRadius: 20,
    borderWidth: 1,
    marginHorizontal: theme.spacing.lg,
    marginTop: theme.spacing.md,
    padding: theme.spacing.md,
  },
  rail: {
    marginTop: theme.spacing.sm,
  },
  railContent: {
    paddingRight: theme.spacing.md,
  },
  stepCard: {
    alignItems: 'center',
    borderRadius: 14,
    borderWidth: 1,
    flexDirection: 'row',
    gap: 8,
    minHeight: 44,
    paddingHorizontal: 9,
    paddingVertical: 8,
    width: 132,
  },
  stepTitle: {
    flex: 1,
    fontSize: 11,
    fontWeight: '900',
    lineHeight: 13,
  },
  subtitle: {
    fontSize: 13,
    fontWeight: '600',
    lineHeight: 18,
    marginTop: theme.spacing.xs,
  },
  title: {
    fontSize: 16,
    fontWeight: '900',
    letterSpacing: -0.3,
    lineHeight: 20,
    marginTop: 4,
  },
});
