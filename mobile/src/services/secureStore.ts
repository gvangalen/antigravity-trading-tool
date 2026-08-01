import * as ExpoSecureStore from 'expo-secure-store';
import { Platform } from 'react-native';

declare const __DEV__: boolean;

const nativeDevFallback = new Map<string, string>();

function getBrowserStorage() {
  try {
    return typeof window !== 'undefined' ? window.localStorage : null;
  } catch {
    return null;
  }
}

function hasNativeSecureStore() {
  if (Platform.OS === 'web') {
    return false;
  }

  return (
    typeof ExpoSecureStore?.getItemAsync === 'function' &&
    typeof ExpoSecureStore?.setItemAsync === 'function' &&
    typeof ExpoSecureStore?.deleteItemAsync === 'function'
  );
}

function assertNativeSecureStoreAvailable() {
  if (Platform.OS === 'web' || hasNativeSecureStore()) {
    return;
  }

  if (__DEV__) {
    console.warn('[secureStore] Native SecureStore unavailable; using in-memory dev fallback.');
    return;
  }

  throw new Error('Native SecureStore is required for release builds.');
}

export async function getItemAsync(key: string) {
  if (hasNativeSecureStore()) {
    return ExpoSecureStore.getItemAsync(key);
  }

  if (Platform.OS === 'web') {
    const storage = getBrowserStorage();
    return storage ? storage.getItem(key) : null;
  }

  assertNativeSecureStoreAvailable();
  return nativeDevFallback.get(key) ?? null;
}

export async function setItemAsync(key: string, value: string) {
  if (hasNativeSecureStore()) {
    await ExpoSecureStore.setItemAsync(key, value);
    return;
  }

  if (Platform.OS === 'web') {
    const storage = getBrowserStorage();
    storage?.setItem(key, value);
    return;
  }

  assertNativeSecureStoreAvailable();
  nativeDevFallback.set(key, value);
}

export async function deleteItemAsync(key: string) {
  if (hasNativeSecureStore()) {
    await ExpoSecureStore.deleteItemAsync(key);
    return;
  }

  if (Platform.OS === 'web') {
    const storage = getBrowserStorage();
    storage?.removeItem(key);
    return;
  }

  assertNativeSecureStoreAvailable();
  nativeDevFallback.delete(key);
}
