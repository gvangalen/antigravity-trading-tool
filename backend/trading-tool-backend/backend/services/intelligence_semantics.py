# ==============================================================================
# Central Intelligence Semantics Service (Single Source of Truth)
# ==============================================================================
from typing import Dict, Any, Optional

def get_macro_semantics(score: Optional[float]) -> Dict[str, Any]:
    val = 50.0 if score is None else float(score)
    conviction = int(val)
    
    if val >= 70:
        return {
            "regime": "Expansion Regime",
            "posture": "Aggressive Growth",
            "risk_state": "Laag / Stabiel",
            "conviction": conviction,
            "explanation": "Markt toont sterke trendcontinuatie, gezonde liquiditeit en gunstige macro-economische condities."
        }
    elif val >= 45:
        return {
            "regime": "Recovery Phase",
            "posture": "Constructive Alignment",
            "risk_state": "Gematigd",
            "conviction": conviction,
            "explanation": "Macro-indicatoren stabiliseren na een correctie met toenemende kapitaalinstroom."
        }
    elif val >= 30:
        return {
            "regime": "Stagflation Risk",
            "posture": "Cautious Stance",
            "risk_state": "Risk Elevated",
            "conviction": conviction,
            "explanation": "Tegenstrijdige signalen in inflatie en rentebeleid vereisen een verlaagde handelsfrequentie."
        }
    else:
        return {
            "regime": "Contraction Regime",
            "posture": "Defensive Posture",
            "risk_state": "Severe Contraction",
            "conviction": conviction,
            "explanation": "Macro-omgeving vertoont zware liquiditeitskrimp. Positiegroottes worden automatisch afgeschaald (0.2x)."
        }

def get_technical_semantics(score: Optional[float]) -> Dict[str, Any]:
    val = 50.0 if score is None else float(score)
    conviction = int(val)
    
    if val >= 70:
        return {
            "structure": "Bullish Structure",
            "conviction": conviction,
            "momentum": "Strong Upward Bias",
            "explanation": "Prijsactie en voortschrijdende gemiddelden wijzen op krachtig institutioneel opwaarts momentum."
        }
    elif val >= 50:
        return {
            "structure": "Bullish Structure",
            "conviction": conviction,
            "momentum": "Positive Divergence",
            "explanation": "Technische structuur herstelt van oversold condities en bouwt hogere bodems op."
        }
    elif val >= 30:
        return {
            "structure": "Neutral Structure",
            "conviction": conviction,
            "momentum": "Neutral / Sideways",
            "explanation": "Prijs beweegt in een krappe bandbreedte zonder duidelijke richting. Uitbraak wordt afgewacht."
        }
    else:
        return {
            "structure": "Weak Structure",
            "conviction": conviction,
            "momentum": "Downward Pressure",
            "explanation": "Dominante neerwaartse trend met zwakke koopkracht. Short-posities of cash-allocatie aanbevolen."
        }

def get_market_semantics(score: Optional[float]) -> Dict[str, Any]:
    val = 50.0 if score is None else float(score)
    conviction = int(val)
    
    if val >= 70:
        return {
            "posture": "Momentum Rising",
            "conviction": conviction,
            "liquidity": "Premium Liquidity",
            "explanation": "Hoge handelsvolumes en brede marktparticipatie bevestigen robuuste institutionele steun."
        }
    elif val >= 50:
        return {
            "posture": "Compression",
            "conviction": conviction,
            "liquidity": "Standard Volume",
            "explanation": "Gemiddelde liquiditeit en orderboekdiepte ondersteunen reguliere DCA-uitvoering."
        }
    elif val >= 30:
        return {
            "posture": "Rangebound",
            "conviction": conviction,
            "liquidity": "Thin Orderbooks",
            "explanation": "Afnemend volume en oplopende spreads duiden op verminderde institutionele interesse."
        }
    else:
        return {
            "posture": "Expansion",
            "conviction": conviction,
            "liquidity": "Capital Flight",
            "explanation": "Kapitaalvlucht waargenomen met verhoogde marktbrede volatiliteit en verkoopdruk."
        }

def get_composite_intelligence(macro_sc: Optional[float], tech_sc: Optional[float], mkt_sc: Optional[float]) -> Dict[str, Any]:
    """
    Combineert de drie kernpijlers in één overkoepelend Chief of Staff oordeel.
    """
    macro = get_macro_semantics(macro_sc)
    tech = get_technical_semantics(tech_sc)
    mkt = get_market_semantics(mkt_sc)
    
    # Bepaal overarching posture
    m_val = 50.0 if macro_sc is None else float(macro_sc)
    t_val = 50.0 if tech_sc is None else float(tech_sc)
    
    if m_val < 35.0:
        status_badge = "DEFENSIVE OVERRIDE"
        chief_conclusion = "Macro contraction regime active. All automated strategy clusters restricted to 0.2x position sizing."
    elif t_val < 30.0:
        status_badge = "CAPITAL PRESERVATION"
        chief_conclusion = "Technical structure broken. Executing defensive DCA ranges and avoiding aggressive entries."
    elif m_val >= 70.0 and t_val >= 70.0:
        status_badge = "AGGRESSIVE EXPANSION"
        chief_conclusion = "Optimal macro and technical alignment. Maximizing position sizing and trend continuation setups."
    else:
        status_badge = "CONTROLLED EXECUTION"
        chief_conclusion = "Constructive market posture. Executing baseline portfolio strategies within standard risk limits."
        
    return {
        "macro": macro,
        "technical": tech,
        "market": mkt,
        "status_badge": status_badge,
        "chief_conclusion": chief_conclusion
    }
