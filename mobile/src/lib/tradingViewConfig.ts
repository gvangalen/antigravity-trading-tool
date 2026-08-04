export type TradingViewInterval = '15' | '60' | '240' | 'D' | 'W' | 'M' | '3M';
export type TradingViewTheme = 'light' | 'dark';

export const DEFAULT_TRADINGVIEW_INTERVAL: TradingViewInterval = 'D';
export const ANALYSIS_CHART_INTERVAL_KEY = 'analysis_chart_interval';

const APP_TIMEFRAME_TO_INTERVAL: Record<string, TradingViewInterval> = {
  '15m': '15',
  '1h': '60',
  '4h': '240',
  '1d': 'D',
  '1w': 'W',
  '1m': 'M',
  '3m': '3M',
};

const VALID_INTERVALS = new Set<TradingViewInterval>(['15', '60', '240', 'D', 'W', 'M', '3M']);

export function toTradingViewSymbol(symbol?: string) {
  const normalized = String(symbol || 'BTC').trim().toUpperCase();
  return normalized.includes(':') ? normalized : `BINANCE:${normalized}USDT`;
}

export function toTradingViewTheme(theme?: string): TradingViewTheme {
  return String(theme || '').toLowerCase() === 'dark' ? 'dark' : 'light';
}

export function normalizeTradingViewInterval(value: unknown): TradingViewInterval {
  const normalized = String(value || '').trim().toUpperCase();
  if (VALID_INTERVALS.has(normalized as TradingViewInterval)) {
    return normalized as TradingViewInterval;
  }

  return APP_TIMEFRAME_TO_INTERVAL[String(value || '').trim().toLowerCase()] ?? DEFAULT_TRADINGVIEW_INTERVAL;
}

export function toTradingViewInterval(value: string) {
  return normalizeTradingViewInterval(value);
}

export function buildTradingViewEmbedConfig(options: {
  interval?: TradingViewInterval;
  symbol?: string;
  theme?: TradingViewTheme;
}) {
  return {
    allow_symbol_change: false,
    autosize: true,
    calendar: false,
    hide_side_toolbar: true,
    hide_top_toolbar: false,
    interval: normalizeTradingViewInterval(options.interval),
    locale: 'en',
    save_image: false,
    style: '1',
    studies: [],
    support_host: 'https://www.tradingview.com',
    symbol: toTradingViewSymbol(options.symbol),
    theme: toTradingViewTheme(options.theme),
    timezone: 'Etc/UTC',
  };
}

export function buildTradingViewWidgetUrl(options: {
  interval?: TradingViewInterval;
  symbol?: string;
  theme?: TradingViewTheme;
}) {
  const params = new URLSearchParams({
    interval: normalizeTradingViewInterval(options.interval),
    symbol: toTradingViewSymbol(options.symbol),
    theme: toTradingViewTheme(options.theme),
  });

  return `https://www.tradingview.com/widgetembed/?${params.toString()}`;
}

export function parseTradingViewIntervalFromUrl(url: string) {
  try {
    const parsedUrl = new URL(url);
    const interval = parsedUrl.searchParams.get('interval');
    return interval ? normalizeTradingViewInterval(interval) : null;
  } catch {
    return null;
  }
}
