import { Pressable, StyleSheet, Text, ViewStyle } from 'react-native';

import { theme } from '../../constants/theme';
import { preferenceColors, useAppPreferences } from '../../preferences/AppPreferencesProvider';

type AppButtonVariant = 'primary' | 'secondary' | 'danger' | 'ghost' | 'chip';

type AppButtonProps = {
  label: string;
  onPress: () => void | Promise<void>;
  disabled?: boolean;
  variant?: AppButtonVariant;
  style?: ViewStyle;
  textColor?: string;
};

export function AppButton({
  label,
  onPress,
  disabled = false,
  variant = 'primary',
  style,
  textColor,
}: AppButtonProps) {
  const { appearance } = useAppPreferences();
  const colors = preferenceColors(appearance);

  const palette = {
    primary: {
      backgroundColor: colors.accent,
      borderColor: colors.accent,
      textColor: '#FFFFFF',
    },
    secondary: {
      backgroundColor: colors.surface,
      borderColor: colors.border,
      textColor: colors.text,
    },
    danger: {
      backgroundColor: colors.danger,
      borderColor: colors.danger,
      textColor: '#FFFFFF',
    },
    ghost: {
      backgroundColor: 'transparent',
      borderColor: 'transparent',
      textColor: colors.textSoft,
    },
    chip: {
      backgroundColor: colors.surfaceMuted,
      borderColor: colors.borderStrong,
      textColor: colors.textSoft,
    },
  }[variant];

  return (
    <Pressable
      disabled={disabled}
      onPress={onPress}
      style={({ pressed }) => [
        styles.base,
        variant === 'chip' ? styles.chip : styles.standard,
        {
          backgroundColor: disabled ? colors.surfaceMuted : palette.backgroundColor,
          borderColor: disabled ? colors.border : palette.borderColor,
        },
        pressed && !disabled && styles.pressed,
        style,
      ]}
    >
      <Text
        style={[
          styles.label,
          {
            color: disabled ? colors.textDim : textColor || palette.textColor,
          },
        ]}
      >
        {label}
      </Text>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  base: {
    alignItems: 'center',
    borderRadius: 10,
    borderWidth: 1,
    justifyContent: 'center',
  },
  chip: {
    minHeight: 36,
    paddingHorizontal: theme.spacing.md,
    paddingVertical: 8,
  },
  label: {
    fontSize: 14,
    fontWeight: '700',
    letterSpacing: 0,
  },
  pressed: {
    opacity: 0.9,
    transform: [{ scale: 0.99 }],
  },
  standard: {
    minHeight: 48,
    paddingHorizontal: theme.spacing.lg,
    paddingVertical: theme.spacing.sm,
  },
});
