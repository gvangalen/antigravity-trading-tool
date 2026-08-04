import { ReactNode, useMemo, useRef } from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import { Feather } from '@expo/vector-icons';
import { Swipeable } from 'react-native-gesture-handler';

import { theme } from '../../constants/theme';
import { preferenceColors, useAppPreferences } from '../../preferences/AppPreferencesProvider';
import { triggerHaptic } from '../../utils/haptics';

type SwipeAction = {
  key: string;
  label: string;
  icon: keyof typeof Feather.glyphMap;
  tone?: 'accent' | 'danger' | 'neutral';
  onPress: () => void | Promise<void>;
};

export function SwipeActionRow({
  children,
  disabled = false,
  actions,
}: {
  children: ReactNode;
  disabled?: boolean;
  actions: SwipeAction[];
}) {
  const swipeableRef = useRef<Swipeable | null>(null);
  const { appearance } = useAppPreferences();
  const colors = preferenceColors(appearance);
  const visibleActions = useMemo(() => actions.filter(Boolean), [actions]);

  if (disabled || visibleActions.length === 0) {
    return <>{children}</>;
  }

  const renderRightActions = () => (
    <View style={styles.actionsWrap}>
      {visibleActions.map((action) => {
        const palette =
          action.tone === 'danger'
            ? {
                background: `${colors.danger}14`,
                border: `${colors.danger}24`,
                color: colors.danger,
              }
            : action.tone === 'neutral'
              ? {
                  background: colors.surfaceMuted,
                  border: colors.borderStrong,
                  color: colors.textDim,
                }
              : {
                  background: `${colors.accent}10`,
                  border: `${colors.accent}20`,
                  color: colors.accent,
                };

        return (
          <Pressable
            key={action.key}
            onPress={async () => {
              swipeableRef.current?.close();
              await triggerHaptic(action.tone === 'danger' ? 'warning' : 'selection');
              await action.onPress();
            }}
            style={[
              styles.actionButton,
              {
                backgroundColor: palette.background,
                borderColor: palette.border,
              },
            ]}
          >
            <Feather color={palette.color} name={action.icon} size={12} />
            <Text style={[styles.actionLabel, { color: palette.color }]}>{action.label}</Text>
          </Pressable>
        );
      })}
    </View>
  );

  return (
    <Swipeable overshootRight={false} ref={swipeableRef} renderRightActions={renderRightActions}>
      {children}
    </Swipeable>
  );
}

const styles = StyleSheet.create({
  actionButton: {
    alignItems: 'center',
    borderRadius: 14,
    borderWidth: 1,
    gap: 4,
    justifyContent: 'center',
    minWidth: 68,
    paddingHorizontal: 10,
    paddingVertical: 8,
  },
  actionLabel: {
    fontSize: 9,
    fontWeight: '800',
    letterSpacing: 0.5,
    textTransform: 'uppercase',
  },
  actionsWrap: {
    flexDirection: 'row',
    gap: 6,
    justifyContent: 'flex-end',
    paddingLeft: 6,
    paddingVertical: 2,
  },
});
