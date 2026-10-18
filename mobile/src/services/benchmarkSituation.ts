export type BenchmarkSituationId = 'heavy_pressure' | 'pressure' | 'no_direction' | 'gaining_strength' | 'strong';

// Keep these inclusive bands aligned with the web setup presets.
export function benchmarkSituationId(value: number | null | undefined): BenchmarkSituationId | null {
  if (value == null || !Number.isFinite(value) || value < 0 || value > 100) return null;
  const score = Math.round(value);
  if (score <= 25) return 'heavy_pressure';
  if (score <= 45) return 'pressure';
  if (score <= 60) return 'no_direction';
  if (score <= 75) return 'gaining_strength';
  return 'strong';
}
