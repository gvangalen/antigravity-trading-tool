/**
 * 🗺️ TRADINGVIEW INDICATOR MAPPING
 * Koppelt database-indicatornamen aan TradingView Study IDs.
 * Gebruik: 'StudyName@tv-basicstudies'
 * 
 * NOTE: Voor MA/EMA moet je vaak 'MAExp@tv-basicstudies' gebruiken en dan 
 * de settings aanpassen, maar als baseline laden we de core studies.
 */
export const INDICATOR_MAP = {
  // Oscillators
  "rsi": "RSI@tv-basicstudies",
  "macd": "MACD@tv-basicstudies",
  "stochastic": "Stochastic@tv-basicstudies",
  "cci": "CCI@tv-basicstudies",
  
  // Volatility & Volume
  "vix": "VIX@tv-basicstudies",
  "volatility_index_(vix)": "VIX@tv-basicstudies",
  "bollinger_bands": "BB@tv-basicstudies",
  "volume": "Volume@tv-basicstudies",
  "atr": "ATR@tv-basicstudies",
  "atr_pct": "ATR@tv-basicstudies",
  "adx": "ADX@tv-basicstudies",

  // Averages & Trends (Mapping defaults)
  "ma_200": "MASimple@tv-basicstudies",
  "ma_50": "MASimple@tv-basicstudies",
  "ema_20": "MAExp@tv-basicstudies",
  "ema_50": "MAExp@tv-basicstudies",
  "ema_20_gap_pct": "MAExp@tv-basicstudies",
  "ema_50_gap_pct": "MAExp@tv-basicstudies",
  "macd_hist_pct": "MACD@tv-basicstudies",
  "supertrend": "SuperTrend@tv-basicstudies",
  "vwap": "VWAP@tv-basicstudies",
};

export const mapTechnicalToStudies = (indicatorList = []) => {
  if (!Array.isArray(indicatorList)) return [];
  
  return indicatorList
    .map(name => {
      const key = name.toLowerCase().replace(/ /g, "_");
      return INDICATOR_MAP[key];
    })
    .filter(Boolean);
};
