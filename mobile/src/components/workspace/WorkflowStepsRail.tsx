import { Feather } from '@expo/vector-icons';
import { ScrollView, StyleSheet, Text, View } from 'react-native';

import { theme } from '../../constants/theme';
import { typography } from '../../constants/typography';
import { preferenceColors, useAppPreferences } from '../../preferences/AppPreferencesProvider';

type WorkflowStep = {
  body: string;
  icon: keyof typeof Feather.glyphMap;
  step: number;
  title: string;
};

export function WorkflowStepsRail({ steps }: { steps: WorkflowStep[] }) {
  const { appearance } = useAppPreferences();
  const colors = preferenceColors(appearance);

  if (steps.length === 0) return null;

  return (
    <ScrollView
      horizontal
      showsHorizontalScrollIndicator={false}
      contentContainerStyle={styles.railContent}
      style={styles.rail}
    >
      {steps.map((item) => (
        <View
          key={`${item.step}-${item.title}`}
          style={[
            styles.card,
            {
              backgroundColor: colors.surface,
              borderColor: colors.borderSubtle,
            },
          ]}
        >
          <View
            style={[
              styles.iconWrap,
              {
                backgroundColor: `${colors.accent}0D`,
                borderColor: `${colors.accent}1A`,
              },
            ]}
          >
            <Feather color={colors.accent} name={item.icon} size={16} />
          </View>
          <View style={styles.copy}>
            <Text style={[styles.title, { color: colors.text }]} numberOfLines={1}>
              {item.step} {item.title}
            </Text>
            <Text style={[styles.body, { color: colors.textMuted }]} numberOfLines={2}>
              {item.body}
            </Text>
          </View>
        </View>
      ))}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  body: {
    ...typography.chipLabelCompact,
    fontWeight: '600',
    lineHeight: 13,
    marginTop: 1,
    textTransform: 'none',
  },
  card: {
    borderRadius: 16,
    borderWidth: 1,
    flexDirection: 'row',
    marginRight: theme.spacing.xs,
    minHeight: 52,
    paddingHorizontal: 10,
    paddingVertical: 7,
    width: 184,
  },
  copy: {
    flex: 1,
    justifyContent: 'center',
    minWidth: 0,
  },
  iconWrap: {
    alignItems: 'center',
    borderRadius: 12,
    borderWidth: 1,
    height: 26,
    justifyContent: 'center',
    marginRight: 8,
    width: 26,
  },
  rail: {
    marginTop: theme.spacing.xs,
  },
  railContent: {
    paddingHorizontal: theme.spacing.lg,
    paddingRight: theme.spacing.lg,
  },
  title: {
    ...typography.subcopy,
    fontWeight: '800',
    lineHeight: 15,
  },
});
