// components/ui/scoreUtils.js

/**
 * Score kleur-logica — centrale UX waarheid
 *
 * Betekenis:
 * - ≥ 75  → sterk positief (groen)
 * - ≥ 60  → positief / voorzichtig (geel)
 * - ≥ 40  → neutraal (oranje)
 * - < 40  → negatief (rood)
 */
export function getScoreBarClass(score) {
  if (score >= 75) return "score-bar score-bar-strong-buy"; // groen
  if (score >= 60) return "score-bar score-bar-buy";        // geel
  if (score >= 40) return "score-bar score-bar-neutral";    // oranje
  return "score-bar score-bar-sell";                        // rood
}
