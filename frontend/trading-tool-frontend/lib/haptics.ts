import { Haptics, ImpactStyle, NotificationType } from '@capacitor/haptics';
import { Capacitor } from '@capacitor/core';

/**
 * 📳 HapticFeedback Utility
 * Provides native vibration feedback for app interactions.
 * Safely checks for Capacitor context to avoid crashes on web.
 */
export const hapticFeedback = {
  impact: async (style: ImpactStyle = ImpactStyle.Medium) => {
    if (Capacitor.isNativePlatform()) {
      await Haptics.impact({ style });
    }
  },
  
  notification: async (type: NotificationType = NotificationType.Success) => {
    if (Capacitor.isNativePlatform()) {
      await Haptics.notification({ type });
    }
  },

  selection: async () => {
    if (Capacitor.isNativePlatform()) {
      await Haptics.selectionStart();
    }
  },

  vibrate: async () => {
    if (Capacitor.isNativePlatform()) {
      await Haptics.vibrate();
    }
  }
};
