import { useState } from 'react';
import { Feather } from '@expo/vector-icons';
import { Pressable, StyleSheet, Text, View } from 'react-native';

import { theme } from '../../constants/theme';
import { typography } from '../../constants/typography';
import { preferenceColors, useAppPreferences } from '../../preferences/AppPreferencesProvider';
import { AppLanguage } from '../../preferences/appLocale';
import { translate } from '../../i18n';
import { triggerHaptic } from '../../utils/haptics';

export type TodayWithFinnQueueItem = {
  key: string;
  label: string;
  value: number | string;
  body: string;
  detail?: string;
};

type FinnCardLabels = {
  eyebrow: string;
  queueTitle: string;
};

type TodayWithFinnCardProps = {
  headline: string;
  support: string;
  metaItems?: string[];
  queueItems?: TodayWithFinnQueueItem[];
  queueStatusLabel?: string;
  queueTitle?: string;
  defaultQueueExpanded?: boolean;
};

export function TodayWithFinnCard({
  headline,
  support,
  metaItems = [],
  queueItems = [],
  queueStatusLabel,
  queueTitle,
  defaultQueueExpanded = false,
}: TodayWithFinnCardProps) {
  const { appearance, language } = useAppPreferences();
  const colors = preferenceColors(appearance);
  const labels = finnCardLabels(language);
  const [queueExpanded, setQueueExpanded] = useState(defaultQueueExpanded);
  const resolvedMeta = metaItems.filter((item) => item.trim().length > 0).slice(0, 3);
  const primaryQueueItem = queueItems[0];
  const secondaryQueueItems = queueItems.slice(1);
  const resolvedQueueStatusLabel =
    queueStatusLabel ||
    translate(language, 'common.itemsOpen', {
      count: queueItems.reduce((total, item) => {
        const value = typeof item.value === 'number' ? item.value : Number(item.value);
        return total + (Number.isFinite(value) && value > 0 ? 1 : 0);
      }, 0),
    });

  return (
    <View style={[styles.panel, { backgroundColor: colors.surface }]}>
      <View style={styles.todayHeader}>
        <View style={[styles.todayDot, { backgroundColor: colors.accent }]} />
        <Text style={[styles.eyebrow, { color: colors.text }]}>{labels.eyebrow}</Text>
      </View>

      <Text numberOfLines={3} style={[styles.headline, { color: colors.text }]}>{headline}</Text>
      <Text numberOfLines={3} style={[styles.support, { color: colors.textMuted }]}>{support}</Text>

      {resolvedMeta.length > 0 ? (
        <Text numberOfLines={2} style={[styles.metaLine, { color: colors.textDim }]}>
          {resolvedMeta.join('  •  ')}
        </Text>
      ) : null}

      {queueItems.length > 0 ? (
        <>
          <Pressable
            onPress={async () => {
              await triggerHaptic('selection');
              setQueueExpanded((current) => !current);
            }}
            style={({ pressed }) => [styles.queueToggle, pressed && styles.pressed]}
          >
            <Text style={[styles.queueTitle, { color: colors.text }]}>
              {queueTitle || labels.queueTitle}
            </Text>
            <View style={styles.queueToggleRight}>
              <Text style={[styles.queueCount, { color: colors.textDim }]}>
                {resolvedQueueStatusLabel}
              </Text>
              <Text style={[styles.queueChevron, { color: colors.textDim }]}>
                {queueExpanded ? '⌃' : '›'}
              </Text>
            </View>
          </Pressable>

          {queueExpanded && primaryQueueItem ? (
            <View style={[styles.queueFocusCard, { borderColor: colors.borderSubtle, backgroundColor: colors.surfaceMuted }]}>
              <View style={styles.queueFocusTop}>
                <Text style={[styles.queueFocusLabel, { color: colors.textDim }]}>
                  {primaryQueueItem.label}
                </Text>
                <View style={[styles.queueFocusValuePill, { backgroundColor: colors.surface }]}>
                  <Text style={[styles.queueFocusValue, { color: colors.text }]}>
                    {primaryQueueItem.value}
                  </Text>
                </View>
              </View>
              <View style={styles.queueFocusBodyRow}>
                <View style={[styles.queueFocusIconWrap, { backgroundColor: colors.surface }]}>
                  <Feather color={colors.accent} name={queueIconForKey(primaryQueueItem.key)} size={13} />
                </View>
                <View style={styles.queueFocusCopy}>
                  <Text numberOfLines={1} style={[styles.queueFocusTitle, { color: colors.text }]}>
                    {primaryQueueItem.body}
                  </Text>
                  {primaryQueueItem.detail ? (
                    <Text numberOfLines={1} style={[styles.queueFocusDetail, { color: colors.textMuted }]}>
                      {primaryQueueItem.detail}
                    </Text>
                  ) : null}
                </View>
                <Feather color={colors.textDim} name="chevron-right" size={16} />
              </View>
            </View>
          ) : null}

          {queueExpanded && secondaryQueueItems.length > 0 ? (
            <View style={[styles.queueList, { borderTopColor: colors.borderSubtle }]}>
              {secondaryQueueItems.map((item, index) => (
                <View
                  key={item.key}
                  style={[
                    styles.queueRow,
                    index < secondaryQueueItems.length - 1 && { borderBottomColor: colors.borderSubtle, borderBottomWidth: 1 },
                  ]}
                >
                  <View style={styles.queueRowLead}>
                    <View style={[styles.queueRowIconWrap, { backgroundColor: colors.surfaceMuted }]}>
                      <Feather color={colors.textDim} name={queueIconForKey(item.key)} size={12} />
                    </View>
                    <View style={styles.queueCopy}>
                      <Text style={[styles.queueLabel, { color: colors.text }]}>{item.label}</Text>
                      <Text numberOfLines={1} style={[styles.queueBody, { color: colors.textMuted }]}>
                        {item.body}
                      </Text>
                    </View>
                  </View>
                  <Text style={[styles.queueValue, { color: colors.text }]}>{item.value}</Text>
                </View>
              ))}
            </View>
          ) : null}
        </>
      ) : null}
    </View>
  );
}

function finnCardLabels(language: AppLanguage): FinnCardLabels {
  return {
    eyebrow: translate(language, 'finn.todayEyebrow'),
    queueTitle: translate(language, 'finn.queueTitle'),
  };
}

function queueIconForKey(key: string): keyof typeof Feather.glyphMap {
  if (key === 'reviews') return 'check-circle';
  if (key === 'risks') return 'alert-circle';
  if (key === 'performance') return 'bar-chart-2';
  if (key === 'tasks') return 'list';
  if (key === 'bots') return 'cpu';
  if (key === 'live') return 'radio';
  if (key === 'paused') return 'pause-circle';
  if (key === 'highlights') return 'bookmark';
  if (key === 'sections') return 'file-text';
  if (key === 'reading') return 'clock';
  return 'circle';
}

const styles = StyleSheet.create({
  eyebrow: {
    ...typography.eyebrow,
  },
  headline: {
    ...typography.sectionTitle,
    fontSize: 14,
    lineHeight: 18,
    marginTop: 8,
  },
  metaLine: {
    ...typography.meta,
    marginTop: 8,
  },
  panel: {
    paddingHorizontal: theme.spacing.md,
    paddingTop: theme.spacing.md,
    paddingBottom: 4,
    width: '100%',
  },
  pressed: {
    opacity: 0.72,
  },
  queueBody: {
    ...typography.meta,
    marginTop: 2,
  },
  queueChevron: {
    fontSize: 15,
    lineHeight: 18,
  },
  queueCopy: {
    flex: 1,
    paddingRight: theme.spacing.sm,
  },
  queueRowIconWrap: {
    alignItems: 'center',
    borderRadius: 999,
    height: 22,
    justifyContent: 'center',
    width: 22,
  },
  queueRowLead: {
    alignItems: 'center',
    flex: 1,
    flexDirection: 'row',
    gap: 8,
    minWidth: 0,
  },
  queueCount: {
    ...typography.meta,
  },
  queueLabel: {
    ...typography.cardTitle,
  },
  queueFocusCard: {
    borderRadius: 14,
    borderWidth: 1,
    marginTop: 6,
    paddingHorizontal: 10,
    paddingTop: 7,
    paddingBottom: 7,
  },
  queueFocusCopy: {
    flex: 1,
    minWidth: 0,
  },
  queueFocusBodyRow: {
    alignItems: 'center',
    flexDirection: 'row',
    gap: 7,
    marginTop: 4,
  },
  queueFocusIconWrap: {
    alignItems: 'center',
    borderRadius: 999,
    height: 18,
    justifyContent: 'center',
    width: 18,
  },
  queueFocusTop: {
    alignItems: 'center',
    flexDirection: 'row',
    justifyContent: 'space-between',
  },
  queueFocusLabel: {
    ...typography.chipLabelCompact,
  },
  queueFocusTitle: {
    ...typography.bodyStrong,
    fontSize: 13,
    lineHeight: 16,
  },
  queueFocusDetail: {
    ...typography.meta,
    marginTop: 1,
  },
  queueFocusValue: {
    fontSize: 11,
    fontWeight: '600',
    lineHeight: 13,
  },
  queueFocusValuePill: {
    alignItems: 'center',
    borderRadius: theme.radius.pill,
    justifyContent: 'center',
    minWidth: 20,
    paddingHorizontal: 5,
    paddingVertical: 1,
  },
  queueList: {
    borderTopWidth: 1,
    marginTop: 6,
    paddingTop: 2,
  },
  queuePreviewValue: {
    fontSize: 14,
    fontWeight: '600',
    lineHeight: 17,
  },
  queueRow: {
    alignItems: 'center',
    flexDirection: 'row',
    justifyContent: 'space-between',
    paddingVertical: 6,
  },
  queueTitle: {
    ...typography.cardTitle,
    fontSize: 14,
  },
  queueToggle: {
    alignItems: 'center',
    flexDirection: 'row',
    justifyContent: 'space-between',
    marginTop: 6,
  },
  queueToggleRight: {
    alignItems: 'center',
    flexDirection: 'row',
    gap: 10,
  },
  queueValue: {
    ...typography.bodyStrong,
    marginLeft: 10,
  },
  support: {
    ...typography.body,
    marginTop: 8,
  },
  todayDot: {
    borderRadius: theme.radius.pill,
    height: 9,
    width: 9,
  },
  todayHeader: {
    alignItems: 'center',
    flexDirection: 'row',
    gap: 10,
  },
});
