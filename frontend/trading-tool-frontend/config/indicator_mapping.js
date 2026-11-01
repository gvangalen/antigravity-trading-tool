// TradingView studies are visual aids. Score 2.0 continues to use its own
// pair-scoped source readings and scoring rules.
const STUDIES = Object.freeze({
  rsi: { id: "RSI@tv-basicstudies", label: "RSI" },
  ma_50: { id: "MASimple@tv-basicstudies", inputs: { length: 50 }, label: "MA 50" },
  ma_200: { id: "MASimple@tv-basicstudies", inputs: { length: 200 }, label: "MA 200" },
  ema_20_gap_pct: { id: "MAExp@tv-basicstudies", inputs: { length: 20 }, label: "EMA 20" },
  ema_50_gap_pct: { id: "MAExp@tv-basicstudies", inputs: { length: 50 }, label: "EMA 50" },
  macd_hist_pct: { id: "MACD@tv-basicstudies", label: "MACD" },
  atr_pct: { id: "ATR@tv-basicstudies", label: "ATR" },
  adx: { id: "ADX@tv-basicstudies", label: "ADX" },
});

export function mapTechnicalToStudies(indicatorList = []) {
  const seen = new Set();
  return (Array.isArray(indicatorList) ? indicatorList : []).flatMap((item) => {
    const name = String(typeof item === "string" ? item : item?.name || item?.indicator || "")
      .trim().toLowerCase();
    if (!STUDIES[name] || seen.has(name)) return [];
    seen.add(name);
    const { label, ...study } = STUDIES[name];
    return [{ ...study, name, label }];
  });
}
