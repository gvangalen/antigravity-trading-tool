"""Render a simple owner-scoped trader profile read from typed evidence."""

from __future__ import annotations

from typing import Any


_FIELD_LABELS = {
    "nl": ("Traderstijl", "Tijdschalen", "Markten", "Doelen", "Ervaring", "Risicoprofiel", "Gedragspunten"),
    "en": ("Trading style", "Timeframes", "Markets", "Goals", "Experience", "Risk profile", "Behavior points"),
    "de": ("Tradingstil", "Zeitrahmen", "Märkte", "Ziele", "Erfahrung", "Risikoprofil", "Verhaltenspunkte"),
}
_FIELDS = (
    "trader_types", "primary_timeframes", "asset_focus", "investment_goals",
    "experience_levels", "risk_profiles", "behavior_flags",
)
_NL_VALUES = {
    "investor": "investeerder", "dca_investor": "DCA-investeerder", "swing_trader": "swing trader",
    "day_trader": "day trader", "scalper": "scalper", "hybrid": "hybride",
    "bitcoin": "Bitcoin", "crypto_general": "crypto algemeen", "stocks": "aandelen",
    "etfs": "ETF's", "forex": "forex", "commodities": "grondstoffen",
    "wealth_building": "vermogen opbouwen", "extra_income": "extra inkomen",
    "active_trading": "actief traden", "financial_independence": "financiële onafhankelijkheid",
    "retirement": "pensioen", "capital_preservation": "kapitaal behouden",
    "beginner": "beginner", "intermediate": "gemiddeld", "advanced": "gevorderd",
    "professional": "professioneel", "conservative": "conservatief",
    "balanced": "normaal", "aggressive": "agressief", "fomo": "FOMO / najagen",
    "takes_profit_too_early": "winst te vroeg nemen",
    "holds_losers_too_long": "verliezers te lang laten lopen",
    "overtrades": "overtraden", "leverage_seeking": "leverage opzoeken",
}
_DE_VALUES = {
    "investor": "Investor", "dca_investor": "DCA-Investor", "swing_trader": "Swing-Trader",
    "day_trader": "Daytrader", "scalper": "Scalper", "hybrid": "Hybrid",
    "bitcoin": "Bitcoin", "crypto_general": "Krypto allgemein", "stocks": "Aktien",
    "etfs": "ETFs", "forex": "Devisen", "commodities": "Rohstoffe",
    "wealth_building": "Vermögen aufbauen", "extra_income": "Zusatzeinkommen",
    "active_trading": "aktives Trading", "financial_independence": "finanzielle Unabhängigkeit",
    "retirement": "Altersvorsorge", "capital_preservation": "Kapital erhalten",
    "beginner": "Anfänger", "intermediate": "Fortgeschritten", "advanced": "Erfahren",
    "professional": "Professionell", "conservative": "konservativ",
    "balanced": "ausgewogen", "aggressive": "aggressiv", "fomo": "FOMO / Nachjagen",
    "takes_profit_too_early": "Gewinne zu früh mitnehmen",
    "holds_losers_too_long": "Verlustpositionen zu lange halten",
    "overtrades": "zu häufig handeln", "leverage_seeking": "Hebelwirkung suchen",
}


def _profile_follow_up(profile: dict[str, Any], language: str) -> str:
    """Ask for the next user choice using saved preferences, never infer suitability."""
    def choices(field: str) -> set[str]:
        values = profile.get(field)
        return {value for value in values if isinstance(value, str)} if isinstance(values, list) else set()

    styles = choices("trader_types")
    goals = choices("investment_goals")
    behaviors = choices("behavior_flags")
    assets = choices("asset_focus")
    long_term = bool(styles & {"investor", "dca_investor"} or goals & {
        "wealth_building", "financial_independence", "retirement",
    })
    active = bool(styles & {"swing_trader", "day_trader", "scalper"} or "active_trading" in goals)
    market = {
        "nl": "Bitcoin" if assets == {"bitcoin"} else "je gekozen markt",
        "en": "Bitcoin" if assets == {"bitcoin"} else "your chosen market",
        "de": "Bitcoin" if assets == {"bitcoin"} else "deinen gewählten Markt",
    }[language]
    if long_term and active:
        return {
            "nl": f"Je profiel noemt zowel opbouwen als actief traden. Wil je voor {market} eerst een opbouwplan of een actieve setup verkennen?",
            "en": f"Your profile mentions both building wealth and active trading. Would you like to explore a long-term plan or an active setup for {market} first?",
            "de": f"Dein Profil nennt sowohl Vermögensaufbau als auch aktives Trading. Möchtest du für {market} zuerst einen langfristigen Plan oder ein aktives Setup besprechen?",
        }[language]
    if "fomo" in behaviors:
        return {
            "nl": "Je noemt FOMO als aandachtspunt. Wil je bespreken welke instapregel je vooraf wilt vastleggen voor een volgend plan?",
            "en": "You mention FOMO as a concern. Would you like to discuss an entry rule to set in advance for your next plan?",
            "de": "Du nennst FOMO als Thema. Möchtest du eine Einstiegsregel besprechen, die du vor deinem nächsten Plan festlegst?",
        }[language]
    if "overtrades" in behaviors:
        return {
            "nl": "Je noemt overtraden als aandachtspunt. Wil je bespreken welke grens je vooraf wilt instellen voor het aantal trades?",
            "en": "You mention overtrading as a concern. Would you like to discuss a limit to set in advance for the number of trades?",
            "de": "Du nennst zu häufiges Handeln als Thema. Möchtest du eine vorher festgelegte Grenze für die Anzahl der Trades besprechen?",
        }[language]
    if "leverage_seeking" in behaviors:
        return {
            "nl": "Je noemt leverage als aandachtspunt. Wil je bespreken welke risicogrens je zelf voor een volgend voorstel wilt aanhouden?",
            "en": "You mention leverage as a concern. Would you like to discuss a risk limit you want to set for your next proposal?",
            "de": "Du nennst Hebelwirkung als Thema. Möchtest du eine Risikogrenze besprechen, die du für deinen nächsten Vorschlag festlegen willst?",
        }[language]
    if long_term:
        return {
            "nl": f"Welke termijn en welk doel wil je voor {market} als eerste uitwerken?",
            "en": f"Which time horizon and goal would you like to work out for {market} first?",
            "de": f"Welchen Zeithorizont und welches Ziel möchtest du für {market} zuerst ausarbeiten?",
        }[language]
    if active:
        return {
            "nl": f"Wil je voor {market} een concrete setup verkennen?",
            "en": f"Would you like to explore a setup for {market}?",
            "de": f"Möchtest du für {market} ein Setup besprechen?",
        }[language]
    return {
        "nl": "Wat wil je met dit profiel als eerste uitwerken: een plan, een setup of een botvoorstel?",
        "en": "What would you like to work on first with this profile: a plan, a setup, or a bot proposal?",
        "de": "Was möchtest du mit diesem Profil zuerst ausarbeiten: einen Plan, ein Setup oder einen Bot-Vorschlag?",
    }[language]


def render_profile_readback(data: dict[str, Any], *, locale: str = "nl") -> str:
    """State saved choices only; they do not establish suitability or advice."""
    language = locale.replace("_", "-").split("-", 1)[0].lower()
    if language not in _FIELD_LABELS:
        language = "nl"
    if data.get("has_profile") is not True:
        return {
            "nl": "Ik kan je opgeslagen traderprofiel lezen, maar er zijn nog geen profielkeuzes ingevuld.",
            "en": "I can read your saved trader profile, but no profile choices have been filled in yet.",
            "de": "Ich kann dein gespeichertes Traderprofil lesen, aber es enthält noch keine Profilauswahl.",
        }[language]

    profile = data.get("trader_profile")
    profile = profile if isinstance(profile, dict) else {}
    labels = _FIELD_LABELS[language]
    value_labels = {"nl": _NL_VALUES, "de": _DE_VALUES}.get(language, {})
    details = []
    for field, label in zip(_FIELDS, labels):
        values = profile.get(field) or []
        if not isinstance(values, list):
            continue
        displayed = [
            value_labels.get(value, value.replace("_", " "))
            for value in values if isinstance(value, str) and value
        ]
        if displayed:
            details.append(f"{label}: {', '.join(displayed)}")
    context = data.get("trader_context")
    if isinstance(context, str) and context.strip():
        details.append({"nl": "Eigen toelichting", "en": "Your note", "de": "Deine Notiz"}[language]
                       + f": {context.strip()[:1000]}")
    prefix = {
        "nl": "Dit staat in je opgeslagen traderprofiel:",
        "en": "Your saved trader profile contains:",
        "de": "In deinem gespeicherten Traderprofil steht:",
    }[language]
    boundary = {
        "nl": "Dit zijn je ingevulde voorkeuren; ze bewijzen niet dat een specifieke trade bij je past.",
        "en": "These are your saved preferences; they do not show that a particular trade suits you.",
        "de": "Das sind deine gespeicherten Präferenzen; sie belegen nicht, dass ein bestimmter Trade zu dir passt.",
    }[language]
    follow_up = _profile_follow_up(profile, language)
    return f"{prefix}\n" + "\n".join(f"• {detail}" for detail in details) + f"\n\n{boundary}\n\n{follow_up}"
