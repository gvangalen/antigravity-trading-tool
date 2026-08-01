import * as ExpoSecureStore from 'expo-secure-store';
import { Platform } from 'react-native';

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

export async function getItemAsync(key: string) {
  if (hasNativeSecureStore()) {
    return ExpoSecureStore.getItemAsync(key);
  }

  const storage = getBrowserStorage();
  return storage ? storage.getItem(key) : null;
}

export async function setItemAsync(key: string, value: string) {
  if (hasNativeSecureStore()) {
    await ExpoSecureStore.setItemAsync(key, value);
    return;
  }

  const storage = getBrowserStorage();
  storage?.setItem(key, value);
}

export async function deleteItemAsync(key: string) {
  if (hasNativeSecureStore()) {
    await ExpoSecureStore.deleteItemAsync(key);
    return;
  }

  const storage = getBrowserStorage();
  storage?.removeItem(key);
}
