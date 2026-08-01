import { Pressable, StyleSheet, Text, View } from 'react-native';

import { useAuth } from '../../auth/AuthProvider';
import { StatusTone, theme } from '../../constants/theme';
import {
  preferenceColors,
  useAppPreferences,
} from '../../preferences/AppPreferencesProvider';
import { AppLanguage } from '../../preferences/appLocale';
import { translate } from '../../i18n';
import { triggerHaptic } from '../../utils/haptics';
import { StatusChip } from '../layout/StatusChip';

export type TodayWithFinnTag = {
  label: string;
  tone: StatusTone;
};

export type TodayWithFinnQueueItem = {
  key: string;
  label: string;
  value: number | string;
  body: string;
};

type FinnCardLabels = {
  eyebrow: string;
  queueTitle: string;
  queueSubtitle: string;
};

type TodayWithFinnCardProps = {
  greeting?: string;
  headline: string;
  support: string;
  tags: TodayWithFinnTag[];
  primaryActionLabel: string;
  onPrimaryAction: () => void;
  queueItems?: TodayWithFinnQueueItem[];
  queueStatusLabel?: string;
  queueTitle?: string;
  queueSubtitle?: string;
};

export function TodayWithFinnCard({
  greeting,
  headline,
  support,
  tags,
  primaryActionLabel,
  onPrimaryAction,
  queueItems = [],
  queueStatusLabel,
  queueTitle,
  queueSubtitle,
}: TodayWithFinnCardProps) {
  const { appearance, language } = useAppPreferences();
  const { user } = useAuth();
  const colors = preferenceColors(appearance);
  const labels = finnCardLabels(language);
  const fallbackGreeting = user?.first_name
    ? translate(language, 'finn.greetingEveningName', { name: user.first_name })
    : translate(language, 'finn.greetingEveningTrader');
  const resolvedGreeting = greeting?.trim() || fallbackGreeting;

  return (
    <View
      style={[
        styles.panel,
        {
          backgroundColor: colors.surfaceMuted,
          borderColor: colors.borderSubtle,
        },
      ]}
    >
      <View style={styles.todayHeader}>
        <View style={[styles.todayDot, { backgroundColor: colors.accent }]} />
        <Text style={[styles.eyebrowAccent, { color: colors.accent }]}>{labels.eyebrow}</Text>
      </View>

      <Text style={[styles.greeting, { color: colors.textMuted }]}>{resolvedGreeting}</Text>
      <Text style={[styles.headline, { color: colors.text }]}>{headline}</Text>
      <Text style={[styles.support, { color: colors.textMuted }]}>{support}</Text>

      <View style={styles.badgeRail}>
        {tags.map((tag) => (
          <View
            key={tag.label}
            style={[styles.badgeCell, tags.length >= 4 && styles.badgeCellHalf]}
          >
            <FilledStatusBadge label={tag.label} tone={tag.tone} />
          </View>
        ))}
      </View>

      <Pressable
        onPress={async () => {
          await triggerHaptic('impact');
          onPrimaryAction();
        }}
        style={({ pressed }) => [styles.primaryActionButton, pressed && styles.pressed]}
      >
        <Text style={styles.primaryActionButtonText}>{primaryActionLabel}</Text>
      </Pressable>

      {queueItems.length > 0 ? (
        <>
          <View style={[styles.divider, { backgroundColor: colors.borderSubtle }]} />

          <View style={styles.subsectionHeader}>
            <View>
              <Text style={[styles.eyebrow, { color: colors.textDim }]}>{queueTitle || labels.queueTitle}</Text>
              <Text style={[styles.microcopy, { color: colors.textMuted }]}>
                {queueSubtitle || labels.queueSubtitle}
              </Text>
            </View>
            {queueStatusLabel ? <StatusChip label={queueStatusLabel} tone="neutral" /> : null}
          </View>

          <View style={styles.queueGrid}>
            {queueItems.map((item) => (
              <View
                key={item.key}
                style={[
                  styles.queueCard,
                  { backgroundColor: colors.surface, borderColor: colors.borderSubtle },
                ]}
              >
                <Text style={[styles.queueValue, { color: colors.text }]}>{item.value}</Text>
                <Text style={[styles.queueLabel, { color: colors.text }]}>{item.label}</Text>
                <Text style={[styles.queueBody, { color: colors.textMuted }]}>{item.body}</Text>
              </View>
            ))}
          </View>
        </>
      ) : null}
    </View>
  );
}

function finnCardLabels(language: AppLanguage): FinnCardLabels {
  return {
    eyebrow: translate(language, 'finn.todayEyebrow'),
    queueTitle: translate(language, 'finn.queueTitle'),
    queueSubtitle: translate(language, 'finn.queueSubtitle'),
  };
}

function FilledStatusBadge({ label, tone }: { label: string; tone: StatusTone }) {
  const { appearance } = useAppPreferences();
  const colors = preferenceColors(appearance);
  const palettes: Record<StatusTone, { background: string; border: string; color: string }> = {
    accent: { background: '#E8F0FF', border: '#C7D7FE', color: colors.accent },
    success: { background: '#EAF9F3', border: '#C8EFD9', color: colors.success },
    warning: { background: '#FEF5E7', border: '#F9D9A7', color: colors.warning },
    danger: { background: '#FDECEF', border: '#F8C7D1', color: colors.danger },
    neutral: { background: colors.surface, border: colors.borderSubtle, color: colors.textDim },
  };
  const palette = palettes[tone];

  return (
    <View style={[styles.filledBadge, { backgroundColor: palette.background, borderColor: palette.border }]}>
      <View style={[styles.filledBadgeDot, { backgroundColor: palette.color }]} />
      <Text
        adjustsFontSizeToFit
        minimumFontScale={0.8}
        numberOfLines={1}
        style={[styles.filledBadgeText, { color: palette.color }]}
      >
        {label}
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  badgeRail: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    columnGap: 10,
    marginTop: theme.spacing.sm,
    rowGap: 10,
    width: '100%',
  },
  badgeCell: {
    flexBasis: '100%',
    maxWidth: '100%',
  },
  badgeCellHalf: {
    flexBasis: '48.2%',
    maxWidth: '48.2%',
  },
  divider: {
    height: 1,
    marginTop: theme.spacing.md,
  },
  eyebrow: {
    fontSize: theme.typography.label,
    fontWeight: '900',
    letterSpacing: 3.2,
    textTransform: 'uppercase',
  },
  eyebrowAccent: {
    fontSize: theme.typography.label,
    fontWeight: '900',
    letterSpacing: 3.2,
    textTransform: 'uppercase',
  },
  filledBadge: {
    alignItems: 'center',
    borderRadius: theme.radius.pill,
    borderWidth: 1,
    flexDirection: 'row',
    justifyContent: 'center',
    paddingHorizontal: 12,
    paddingVertical: 9,
    width: '100%',
  },
  filledBadgeDot: {
    borderRadius: theme.radius.pill,
    height: 10,
    marginRight: 10,
    width: 10,
  },
  filledBadgeText: {
    flexShrink: 1,
    fontSize: 10.5,
    fontWeight: '900',
    letterSpacing: 1.1,
    textTransform: 'uppercase',
  },
  greeting: {
    fontSize: 16,
    fontWeight: '700',
    lineHeight: 22,
    marginTop: theme.spacing.sm,
  },
  headline: {
    fontSize: 24,
    fontWeight: '900',
    letterSpacing: -0.8,
    lineHeight: 34,
    marginTop: theme.spacing.sm,
  },
  microcopy: {
    fontSize: 13,
    fontWeight: '700',
    letterSpacing: 0.2,
    lineHeight: 18,
    marginTop: 4,
  },
  panel: {
    alignSelf: 'stretch',
    borderRadius: theme.radius.xl,
    borderWidth: 1,
    maxWidth: '100%',
    minWidth: '100%',
    paddingHorizontal: 16,
    paddingTop: 16,
    paddingBottom: 18,
    width: '100%',
  },
  pressed: {
    opacity: 0.88,
    transform: [{ scale: 0.99 }],
  },
  primaryActionButton: {
    alignItems: 'center',
    backgroundColor: theme.colors.accent,
    borderRadius: 18,
    justifyContent: 'center',
    marginTop: theme.spacing.md,
    minHeight: 56,
    paddingHorizontal: 16,
  },
  primaryActionButtonText: {
    color: '#ffffff',
    fontSize: 13,
    fontWeight: '900',
    letterSpacing: 1.8,
    textTransform: 'uppercase',
  },
  queueBody: {
    fontSize: 12,
    fontWeight: '600',
    lineHeight: 18,
    marginTop: 8,
  },
  queueCard: {
    borderRadius: 24,
    borderWidth: 1,
    flexBasis: '48.2%',
    maxWidth: '48.2%',
    minHeight: 112,
    paddingHorizontal: 16,
    paddingVertical: 14,
  },
  queueGrid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    columnGap: 10,
    marginTop: theme.spacing.sm,
    rowGap: 10,
    width: '100%',
  },
  queueLabel: {
    fontSize: 14,
    fontWeight: '800',
    lineHeight: 20,
  },
  queueValue: {
    fontSize: 34,
    fontWeight: '900',
    letterSpacing: -1.2,
    lineHeight: 36,
  },
  subsectionHeader: {
    alignItems: 'flex-start',
    flexDirection: 'row',
    justifyContent: 'space-between',
    marginTop: theme.spacing.md,
  },
  support: {
    fontSize: 16,
    fontWeight: '700',
    lineHeight: 22,
    marginTop: theme.spacing.sm,
  },
  todayDot: {
    borderRadius: theme.radius.pill,
    height: 12,
    width: 12,
  },
  todayHeader: {
    alignItems: 'center',
    flexDirection: 'row',
    gap: 12,
  },
});
