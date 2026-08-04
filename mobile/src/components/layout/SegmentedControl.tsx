import { Pressable, StyleSheet, Text, View } from 'react-native';

import { theme } from '../../constants/theme';
import { typography } from '../../constants/typography';
import { preferenceColors, useAppPreferences } from '../../preferences/AppPreferencesProvider';

type SegmentedItem<T extends string> = {
  key: T;
  label: string;
};

type SegmentedControlProps<T extends string> = {
  compact?: boolean;
  items: Array<SegmentedItem<T>>;
  onChange: (value: T) => void;
  selected: T;
};

export function SegmentedControl<T extends string>({
  compact = false,
  items,
  onChange,
  selected,
}: SegmentedControlProps<T>) {
  const { appearance } = useAppPreferences();
  const colors = preferenceColors(appearance);

  return (
    <View
      style={[
        styles.shell,
        compact && styles.shellCompact,
        { backgroundColor: colors.backgroundSoft, borderColor: colors.border },
      ]}
    >
      {items.map((item) => {
        const active = item.key === selected;
        return (
          <Pressable
            key={item.key}
            onPress={() => onChange(item.key)}
            style={[
              styles.item,
              compact && styles.itemCompact,
              active && {
                backgroundColor: colors.surface,
                borderColor: colors.accent,
              },
            ]}
          >
            <Text
              numberOfLines={1}
              style={[
                styles.label,
                compact && styles.labelCompact,
                { color: active ? colors.accent : colors.textMuted },
              ]}
            >
              {item.label}
            </Text>
          </Pressable>
        );
      })}
    </View>
  );
}

const styles = StyleSheet.create({
  item: {
    alignItems: 'center',
    borderColor: 'transparent',
    borderRadius: theme.radius.sm,
    borderWidth: 1,
    flex: 1,
    minHeight: 34,
    justifyContent: 'center',
    paddingHorizontal: 10,
    paddingVertical: 6,
  },
  itemCompact: {
    minHeight: 24,
    paddingHorizontal: 10,
    paddingVertical: 3,
  },
  label: {
    ...typography.chipLabel,
    textAlign: 'center',
  },
  labelCompact: {
    ...typography.chipLabelCompact,
  },
  shell: {
    borderRadius: 18,
    borderWidth: 1,
    flexDirection: 'row',
    gap: 6,
    marginTop: theme.spacing.sm,
    padding: 6,
  },
  shellCompact: {
    alignSelf: 'flex-start',
    gap: 4,
    padding: 4,
  },
});
