import pytest

from backend.services.finn_v2_domain_requirement_service import FinnV2DomainRequirementService
from backend.services.finn_v2_request_analysis_service import FinnV2RequestAnalysisService
from backend.services.finn_v2_tool_plan_service import FinnV2ToolPlanService


ANALYSIS = FinnV2RequestAnalysisService()
DOMAINS = FinnV2DomainRequirementService()
TOOLS = FinnV2ToolPlanService()


GOLDEN_FAMILIES = [
    ("CAPABILITY", None, ["Hoi FINN, wat kun je voor mij doen?", "Waarmee help je mij?", "Wat doet FINN?", "Hoe kun je mij helpen?", "What can FINN do for me?"], []),
    ("READ", "read_asset", ["Welke asset heb ik actief?", "Wat is mijn actieve asset?", "Toon mijn gekozen asset.", "Welke coin of aandeel volg ik nu?", "Laat mijn huidige instrument zien."], ["asset"]),
    ("READ", "read_setup", ["Welke setup is actief?", "Toon mijn actieve setup.", "Wat is mijn huidige BTC setup?", "Welke setup gebruik ik?", "Op welk timeframe draait mijn setup?"], ["asset", "setup"]),
    ("READ", "read_indicators", ["Welke indicatoren zijn ingesteld?", "Toon mijn indicatorconfiguratie.", "Welke signalen gebruik ik?", "Hoe zijn mijn indicatoren geconfigureerd?", "Welke volume- en trendindicatoren volg ik?"], ["asset", "indicators"]),
    ("READ", None, ["Welke strategie gebruikt mijn bot?", "Aan welke strategie is mijn bot gekoppeld?", "Toon mijn strategie en bot.", "Wat is mijn actieve plan en welke bot hoort daarbij?", "Welke bot hoort bij deze setup?"], ["asset", "setup", "strategy", "bot", "bot_status"]),
    ("EVALUATE", "evaluate_complete_plan", ["Bekijk mijn hele plan en noem het zwakste punt.", "Waar wringt mijn plan?", "Wat ontbreekt er nog in mijn plan?", "Beoordeel mijn profiel, indicatoren, setup, strategie en bot.", "Welke voorwaarde ontbreekt voordat ik dit plan kan vertrouwen?"], ["profile", "indicators", "setup", "strategy", "bot", "bot_status"]),
    ("EVALUATE", None, ["Past mijn strategie bij mijn risicoprofiel?", "Is mijn strategie een goede fit voor mijn tradingstijl?", "Waar zit het risico in mijn plan?", "Beoordeel het vertrouwen in mijn bot.", "Welke indicator weegt het zwaarst in mijn plan?"], []),
    ("CREATE_PROPOSAL", "propose_setup", ["Maak een setup voor BTC swing trading.", "Stel een BTC setup voor.", "Bereid een nieuwe setup voor, nog niet opslaan.", "Welk setupconcept past bij mijn plan?", "Create a setup proposal for BTC."], ["profile", "asset", "indicators", "setup", "strategy"]),
    ("ACTION_PROPOSAL", "propose_watchlist_change", ["Voeg ETH toe aan mijn watchlist.", "Zet ETH op mijn volglijst.", "Add ETH to my watchlist.", "Ik wil ETH toevoegen aan de watchlist.", "Maak een voorstel om ETH te volgen."], ["asset", "watchlist"]),
    ("ACTION_PROPOSAL", None, ["Activeer deze bot live.", "Zet mijn bot live.", "Maak deze bot live.", "Activate my bot live.", "Start live trading met deze bot."], ["asset", "setup", "strategy", "bot", "bot_status", "market_snapshot"]),
]


@pytest.mark.parametrize("mode,goal,messages,required_scopes", GOLDEN_FAMILIES)
def test_btc_golden_paraphrases_keep_a_canonical_request_contract(mode, goal, messages, required_scopes):
    for index, message in enumerate(messages):
        analysis = ANALYSIS.analyze(message=message)
        assert analysis.interaction_mode == mode
        assert analysis.request_plan is not None
        assert analysis.request_plan.interaction_mode == mode
        if goal is not None:
            assert analysis.request_plan.user_goal == goal
        for scope in required_scopes:
            assert scope in analysis.request_plan.required_information_scopes
        plan = TOOLS.build(run_id=f"golden-{mode}-{index}", analysis=analysis, domain_plan=DOMAINS.determine(analysis))
        assert plan.request_plan == analysis.request_plan
        assert all(tool.startswith("read_") for tool in plan.tool_names)


def test_request_plan_preserves_a_follow_up_reference_without_reusing_unverified_text():
    analysis = ANALYSIS.analyze(
        message="Onderbouw die conclusie voor mijn bot.",
        conversation_context={
            "last_user_goal": "evaluate_complete_plan",
            "last_verified_conclusion": "verified only",
            "resolved_asset": "BTC",
            "resolved_setup_id": 309,
            "resolved_strategy_id": 325,
            "resolved_bot_id": 186,
        },
    )

    assert analysis.request_plan is not None
    assert analysis.request_plan.conversation_reference == "evaluate_complete_plan"
    assert analysis.request_plan.user_goal == "read_bot"
    assert analysis.explicit_asset == "BTC"
    assert analysis.explicit_setup_id == 309
    assert analysis.explicit_strategy_id == 325
    assert analysis.explicit_bot_id == 186
