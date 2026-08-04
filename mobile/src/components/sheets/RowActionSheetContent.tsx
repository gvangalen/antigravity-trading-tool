import { Feather } from '@expo/vector-icons';
import { Pressable, StyleSheet, Text, View } from 'react-native';

import { theme } from '../../constants/theme';
import { preferenceColors, useAppPreferences } from '../../preferences/AppPreferencesProvider';
import { triggerHaptic } from '../../utils/haptics';

type RowActionItem = {
  key: string;
  label: string;
  description?: string;
  icon: keyof typeof Feather.glyphMap;
  tone?: 'accent' | 'danger' | 'neutral';
  onPress: () => void | Promise<void>;
};

export function RowActionSheetContent({
  actions,
}: {
  actions: RowActionItem[];
}) {
  const { appearance } = useAppPreferences();
  const colors = preferenceColors(appearance);

  return (
    <View style={styles.stack}>
      {actions.map((action) => {
        const color =
          action.tone === 'danger'
            ? colors.danger
            : action.tone === 'neutral'
              ? colors.textDim
              : colors.accent;

        return (
          <Pressable
            key={action.key}
            onPress={async () => {
              await triggerHaptic(action.tone === 'danger' ? 'warning' : 'selection');
              await action.onPress();
            }}
            style={[styles.row, { borderColor: colors.borderSubtle }]}
          >
            <View style={[styles.iconWrap, { backgroundColor: `${color}10`, borderColor: `${color}20` }]}>
              <Feather color={color} name={action.icon} size={16} />
            </View>
            <View style={styles.copy}>
              <Text style={[styles.label, { color: colors.text }]}>{action.label}</Text>
              {action.description ? (
                <Text style={[styles.description, { color: colors.textMuted }]}>{action.description}</Text>
              ) : null}
            </View>
            <Feather color={colors.textDim} name="chevron-right" size={16} />
          </Pressable>
        );
      })}
    </View>
  );
}

export function ConfirmDestructiveSheetContent({
  body,
  confirmLabel,
  onConfirm,
  title,
}: {
  title: string;
  body: string;
  confirmLabel: string;
  onConfirm: () => void | Promise<void>;
}) {
  const { appearance } = useAppPreferences();
  const colors = preferenceColors(appearance);

  return (
    <View style={styles.confirmWrap}>
      <View style={[styles.confirmIcon, { backgroundColor: `${colors.danger}12`, borderColor: `${colors.danger}24` }]}>
        <Feather color={colors.danger} name="trash-2" size={18} />
      </View>
      <Text style={[styles.confirmTitle, { color: colors.text }]}>{title}</Text>
      <Text style={[styles.confirmBody, { color: colors.textMuted }]}>{body}</Text>
      <Pressable
        onPress={async () => {
          await triggerHaptic('warning');
          await onConfirm();
        }}
        style={[styles.confirmButton, { backgroundColor: colors.danger }]}
      >
        <Text style={styles.confirmButtonText}>{confirmLabel}</Text>
      </Pressable>
    </View>
  );
}

const styles = StyleSheet.create({
  confirmBody: {
    fontSize: 14,
    lineHeight: 22,
    textAlign: 'center',
  },
  confirmButton: {
    alignItems: 'center',
    borderRadius: theme.radius.button,
    paddingHorizontal: theme.spacing.md,
    paddingVertical: theme.spacing.sm,
  },
  confirmButtonText: {
    color: theme.colors.white,
    fontSize: 13,
    fontWeight: '800',
    letterSpacing: 0.4,
  },
  confirmIcon: {
    alignItems: 'center',
    borderRadius: 18,
    borderWidth: 1,
    height: 44,
    justifyContent: 'center',
    width: 44,
  },
  confirmTitle: {
    fontSize: 18,
    fontWeight: '900',
    textAlign: 'center',
  },
  confirmWrap: {
    alignItems: 'center',
    gap: theme.spacing.sm,
  },
  copy: {
    flex: 1,
    gap: 4,
  },
  description: {
    fontSize: 13,
    lineHeight: 18,
  },
  iconWrap: {
    alignItems: 'center',
    borderRadius: 14,
    borderWidth: 1,
    height: 36,
    justifyContent: 'center',
    width: 36,
  },
  label: {
    fontSize: 15,
    fontWeight: '800',
  },
  row: {
    alignItems: 'center',
    borderBottomWidth: 1,
    flexDirection: 'row',
    gap: theme.spacing.sm,
    paddingVertical: theme.spacing.sm,
  },
  stack: {
    gap: 2,
  },
});
