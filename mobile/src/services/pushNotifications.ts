import * as Notifications from 'expo-notifications';
import { Platform } from 'react-native';

import type { MainTabParamList } from '../navigation/MainTabNavigator';
import { apiClient } from './apiClient';
import { deleteItemAsync, getItemAsync, setItemAsync } from './secureStore';

const PUSH_TOKEN_KEY = 'tradamind_mobile_push_token';

export type PushRegistrationResult =
  | { status: 'registered'; token: string }
  | { status: 'denied' | 'unavailable'; reason: string };

export type MobileNotificationData = {
  type?: string;
  symbol?: string;
  title?: string;
  description?: string;
  event_id?: number;
  bot_id?: number;
  strategy_id?: number;
  report_type?: string;
};

export type NotificationRoute =
  | { screen: 'FINN'; params?: { prefill?: string; source?: string; contextMetric?: string; symbol?: string } }
  | { screen: 'Setup'; params?: MainTabParamList['Setup'] }
  | { screen: 'Automation'; params?: MainTabParamList['Automation'] }
  | { screen: 'Report'; params?: MainTabParamList['Report'] }
  | { screen: 'Watchlist'; params?: MainTabParamList['Watchlist'] };

Notifications.setNotificationHandler({
  handleNotification: async () => ({
    shouldPlaySound: false,
    shouldSetBadge: false,
    shouldShowBanner: true,
    shouldShowList: true,
  }),
});

export async function registerMobilePushToken(userId: number): Promise<PushRegistrationResult> {
  if (Platform.OS === 'web') {
    return { status: 'unavailable', reason: 'Native push is not available on web.' };
  }

  const permission = await Notifications.getPermissionsAsync();
  const finalPermission =
    permission.status === 'granted' ? permission : await Notifications.requestPermissionsAsync();

  if (finalPermission.status !== 'granted') {
    return { status: 'denied', reason: 'Push permission was not granted.' };
  }

  const tokenResponse = await Notifications.getExpoPushTokenAsync();
  const token = tokenResponse.data;

  await apiClient.post('/api/notifications/mobile/subscribe', {
    device_name: Platform.OS,
    push_token: token,
    user_id: userId,
  });
  await setItemAsync(PUSH_TOKEN_KEY, token);

  return { status: 'registered', token };
}

export async function unregisterMobilePushToken() {
  const token = await getItemAsync(PUSH_TOKEN_KEY);
  if (!token) return;

  try {
    await apiClient.post('/api/notifications/mobile/unsubscribe', {
      push_token: token,
    });
  } finally {
    await deleteItemAsync(PUSH_TOKEN_KEY);
  }
}

export async function getStoredPushToken() {
  return getItemAsync(PUSH_TOKEN_KEY);
}

export function normalizeNotificationData(data: Record<string, unknown> | undefined): MobileNotificationData {
  if (!data) return {};

  return {
    bot_id: numberValue(data.bot_id),
    description: stringValue(data.description),
    event_id: numberValue(data.event_id),
    report_type: stringValue(data.report_type),
    strategy_id: numberValue(data.strategy_id),
    symbol: stringValue(data.symbol)?.toUpperCase(),
    title: stringValue(data.title),
    type: stringValue(data.type),
  };
}

export function routeForNotification(data: MobileNotificationData): NotificationRoute {
  const type = data.type ?? '';
  const symbol = data.symbol ?? 'BTC';
  const title = data.title ?? notificationTitle(type, symbol);
  const description = data.description ?? 'Open de context en vraag FINN om uitleg voordat je actie neemt.';

  if (type === 'bot_action_ready') {
    return {
      screen: 'Automation',
      params: { notificationType: type, symbol },
    };
  }

  if (type === 'report_ready') {
    return {
      screen: 'Report',
      params: { notificationType: type, symbol },
    };
  }

  if (type === 'strategy_invalidated') {
    return {
      screen: 'Setup',
      params: { notificationType: type, symbol },
    };
  }

  if (type === 'risk_warning') {
    return {
      screen: 'FINN',
      params: {
        prefill: `Leg deze risicomelding uit voor ${symbol}: "${title}" - ${description}`,
        source: 'push-risk-warning',
      },
    };
  }

  if (type === 'draft_needs_review') {
    return {
      screen: 'FINN',
      params: {
        prefill: `Open mijn draft-context en leg uit wat ik veilig kan bevestigen: "${title}" - ${description}`,
        source: 'push-draft-review',
      },
    };
  }

  return {
    screen: 'FINN',
    params: {
      prefill: `Bespreek deze melding: "${title}" - ${description}`,
      source: type ? `push-${type}` : 'push',
    },
  };
}

function notificationTitle(type: string, symbol: string) {
  if (type === 'daily_briefing_ready') return 'Daily briefing ready';
  if (type === 'bot_action_ready') return `${symbol} bot decision ready`;
  if (type === 'risk_warning') return `${symbol} risk warning`;
  if (type === 'strategy_invalidated') return `${symbol} strategy needs review`;
  if (type === 'report_ready') return 'Report ready';
  if (type === 'draft_needs_review') return 'Draft needs review';
  return 'Tradamind update';
}

function stringValue(value: unknown) {
  return typeof value === 'string' && value.trim() ? value.trim() : undefined;
}

function numberValue(value: unknown) {
  if (typeof value === 'number' && Number.isFinite(value)) return value;
  if (typeof value === 'string' && value.trim()) {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : undefined;
  }
  return undefined;
}
