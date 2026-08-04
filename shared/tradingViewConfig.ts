export type TradingViewTheme = 'light' | 'dark';
export type TradingViewInterval = '15' | '60' | '240' | 'D' | 'W' | 'M' | '3M';

export const DEFAULT_TRADINGVIEW_EXCHANGE = 'BINANCE';
export const DEFAULT_TRADINGVIEW_QUOTE = 'USDT';
export const DEFAULT_TRADINGVIEW_INTERVAL: TradingViewInterval = 'D';
export const ANALYSIS_CHART_INTERVAL_KEY = 'analysis_chart_interval';

const APP_TIMEFRAME_TO_INTERVAL: Record<string, TradingViewInterval> = {
  '15m': '15',
  '1h': '60',
  '4h': '240',
  '1d': 'D',
  day: 'D',
  week: 'W',
  month: 'M',
  quarter: '3M',
  D: 'D',
  W: 'W',
  M: 'M',
  '3M': '3M',
};

const VALID_INTERVALS = new Set<TradingViewInterval>(['15', '60', '240', 'D', 'W', 'M', '3M']);

export function toTradingViewSymbol(symbol: string) {
  const normalized = String(symbol || 'BTC').trim().toUpperCase();
  if (!normalized) {
    return `${DEFAULT_TRADINGVIEW_EXCHANGE}:BTC${DEFAULT_TRADINGVIEW_QUOTE}`;
  }
  if (normalized.includes(':')) {
    return normalized;
  }
  if (normalized.endsWith(DEFAULT_TRADINGVIEW_QUOTE)) {
    return `${DEFAULT_TRADINGVIEW_EXCHANGE}:${normalized}`;
  }
  return `${DEFAULT_TRADINGVIEW_EXCHANGE}:${normalized}${DEFAULT_TRADINGVIEW_QUOTE}`;
}

export function normalizeTradingViewInterval(value: unknown): TradingViewInterval {
  const normalized = String(value ?? '').trim();
  if (VALID_INTERVALS.has(normalized as TradingViewInterval)) {
    return normalized as TradingViewInterval;
  }
  return APP_TIMEFRAME_TO_INTERVAL[normalized] ?? DEFAULT_TRADINGVIEW_INTERVAL;
}

export function toTradingViewInterval(value: string) {
  return normalizeTradingViewInterval(value);
}

export function toTradingViewTheme(appearance: 'system' | 'dark' | 'light'): TradingViewTheme {
  return appearance === 'light' ? 'light' : 'dark';
}

export function buildTradingViewEmbedConfig(options: {
  allowSymbolChange?: boolean;
  indicators?: string[];
  interval: string;
  symbol: string;
  theme: TradingViewTheme;
}) {
  return {
    autosize: true,
    symbol: options.symbol,
    interval: options.interval,
    timezone: 'Etc/UTC',
    theme: options.theme,
    style: '1',
    locale: 'en',
    hide_top_toolbar: false,
    hide_side_toolbar: true,
    allow_symbol_change: options.allowSymbolChange ?? false,
    save_image: false,
    calendar: false,
    support_host: 'https://www.tradingview.com',
    studies: options.indicators ?? [],
  };
}

export function buildTradingViewWidgetUrl(options: {
  interval: string;
  symbol: string;
  theme: TradingViewTheme;
}) {
  const params = new URLSearchParams({
    details: '1',
    hideideas: '1',
    hideideasbutton: '1',
    hidesidetoolbar: '1',
    interval: options.interval,
    locale: 'en',
    saveimage: '0',
    style: '1',
    symbol: options.symbol,
    symboledit: '0',
    theme: options.theme,
    timezone: 'Etc/UTC',
    withdateranges: '1',
  });

  return `https://s.tradingview.com/widgetembed/?${params.toString()}`;
}

export function parseTradingViewIntervalFromUrl(url: string) {
  if (!url) return null;
  try {
    const parsed = new URL(url);
    const interval = parsed.searchParams.get('interval');
    return interval ? normalizeTradingViewInterval(interval) : null;
  } catch {
    return null;
  }
}
