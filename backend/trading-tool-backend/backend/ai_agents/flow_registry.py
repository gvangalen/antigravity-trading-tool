# =====================================================
# TRADAMIND AI ASSISTANT - FLOW REGISTRY
# =====================================================
from typing import Dict, Any, List, Optional

FLOW_DEFINITIONS: Dict[str, Dict[str, Any]] = {
    "user_onboarding": {
        "page": "/profile",
        "assistant_role": "Onboarding Coach",
        "required_slots": ["experience_level", "risk_profile", "investment_goals"],
        "question_sequence": [
            {
                "slot": "experience_level",
                "question_beginner": "Hoi! Laten we je ervaring personaliseren. Hoeveel ervaring heb je al met crypto-trading? (kies uit: beginner, intermediate, advanced)",
                "question_advanced": "Wat is je crypto-trading ervaring? (beginner / intermediate / advanced):"
            },
            {
                "slot": "risk_profile",
                "question_beginner": "En hoe ga je om met risico? Ben je heel voorzichtig (conservative), zoek je een gezonde balans (balanced), of ga je voor maximale winst met hogere risico's (aggressive)?",
                "question_advanced": "Risicoprofiel? (conservative / balanced / aggressive):"
            },
            {
                "slot": "investment_goals",
                "question_beginner": "Als laatste: wat is je belangrijkste doel op Tradamind? Bijvoorbeeld 'wekelijks passief bijkopen' of 'actief traden op daggrafieken'?",
                "question_advanced": "Wat zijn je primaire investeringsdoelen?"
            }
        ],
        "draft_type": None,
        "allowed_actions": ["navigate_to_page"],
        "suggested_next_actions": [
            {
                "label": "Ga naar Overview",
                "query": "ga naar dashboard",
                "page_link": "/dashboard"
            }
        ]
    },
    "setup_creation": {
        "page": "/setup",
        "assistant_role": "Setup Wizard",
        "required_slots": ["symbol", "setup_type", "timeframe", "name"],
        "conditional_slots": {
            "dca_frequency": {
                "depends_on": "setup_type",
                "equals_value": "dca"
            },
            "dca_day": {
                "depends_on": "dca_frequency",
                "equals_value": "weekly"
            },
            "dca_month_day": {
                "depends_on": "dca_frequency",
                "equals_value": "monthly"
            }
        },
        "question_sequence": [
            {
                "slot": "symbol",
                "question_beginner": "Welke asset?",
                "question_advanced": "Welke asset?"
            },
            {
                "slot": "setup_type",
                "question_beginner": "Wil je een DCA of een actieve Trade setup maken?",
                "question_advanced": "DCA of trade?"
            },
            {
                "slot": "timeframe",
                "question_beginner": "Welke timeframe wil je voor deze setup gebruiken? Voor DCA is 1W of 1M logisch; voor een trade bijvoorbeeld 4H of 1D.",
                "question_advanced": "Welke timeframe hoort bij deze setup?"
            },
            {
                "slot": "name",
                "question_beginner": "Welke naam wil je aan deze setup geven?",
                "question_advanced": "Wat is de naam van deze setup?"
            },
            {
                "slot": "dca_frequency",
                "question_beginner": "Hoe vaak wil je bijkopen? (dagelijks, wekelijks of maandelijks)",
                "question_advanced": "Frequentie?"
            },
            {
                "slot": "dca_day",
                "question_beginner": "Op welke dag wil je bijkopen? (bijvoorbeeld maandag)",
                "question_advanced": "Welke weekdag?"
            },
            {
                "slot": "dca_month_day",
                "question_beginner": "Op welke dag van de maand wil je bijkopen? (bijvoorbeeld 1, 5 of 28)",
                "question_advanced": "Welke maanddag?"
            },
            {
                "slot": "market_condition",
                "question_beginner": "In welke marktconditie wil je vooral instappen? Kies bijvoorbeeld: bevestigd sterk, normale pullback, of vroege dip.",
                "question_advanced": "Welke marktconditie wil je voor deze setup gebruiken?"
            }
        ],
        "draft_type": "setup",
        "allowed_actions": ["open_setup_page"],
        "suggested_next_actions": [
            {
                "label": "Ontwerp Strategie",
                "query": "ontwerp een strategie voor deze setup",
                "page_link": "/strategy"
            }
        ]
    },
    "strategy_creation": {
        "page": "/strategy",
        "assistant_role": "Strategie Architect",
        "required_slots": ["setup_id", "base_amount"],
        "conditional_slots": {
            "entry": {
                "depends_on": "setup_type",
                "equals_value": "trade"
            },
            "targets": {
                "depends_on": "setup_type",
                "equals_value": "trade"
            },
            "stop_loss": {
                "depends_on": "setup_type",
                "equals_value": "trade"
            }
        },
        "question_sequence": [
            {
                "slot": "setup_id",
                "question_beginner": "Voor welke setup wil je deze strategie maken?",
                "question_advanced": "Voor welke setup wil je deze strategie maken?"
            },
            {
                "slot": "base_amount",
                "question_beginner": "Met welk basisbedrag in euro wil je deze strategie uitvoeren?",
                "question_advanced": "Met welk basisbedrag in euro wil je deze strategie uitvoeren?"
            },
            {
                "slot": "entry",
                "question_beginner": "Welke entry hoort bij deze trade-strategie?",
                "question_advanced": "Welke entry hoort bij deze trade-strategie?"
            },
            {
                "slot": "targets",
                "question_beginner": "Welke target(s) wil je gebruiken?",
                "question_advanced": "Welke target(s) wil je gebruiken?"
            },
            {
                "slot": "stop_loss",
                "question_beginner": "Welke stop-loss wil je gebruiken?",
                "question_advanced": "Welke stop-loss wil je gebruiken?"
            }
        ],
        "draft_type": "strategy",
        "allowed_actions": ["generate_strategy"],
        "suggested_next_actions": [
            {
                "label": "Start een Bot",
                "query": "start een trading bot voor deze strategie",
                "page_link": "/bot"
            }
        ]
    },
    "bot_creation": {
        "page": "/bot",
        "assistant_role": "Bot Deployer",
        "required_slots": ["name", "budget_total_eur", "budget_daily_limit_eur"],
        "question_sequence": [
            {
                "slot": "name",
                "question_beginner": "Bot naam?",
                "question_advanced": "Bot naam?"
            },
            {
                "slot": "budget_total_eur",
                "question_beginner": "Totaal budget?",
                "question_advanced": "Totaal budget?"
            },
            {
                "slot": "budget_daily_limit_eur",
                "question_beginner": "Dagelijks limiet budget?",
                "question_advanced": "Dagelijks limiet?"
            }
        ],
        "draft_type": "bot",
        "allowed_actions": ["open_bot_draft"],
        "suggested_next_actions": [
            {
                "label": "Ga naar Overview",
                "query": "ga naar dashboard",
                "page_link": "/dashboard"
            }
        ]
    },
    "macro_analysis_walkthrough": {
        "page": "/macro",
        "assistant_role": "Macro Analist",
        "required_slots": ["symbol"],
        "question_sequence": [
            {
                "slot": "symbol",
                "question_beginner": "Voor welke munt wil je de macro-economische analyse doorlopen?",
                "question_advanced": "Macro walkthrough asset ticker:"
            }
        ],
        "draft_type": None,
        "allowed_actions": ["navigate_to_page"],
        "suggested_next_actions": [
            {
                "label": "Check Technics",
                "query": "bekijk de technische analyse",
                "page_link": "/technical"
            }
        ]
    },
    "technical_analysis_walkthrough": {
        "page": "/technical",
        "assistant_role": "Technische Gids",
        "required_slots": ["symbol"],
        "question_sequence": [
            {
                "slot": "symbol",
                "question_beginner": "Voor welke munt wil je de technische indicatoren doornemen?",
                "question_advanced": "Technical walkthrough asset ticker:"
            }
        ],
        "draft_type": None,
        "allowed_actions": ["navigate_to_page"],
        "suggested_next_actions": [
            {
                "label": "Maak een Setup",
                "query": "maak een setup",
                "page_link": "/setup"
            }
        ]
    },
    "portfolio_review": {
        "page": "/portfolio",
        "assistant_role": "Risico Adviseur",
        "required_slots": [],
        "question_sequence": [],
        "draft_type": None,
        "allowed_actions": ["navigate_to_page"],
        "suggested_next_actions": [
            {
                "label": "Markt bekijken",
                "query": "laat me de markt zien",
                "page_link": "/market"
            }
        ]
    },
    "report_walkthrough": {
        "page": "/report",
        "assistant_role": "Performance Coach",
        "required_slots": [],
        "question_sequence": [],
        "draft_type": None,
        "allowed_actions": ["navigate_to_page"],
        "suggested_next_actions": [
            {
                "label": "Pas Strategie aan",
                "query": "pas mijn actieve strategie aan",
                "page_link": "/strategy"
            }
        ]
    },
    "risk_check": {
        "page": "/portfolio",
        "assistant_role": "Risico Adviseur",
        "required_slots": ["symbol", "proposed_size"],
        "question_sequence": [
            {
                "slot": "symbol",
                "question_beginner": "Over welke munt wil je de risicocontrole uitvoeren?",
                "question_advanced": "Asset ticker:"
            },
            {
                "slot": "proposed_size",
                "question_beginner": "Wat is de voorgestelde ordergrootte in EUR?",
                "question_advanced": "Order size (EUR):"
            }
        ],
        "draft_type": None,
        "allowed_actions": ["navigate_to_page"],
        "suggested_next_actions": [
            {
                "label": "Bekijk Portfolio",
                "query": "toon mijn portfolio",
                "page_link": "/portfolio"
            }
        ]
    },
    "navigate_to_page": {
        "page": "/dashboard",
        "assistant_role": "Centraal Kompas",
        "required_slots": ["target_page"],
        "question_sequence": [
            {
                "slot": "target_page",
                "question_beginner": "Naar welke pagina wil je navigeren?",
                "question_advanced": "Bestemmingspagina:"
            }
        ],
        "draft_type": None,
        "allowed_actions": ["navigate_to_page"],
        "suggested_next_actions": []
    }
}
