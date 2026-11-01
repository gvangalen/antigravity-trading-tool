/** Visual chart studies calculated from the exact market candles, not Score 2.0. */
export function rsiSeries(candles, length = 14) {
  if (!Array.isArray(candles) || candles.length <= length) return [];
  let gains = 0;
  let losses = 0;
  const output = [];
  const value = (gain, loss) => loss === 0 ? (gain === 0 ? 50 : 100) : 100 - 100 / (1 + gain / loss);
  for (let index = 1; index < candles.length; index += 1) {
    const change = candles[index].close - candles[index - 1].close;
    const gain = Math.max(change, 0);
    const loss = Math.max(-change, 0);
    if (index <= length) {
      gains += gain;
      losses += loss;
      if (index === length) {
        gains /= length;
        losses /= length;
        output.push({ time: candles[index].time, value: value(gains, losses) });
      }
    } else {
      gains = (gains * (length - 1) + gain) / length;
      losses = (losses * (length - 1) + loss) / length;
      output.push({ time: candles[index].time, value: value(gains, losses) });
    }
  }
  return output;
}

export function movingAverageSeries(candles, length, exponential = false) {
  if (!Array.isArray(candles) || candles.length < length) return [];
  let average = 0;
  const output = [];
  const alpha = 2 / (length + 1);
  for (let index = 0; index < candles.length; index += 1) {
    if (index < length) average += candles[index].close / length;
    else if (exponential) average += alpha * (candles[index].close - average);
    else average += (candles[index].close - candles[index - length].close) / length;
    if (index >= length - 1) output.push({ time: candles[index].time, value: average });
  }
  return output;
}
