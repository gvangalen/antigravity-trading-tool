// ==============================================================================
// Central Frontend Intelligence Semantics Helper (Single Source of Truth)
// ==============================================================================
import { useTranslation } from "@/app/providers/I18nProvider";

export function useIntelligenceSemantics() {
  const { locale } = useTranslation();
  const isDutch = String(locale).toLowerCase().startsWith("nl");
  const getMacroSemantics = (score) => {
    const val = score === null || score === undefined ? 50 : Number(score);
    const conviction = Math.round(val);

    if (val >= 70) {
      return {
        regime: isDutch ? "Expansieregime" : "Expansion regime",
        posture: isDutch ? "Agressieve groei" : "Aggressive growth",
        riskState: isDutch ? "Laag macrorisico" : "Minimal macro risk",
        conviction,
        explanation: isDutch
          ? "De markt toont sterke trendcontinuatie, gezonde liquiditeit en gunstige macro-economische condities."
          : "The market shows strong trend continuation, healthy liquidity, and favorable macroeconomic conditions.",
        badgeClass: "bg-emerald-50 text-emerald-700 border-emerald-200",
      };
    }
    if (val >= 45) {
      return {
        regime: isDutch ? "Herstelfase" : "Recovery phase",
        posture: isDutch ? "Constructieve alignering" : "Constructive alignment",
        riskState: isDutch ? "Beheerst risico" : "Controlled risk",
        conviction,
        explanation: isDutch
          ? "Macro-indicatoren stabiliseren na een correctie met toenemende kapitaalinstroom."
          : "Macro indicators are stabilizing after a correction with increasing capital inflows.",
        badgeClass: "bg-blue-50 text-blue-700 border-blue-200",
      };
    }
    if (val >= 30) {
      return {
        regime: isDutch ? "Stagflatierisico" : "Stagflation risk",
        posture: isDutch ? "Voorzichtige houding" : "Cautious stance",
        riskState: isDutch ? "Verhoogde onzekerheid" : "Elevated uncertainty",
        conviction,
        explanation: isDutch
          ? "Tegenstrijdige signalen in inflatie en rentebeleid vragen om een lagere handelsfrequentie."
          : "Conflicting inflation and rate-policy signals call for a lower trading frequency.",
        badgeClass: "bg-amber-50 text-amber-700 border-amber-200",
      };
    }
    return {
      regime: isDutch ? "Krimpregime" : "Contraction regime",
      posture: isDutch ? "Defensieve houding" : "Defensive posture",
      riskState: isDutch ? "Zware krimp" : "Severe contraction",
      conviction,
      explanation: isDutch
        ? "De macro-omgeving laat stevige liquiditeitskrimp zien. Positiegroottes worden automatisch afgeschaald (0,2x)."
        : "The macro environment shows severe liquidity contraction. Position sizing is automatically scaled down (0.2x).",
      badgeClass: "bg-rose-50 text-rose-700 border-rose-200",
    };
  };

  const getTechnicalSemantics = (score) => {
    const val = score === null || score === undefined ? 50 : Number(score);
    const conviction = Math.round(val);

    if (val >= 70) {
      return {
        structure: isDutch ? "Positieve expansie" : "Bullish expansion",
        conviction,
        momentum: isDutch ? "Sterk opwaarts momentum" : "Strong upward bias",
        explanation: isDutch
          ? "Prijsactie en voortschrijdende gemiddelden wijzen op krachtig institutioneel opwaarts momentum."
          : "Price action and moving averages point to strong institutional upside momentum.",
        badgeClass: "bg-emerald-50 text-emerald-700 border-emerald-200",
      };
    }
    if (val >= 50) {
      return {
        structure: isDutch ? "Positief herstel" : "Bullish recovery",
        conviction,
        momentum: isDutch ? "Positieve divergentie" : "Positive divergence",
        explanation: isDutch
          ? "De technische structuur herstelt van oversold-condities en bouwt hogere bodems op."
          : "Technical structure is recovering from oversold conditions and building higher lows.",
        badgeClass: "bg-blue-50 text-blue-700 border-blue-200",
      };
    }
    if (val >= 30) {
      return {
        structure: isDutch ? "Consolidatie" : "Consolidation",
        conviction,
        momentum: isDutch ? "Neutraal / zijwaarts" : "Neutral / sideways",
        explanation: isDutch
          ? "De prijs beweegt in een smalle bandbreedte zonder duidelijke richting. Een uitbraak wordt afgewacht."
          : "Price is moving in a tight range without clear direction. Waiting for a breakout.",
        badgeClass: "bg-slate-50 text-slate-700 border-slate-200",
      };
    }
    return {
      structure: isDutch ? "Negatieve structuur" : "Bearish structure",
      conviction,
      momentum: isDutch ? "Neerwaartse druk" : "Downward pressure",
      explanation: isDutch
        ? "Een dominante neerwaartse trend met zwakke koopkracht. Meer cash of defensieve positionering ligt meer voor de hand."
        : "A dominant downward trend with weak buying pressure. More cash or defensive positioning is more appropriate.",
      badgeClass: "bg-rose-50 text-rose-700 border-rose-200",
    };
  };

  const getMarketSemantics = (score) => {
    const val = score === null || score === undefined ? 50 : Number(score);
    const conviction = Math.round(val);

    if (val >= 70) {
      return {
        posture: isDutch ? "Kapitaalinstroom" : "Capital inflow",
        conviction,
        liquidity: isDutch ? "Sterke liquiditeit" : "Premium liquidity",
        explanation: isDutch
          ? "Hoge handelsvolumes en brede marktparticipatie bevestigen robuuste institutionele steun."
          : "High trading volumes and broad participation confirm robust institutional support.",
        badgeClass: "bg-emerald-50 text-emerald-700 border-emerald-200",
      };
    }
    if (val >= 50) {
      return {
        posture: isDutch ? "Stabiele participatie" : "Stable participation",
        conviction,
        liquidity: isDutch ? "Normaal volume" : "Standard volume",
        explanation: isDutch
          ? "Gemiddelde liquiditeit en orderboekdiepte ondersteunen reguliere DCA-uitvoering."
          : "Average liquidity and order book depth support regular DCA execution.",
        badgeClass: "bg-blue-50 text-blue-700 border-blue-200",
      };
    }
    if (val >= 30) {
      return {
        posture: isDutch ? "Liquiditeitsdivergentie" : "Liquidity divergence",
        conviction,
        liquidity: isDutch ? "Dunne orderboeken" : "Thin order books",
        explanation: isDutch
          ? "Afnemend volume en oplopende spreads duiden op afnemende institutionele interesse."
          : "Falling volume and widening spreads point to declining institutional interest.",
        badgeClass: "bg-amber-50 text-amber-700 border-amber-200",
      };
    }
    return {
      posture: isDutch ? "Risicomijding" : "Risk aversion",
      conviction,
      liquidity: isDutch ? "Kapitaalvlucht" : "Capital flight",
      explanation: isDutch
        ? "Er is kapitaalvlucht zichtbaar met verhoogde marktbrede volatiliteit en verkoopdruk."
        : "Capital flight is visible, with elevated market-wide volatility and selling pressure.",
      badgeClass: "bg-rose-50 text-rose-700 border-rose-200",
    };
  };

  return {
    getMacroSemantics,
    getTechnicalSemantics,
    getMarketSemantics,
  };
}
