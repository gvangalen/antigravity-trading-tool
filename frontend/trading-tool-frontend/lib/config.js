// Detecteer of we op de server, web of in een native Capacitor shell draaien.
const isServer = typeof window === 'undefined';
export const IS_NATIVE_APP = !isServer && (
  window.location.protocol === 'capacitor:' ||
  window.location.protocol === 'ionic:' ||
  !!window.Capacitor?.isNativePlatform?.() ||
  (!!window.Capacitor && window.location.hostname === 'localhost')
);
const isTradamindWeb = !isServer && window.location.hostname.includes('tradamind.com');

export const API_BASE_URL = IS_NATIVE_APP
  ? (process.env.NEXT_PUBLIC_MOBILE_API_BASE_URL || 'https://tradamind.com')
  : isTradamindWeb
    ? window.location.origin
    : (process.env.NEXT_PUBLIC_API_BASE_URL || 'http://localhost:8000');
