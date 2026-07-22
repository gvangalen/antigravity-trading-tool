// ==============================================================================
// Central Frontend Intelligence Semantics Helper (Single Source of Truth)
// ==============================================================================
import { useTranslation } from "@/app/providers/I18nProvider";

export function useIntelligenceSemantics() {
  const { t } = useTranslation();
  const semanticsT = t?.dashboard?.intelligenceSemantics || {};
  const toValidScore = (score) => {
    if (score === null || score === undefined || score === "") return null;
    const value = Number(score);
    return Number.isFinite(value) ? value : null;
  };
  const getMacroSemantics = (score) => {
    const val = toValidScore(score);
    if (val === null) return null;
    const conviction = Math.round(val);

    if (val >= 70) {
      return {
        regime: semanticsT?.macro?.expansion?.regime,
        posture: semanticsT?.macro?.expansion?.posture,
        riskState: semanticsT?.macro?.expansion?.riskState,
        conviction,
        explanation: semanticsT?.macro?.expansion?.explanation,
        badgeClass: "bg-emerald-50 text-emerald-700 border-emerald-200",
      };
    }
    if (val >= 45) {
      return {
        regime: semanticsT?.macro?.recovery?.regime,
        posture: semanticsT?.macro?.recovery?.posture,
        riskState: semanticsT?.macro?.recovery?.riskState,
        conviction,
        explanation: semanticsT?.macro?.recovery?.explanation,
        badgeClass: "bg-blue-50 text-blue-700 border-blue-200",
      };
    }
    if (val >= 30) {
      return {
        regime: semanticsT?.macro?.stagflation?.regime,
        posture: semanticsT?.macro?.stagflation?.posture,
        riskState: semanticsT?.macro?.stagflation?.riskState,
        conviction,
        explanation: semanticsT?.macro?.stagflation?.explanation,
        badgeClass: "bg-amber-50 text-amber-700 border-amber-200",
      };
    }
    return {
      regime: semanticsT?.macro?.contraction?.regime,
      posture: semanticsT?.macro?.contraction?.posture,
      riskState: semanticsT?.macro?.contraction?.riskState,
      conviction,
      explanation: semanticsT?.macro?.contraction?.explanation,
      badgeClass: "bg-rose-50 text-rose-700 border-rose-200",
    };
  };

  const getTechnicalSemantics = (score) => {
    const val = toValidScore(score);
    if (val === null) return null;
    const conviction = Math.round(val);

    if (val >= 70) {
      return {
        structure: semanticsT?.technical?.strong?.structure,
        conviction,
        momentum: semanticsT?.technical?.strong?.momentum,
        explanation: semanticsT?.technical?.strong?.explanation,
        badgeClass: "bg-emerald-50 text-emerald-700 border-emerald-200",
      };
    }
    if (val >= 50) {
      return {
        structure: semanticsT?.technical?.recovery?.structure,
        conviction,
        momentum: semanticsT?.technical?.recovery?.momentum,
        explanation: semanticsT?.technical?.recovery?.explanation,
        badgeClass: "bg-blue-50 text-blue-700 border-blue-200",
      };
    }
    if (val >= 30) {
      return {
        structure: semanticsT?.technical?.neutral?.structure,
        conviction,
        momentum: semanticsT?.technical?.neutral?.momentum,
        explanation: semanticsT?.technical?.neutral?.explanation,
        badgeClass: "bg-slate-50 text-slate-700 border-slate-200",
      };
    }
    return {
      structure: semanticsT?.technical?.weak?.structure,
      conviction,
      momentum: semanticsT?.technical?.weak?.momentum,
      explanation: semanticsT?.technical?.weak?.explanation,
      badgeClass: "bg-rose-50 text-rose-700 border-rose-200",
    };
  };

  const getMarketSemantics = (score) => {
    const val = toValidScore(score);
    if (val === null) return null;
    const conviction = Math.round(val);

    if (val >= 70) {
      return {
        posture: semanticsT?.market?.strong?.posture,
        conviction,
        liquidity: semanticsT?.market?.strong?.liquidity,
        explanation: semanticsT?.market?.strong?.explanation,
        badgeClass: "bg-emerald-50 text-emerald-700 border-emerald-200",
      };
    }
    if (val >= 50) {
      return {
        posture: semanticsT?.market?.recovery?.posture,
        conviction,
        liquidity: semanticsT?.market?.recovery?.liquidity,
        explanation: semanticsT?.market?.recovery?.explanation,
        badgeClass: "bg-blue-50 text-blue-700 border-blue-200",
      };
    }
    if (val >= 30) {
      return {
        posture: semanticsT?.market?.cautious?.posture,
        conviction,
        liquidity: semanticsT?.market?.cautious?.liquidity,
        explanation: semanticsT?.market?.cautious?.explanation,
        badgeClass: "bg-amber-50 text-amber-700 border-amber-200",
      };
    }
    return {
      posture: semanticsT?.market?.defensive?.posture,
      conviction,
      liquidity: semanticsT?.market?.defensive?.liquidity,
      explanation: semanticsT?.market?.defensive?.explanation,
      badgeClass: "bg-rose-50 text-rose-700 border-rose-200",
    };
  };

  return {
    getMacroSemantics,
    getTechnicalSemantics,
    getMarketSemantics,
  };
}
