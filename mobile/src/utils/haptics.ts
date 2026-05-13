export type HapticIntent = 'selection' | 'success' | 'warning' | 'impact';

export async function triggerHaptic(_intent: HapticIntent = 'selection') {
  // Foundation placeholder: wire to expo-haptics when native feedback is enabled.
  return Promise.resolve();
}
