// ==============================================================================
// Central Frontend Intelligence Semantics Helper (Single Source of Truth)
// ==============================================================================

export function useIntelligenceSemantics() {
  const getMacroSemantics = (score) => {
    const val = score === null || score === undefined ? 50 : Number(score);
    const conviction = Math.round(val);

    if (val >= 70) {
      return {
        regime: "Expansion Regime",
        posture: "Aggressive Growth",
        riskState: "Minimal Macro Risk",
        conviction,
        explanation: "Markt toont sterke trendcontinuatie, gezonde liquiditeit en gunstige macro-economische condities.",
        badgeClass: "bg-emerald-50 text-emerald-700 border-emerald-200",
      };
    }
    if (val >= 45) {
      return {
        regime: "Recovery Phase",
        posture: "Constructive Alignment",
        riskState: "Controlled Risk",
        conviction,
        explanation: "Macro-indicatoren stabiliseren na een correctie met toenemende kapitaalinstroom.",
        badgeClass: "bg-blue-50 text-blue-700 border-blue-200",
      };
    }
    if (val >= 30) {
      return {
        regime: "Stagflation Risk",
        posture: "Cautious Stance",
        riskState: "Elevated Uncertainty",
        conviction,
        explanation: "Tegenstrijdige signalen in inflatie en rentebeleid vereisen een verlaagde handelsfrequentie.",
        badgeClass: "bg-amber-50 text-amber-700 border-amber-200",
      };
    }
    return {
      regime: "Contraction Regime",
      posture: "Defensive Posture",
      riskState: "Severe Contraction",
      conviction,
      explanation: "Macro-omgeving vertoont zware liquiditeitskrimp. Positiegroottes worden automatisch afgeschaald (0.2x).",
      badgeClass: "bg-rose-50 text-rose-700 border-rose-200",
    };
  };

  const getTechnicalSemantics = (score) => {
    const val = score === null || score === undefined ? 50 : Number(score);
    const conviction = Math.round(val);

    if (val >= 70) {
      return {
        structure: "Bullish Expansion",
        conviction,
        momentum: "Strong Upward Bias",
        explanation: "Prijsactie en voortschrijdende gemiddelden wijzen op krachtig institutioneel opwaarts momentum.",
        badgeClass: "bg-emerald-50 text-emerald-700 border-emerald-200",
      };
    }
    if (val >= 50) {
      return {
        structure: "Bullish Recovery",
        conviction,
        momentum: "Positive Divergence",
        explanation: "Technische structuur herstelt van oversold condities en bouwt hogere bodems op.",
        badgeClass: "bg-blue-50 text-blue-700 border-blue-200",
      };
    }
    if (val >= 30) {
      return {
        structure: "Consolidation",
        conviction,
        momentum: "Neutral / Sideways",
        explanation: "Prijs beweegt in een krappe bandbreedte zonder duidelijke richting. Uitbraak wordt afgewacht.",
        badgeClass: "bg-slate-50 text-slate-700 border-slate-200",
      };
    }
    return {
      structure: "Bearish Structure",
      conviction,
      momentum: "Downward Pressure",
      explanation: "Dominante neerwaartse trend met zwakke koopkracht. Short-posities of cash-allocatie aanbevolen.",
      badgeClass: "bg-rose-50 text-rose-700 border-rose-200",
    };
  };

  const getMarketSemantics = (score) => {
    const val = score === null || score === undefined ? 50 : Number(score);
    const conviction = Math.round(val);

    if (val >= 70) {
      return {
        posture: "Capital Inflow",
        conviction,
        liquidity: "Premium Liquidity",
        explanation: "Hoge handelsvolumes en brede marktparticipatie bevestigen robuuste institutionele steun.",
        badgeClass: "bg-emerald-50 text-emerald-700 border-emerald-200",
      };
    }
    if (val >= 50) {
      return {
        posture: "Stable Participation",
        conviction,
        liquidity: "Standard Volume",
        explanation: "Gemiddelde liquiditeit en orderboekdiepte ondersteunen reguliere DCA-uitvoering.",
        badgeClass: "bg-blue-50 text-blue-700 border-blue-200",
      };
    }
    if (val >= 30) {
      return {
        posture: "Liquidity Divergence",
        conviction,
        liquidity: "Thin Orderbooks",
        explanation: "Afnemend volume en oplopende spreads duiden op verminderde institutionele interesse.",
        badgeClass: "bg-amber-50 text-amber-700 border-amber-200",
      };
    }
    return {
      posture: "Risk Aversion",
      conviction,
      liquidity: "Capital Flight",
      explanation: "Kapitaalvlucht waargenomen met verhoogde marktbrede volatiliteit en verkoopdruk.",
      badgeClass: "bg-rose-50 text-rose-700 border-rose-200",
    };
  };

  return {
    getMacroSemantics,
    getTechnicalSemantics,
    getMarketSemantics,
  };
}
