import { ReactNode } from 'react';
import { Modal, Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { theme } from '../../constants/theme';
import { preferenceColors, preferenceLabels, useAppPreferences } from '../../preferences/AppPreferencesProvider';
import { triggerHaptic } from '../../utils/haptics';

type BottomSheetProps = {
  visible: boolean;
  title: string;
  children: ReactNode;
  onClose: () => void;
};

export function BottomSheet({ visible, title, children, onClose }: BottomSheetProps) {
  const insets = useSafeAreaInsets();
  const { appearance, language } = useAppPreferences();
  const colors = preferenceColors(appearance);
  const labels = preferenceLabels(language);

  return (
    <Modal animationType="slide" transparent visible={visible} onRequestClose={onClose}>
      <View style={styles.overlay}>
        <Pressable style={styles.backdrop} onPress={onClose} />
        <View
          style={[
            styles.sheet,
            {
              backgroundColor: colors.surface,
              borderColor: colors.border,
              paddingBottom: Math.max(insets.bottom, theme.spacing.lg),
            },
          ]}
        >
          <View style={[styles.handle, { backgroundColor: colors.borderStrong }]} />
          <View style={styles.header}>
            <Text style={[styles.title, { color: colors.text }]}>{title}</Text>
            <Pressable
              onPress={async () => {
                await triggerHaptic('selection');
                onClose();
              }}
              style={({ pressed }) => [styles.close, pressed && styles.pressed]}
            >
              <Text style={[styles.closeText, { color: colors.textSoft }]}>{labels.close}</Text>
            </Pressable>
          </View>
          <ScrollView
            contentContainerStyle={styles.content}
            keyboardShouldPersistTaps="handled"
            showsVerticalScrollIndicator={false}
          >
            {children}
          </ScrollView>
        </View>
      </View>
    </Modal>
  );
}

const styles = StyleSheet.create({
  backdrop: {
    ...StyleSheet.absoluteFillObject,
  },
  close: {
    backgroundColor: theme.colors.surfaceMuted,
    borderColor: theme.colors.borderStrong,
    borderRadius: theme.radius.pill,
    borderWidth: 1,
    paddingHorizontal: theme.spacing.md,
    paddingVertical: theme.spacing.sm,
  },
  closeText: {
    color: theme.colors.textSoft,
    fontSize: 12,
    fontWeight: '900',
  },
  content: {
    gap: theme.spacing.md,
  },
  handle: {
    alignSelf: 'center',
    backgroundColor: theme.colors.borderStrong,
    borderRadius: theme.radius.pill,
    height: 4,
    marginBottom: theme.spacing.md,
    width: 44,
  },
  header: {
    alignItems: 'center',
    flexDirection: 'row',
    justifyContent: 'space-between',
    marginBottom: theme.spacing.lg,
  },
  overlay: {
    backgroundColor: 'rgba(2, 6, 23, 0.62)',
    flex: 1,
    justifyContent: 'flex-end',
  },
  pressed: {
    opacity: 0.82,
  },
  sheet: {
    backgroundColor: theme.colors.surface,
    borderColor: theme.colors.border,
    borderTopLeftRadius: 28,
    borderTopRightRadius: 28,
    borderWidth: 1,
    maxHeight: '88%',
    paddingHorizontal: theme.spacing.lg,
    paddingTop: theme.spacing.md,
    ...theme.shadows.sheet,
  },
  title: {
    color: theme.colors.text,
    flex: 1,
    fontSize: theme.typography.title,
    fontWeight: '900',
  },
});
