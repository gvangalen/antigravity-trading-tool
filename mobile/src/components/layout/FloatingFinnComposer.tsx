import { Pressable, StyleSheet, Text, View } from 'react-native';
import { Feather } from '@expo/vector-icons';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { theme } from '../../constants/theme';
import { useIntelligenceContext } from '../../contexts/ActiveIntelligenceContext';
import { useFinnOverlay } from '../../contexts/FinnOverlayContext';
import { preferenceColors, useAppPreferences } from '../../preferences/AppPreferencesProvider';
import { triggerHaptic } from '../../utils/haptics';

export function FloatingFinnComposer() {
  const insets = useSafeAreaInsets();
  const { appearance } = useAppPreferences();
  const colors = preferenceColors(appearance);
  const { context } = useIntelligenceContext();
  const { openFinn } = useFinnOverlay();

  return (
    <View pointerEvents="box-none" style={[styles.wrap, { bottom: insets.bottom + 62 }]}>
      <Pressable
        onPress={async () => {
          await triggerHaptic('selection');
          openFinn({
            prefill: '',
            source: 'floating-composer',
            symbol: context.asset,
          });
        }}
        style={({ pressed }) => [
          styles.composer,
          {
            backgroundColor: colors.surface,
            borderColor: colors.border,
            shadowColor: appearance === 'light' ? '#0F172A' : '#000000',
            shadowOpacity: appearance === 'light' ? 0.06 : 0.22,
          },
          pressed && styles.pressed,
        ]}
      >
        <View style={[styles.plusWrap, { backgroundColor: colors.backgroundSoft, borderColor: colors.borderSubtle }]}>
          <Feather name="plus" size={18} color={colors.textDim} />
        </View>
        <View style={styles.copy}>
          <Text style={[styles.placeholder, { color: colors.textDim }]} numberOfLines={1}>
            Ask FINN, search an asset or add an indicator...
          </Text>
        </View>
        <View style={[styles.sendPill, { backgroundColor: colors.textDim }]}>
          <Feather name="send" size={16} color="#ffffff" />
        </View>
      </Pressable>
    </View>
  );
}

const styles = StyleSheet.create({
  composer: {
    alignItems: 'center',
    borderRadius: 26,
    borderWidth: 1,
    flexDirection: 'row',
    gap: 10,
    marginHorizontal: 24,
    minHeight: 54,
    paddingHorizontal: 12,
    paddingVertical: 7,
    shadowOffset: { width: 0, height: 8 },
    shadowRadius: 20,
  },
  copy: {
    flex: 1,
    gap: 0,
  },
  placeholder: {
    fontSize: 11,
    fontWeight: '500',
  },
  plusWrap: {
    alignItems: 'center',
    borderRadius: 18,
    borderWidth: 1,
    height: 34,
    justifyContent: 'center',
    width: 34,
  },
  pressed: {
    opacity: 0.9,
    transform: [{ scale: 0.99 }],
  },
  sendPill: {
    alignItems: 'center',
    borderRadius: 18,
    justifyContent: 'center',
    height: 38,
    width: 38,
  },
  wrap: {
    left: 0,
    position: 'absolute',
    right: 0,
  },
});
