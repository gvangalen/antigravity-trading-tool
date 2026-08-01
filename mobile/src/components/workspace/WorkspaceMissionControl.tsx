import { StyleSheet, Text, View } from 'react-native';

import { StatusTone, theme } from '../../constants/theme';
import { preferenceColors, useAppPreferences } from '../../preferences/AppPreferencesProvider';
import { CardShell } from '../cards/CardShell';
import { StatusChip } from '../layout/StatusChip';
import { SectionHeader } from '../layout/SectionHeader';

export type MissionControlSection = {
  key: string;
  label: string;
  summary: string;
  tone?: StatusTone;
  items?: string[];
};

type WorkspaceMissionControlProps = {
  title?: string;
  sections: MissionControlSection[];
};

export function WorkspaceMissionControl({
  title = 'Today, reviews, risks and follow-through',
  sections,
}: WorkspaceMissionControlProps) {
  const { appearance } = useAppPreferences();
  const colors = preferenceColors(appearance);

  return (
    <View style={styles.wrapper}>
      <SectionHeader
        compact
        label="Mission Control"
        title={title}
      />
      <View style={styles.grid}>
        {sections.map((section) => (
          <CardShell key={section.key} emphasis="standard">
            <View style={styles.cardTop}>
              <Text style={styles.cardLabel}>{section.label}</Text>
              <StatusChip compact label={section.label} tone={section.tone || 'neutral'} />
            </View>
            <Text style={[styles.cardSummary, { color: colors.text }]}>{section.summary}</Text>
            {section.items && section.items.length > 0 ? (
              <View style={styles.items}>
                {section.items.slice(0, 3).map((item, index) => (
                  <View key={`${section.key}-${index}`} style={styles.itemRow}>
                    <View style={[styles.dot, { backgroundColor: colors.textDim }]} />
                    <Text style={[styles.itemText, { color: colors.textMuted }]}>{item}</Text>
                  </View>
                ))}
              </View>
            ) : null}
          </CardShell>
        ))}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  cardLabel: {
    color: theme.colors.textDim,
    fontSize: theme.typography.label,
    fontWeight: '900',
    letterSpacing: 1.3,
    textTransform: 'uppercase',
  },
  cardSummary: {
    fontSize: 14,
    fontWeight: '800',
    lineHeight: 20,
    marginTop: theme.spacing.sm,
  },
  cardTop: {
    alignItems: 'center',
    flexDirection: 'row',
    gap: theme.spacing.sm,
    justifyContent: 'space-between',
  },
  dot: {
    borderRadius: theme.radius.pill,
    height: 5,
    marginTop: 7,
    width: 5,
  },
  grid: {
    paddingHorizontal: theme.spacing.lg,
  },
  itemRow: {
    flexDirection: 'row',
    gap: theme.spacing.sm,
  },
  itemText: {
    flex: 1,
    fontSize: 13,
    fontWeight: '600',
    lineHeight: 19,
  },
  items: {
    gap: theme.spacing.xs,
    marginTop: theme.spacing.md,
  },
  wrapper: {
    paddingTop: theme.spacing.md,
  },
});
