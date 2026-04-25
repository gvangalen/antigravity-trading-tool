// Detecteer of we op de server of lokaal draaien om de juiste API-URL te kiezen
const isServer = typeof window === 'undefined';
const isLocalhost = !isServer && (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1');

export const API_BASE_URL = !isServer && window.location.hostname.includes('tradamind.com')
  ? 'https://www.tradamind.com'  // Zonder /api omdat routes dit zelf toevoegen
  : (process.env.NEXT_PUBLIC_API_BASE_URL || 'http://localhost:8000');


