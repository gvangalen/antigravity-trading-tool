import { Pressable, StyleSheet, Text, View } from 'react-native';

import { theme } from '../../constants/theme';
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
                borderColor: colors.border,
              },
            ]}
          >
            <Text
              numberOfLines={1}
              style={[
                styles.label,
                compact && styles.labelCompact,
                { color: active ? colors.text : colors.textMuted },
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
    borderRadius: theme.radius.lg,
    borderWidth: 1,
    flex: 1,
    minHeight: 40,
    justifyContent: 'center',
    paddingHorizontal: theme.spacing.sm,
    paddingVertical: theme.spacing.xs,
  },
  itemCompact: {
    minHeight: 34,
    paddingHorizontal: theme.spacing.sm,
    paddingVertical: theme.spacing.xxs,
  },
  label: {
    fontSize: 11,
    fontWeight: '900',
    letterSpacing: 0,
    textAlign: 'center',
    textTransform: 'uppercase',
  },
  labelCompact: {
    fontSize: 10,
  },
  shell: {
    borderRadius: theme.radius.xl,
    borderWidth: 1,
    flexDirection: 'row',
    gap: theme.spacing.xs,
    marginTop: theme.spacing.sm,
    padding: theme.spacing.xs,
  },
  shellCompact: {
    alignSelf: 'flex-start',
  },
});
