import pytest

from backend.domain.finn_v2_operation_registry import FinnV2OperationRegistry
from backend.services.finn_v2_domain_requirement_service import FinnV2DomainRequirementService
from backend.services.finn_v2_request_analysis_service import FinnV2RequestAnalysisService
from backend.services.finn_v2_tool_plan_service import FinnV2ToolPlanService


ANALYSIS = FinnV2RequestAnalysisService()
DOMAINS = FinnV2DomainRequirementService()
TOOLS = FinnV2ToolPlanService()
REGISTRY = FinnV2OperationRegistry()


GOLDEN_FAMILIES = [
    ("CAPABILITY", None, ["Hoi FINN, wat kun je voor mij doen?", "Waarmee help je mij?", "Wat doet FINN?", "Hoe kun je mij helpen?", "What can FINN do for me?"], []),
    ("READ", "read_asset", ["Welke asset heb ik actief?", "Wat is mijn actieve asset?", "Toon mijn gekozen asset.", "Welke coin of aandeel volg ik nu?", "Laat mijn huidige instrument zien."], ["active_asset"]),
    ("READ", "read_setup", ["Welke setup is actief?", "Toon mijn actieve setup.", "Wat is mijn huidige BTC setup?", "Welke setup gebruik ik?", "Op welk timeframe draait mijn setup?"], ["active_asset", "active_setup"]),
    ("READ", "read_indicators", ["Welke indicatoren zijn ingesteld?", "Toon mijn indicatorconfiguratie.", "Welke signalen gebruik ik?", "Hoe zijn mijn indicatoren geconfigureerd?", "Welke volume- en trendindicatoren volg ik?"], ["active_asset", "indicator_configuration"]),
    ("READ", None, ["Welke strategie gebruikt mijn bot?", "Aan welke strategie is mijn bot gekoppeld?", "Toon mijn strategie en bot.", "Wat is mijn actieve plan en welke bot hoort daarbij?", "Welke bot hoort bij deze setup?"], ["active_asset", "active_setup", "linked_strategy", "linked_bot", "bot_status"]),
    ("EVALUATE", "evaluate_complete_plan", ["Bekijk mijn hele plan en noem het zwakste punt.", "Waar wringt mijn plan?", "Wat ontbreekt er nog in mijn plan?", "Beoordeel mijn profiel, indicatoren, setup, strategie en bot.", "Welke voorwaarde ontbreekt voordat ik dit plan kan vertrouwen?"], ["profile", "indicator_configuration", "active_setup", "linked_strategy", "linked_bot", "bot_status"]),
    ("EVALUATE", None, ["Past mijn strategie bij mijn risicoprofiel?", "Is mijn strategie een goede fit voor mijn tradingstijl?", "Waar zit het risico in mijn plan?", "Beoordeel het vertrouwen in mijn bot.", "Welke indicator weegt het zwaarst in mijn plan?"], []),
    ("CREATE_PROPOSAL", "propose_setup", ["Maak een setup voor BTC swing trading.", "Stel een BTC setup voor.", "Bereid een nieuwe setup voor, nog niet opslaan.", "Welk setupconcept past bij mijn plan?", "Create a setup proposal for BTC."], ["active_asset"]),
    ("ACTION_PROPOSAL", "propose_watchlist_change", ["Voeg ETH toe aan mijn watchlist.", "Zet ETH op mijn volglijst.", "Add ETH to my watchlist.", "Ik wil ETH toevoegen aan de watchlist.", "Maak een voorstel om ETH te volgen."], ["active_asset", "watchlist"]),
    ("ACTION_PROPOSAL", None, ["Activeer deze bot live.", "Zet mijn bot live.", "Maak deze bot live.", "Activate my bot live.", "Start live trading met deze bot."], ["active_asset", "active_setup", "linked_strategy", "linked_bot", "bot_status", "market_snapshot"]),
]


@pytest.mark.parametrize("mode,goal,messages,required_scopes", GOLDEN_FAMILIES)
def test_btc_golden_paraphrases_keep_a_canonical_request_contract(mode, goal, messages, required_scopes):
    for index, message in enumerate(messages):
        analysis = ANALYSIS.analyze(message=message)
        contract = REGISTRY.require_supported(analysis.request_plan.operation_id)
        assert analysis.interaction_mode == mode
        assert analysis.request_plan is not None
        assert analysis.request_plan.interaction_mode == contract.mode
        assert analysis.request_plan.operation_contract_version == contract.version
        assert analysis.request_plan.required_information_scopes == list(contract.required_scopes)
        assert analysis.request_plan.optional_information_scopes == list(contract.optional_scopes)
        if goal is not None:
            assert analysis.request_plan.user_goal == goal
        for scope in required_scopes:
            assert scope in analysis.request_plan.required_information_scopes
        plan = TOOLS.build(run_id=f"golden-{mode}-{index}", analysis=analysis, domain_plan=DOMAINS.determine(analysis))
        assert plan.request_plan == analysis.request_plan
        assert plan.tool_names == list(contract.tool_names)


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
            "last_mode": "EVALUATE",
            "last_primary_domains": ["profile", "indicators", "setup", "strategy", "bot"],
            "last_required_information_scopes": ["profile", "preferences", "active_asset", "indicator_configuration", "active_setup", "linked_strategy", "linked_bot", "bot_status"],
        },
    )

    assert analysis.request_plan is not None
    assert analysis.request_plan.conversation_reference == "evaluate_complete_plan"
    assert analysis.request_plan.user_goal == "evaluate"
    assert analysis.explicit_asset == "BTC"
    assert analysis.explicit_setup_id == 309
    assert analysis.explicit_strategy_id == 325
    assert analysis.explicit_bot_id == 186
    assert analysis.interaction_mode == "EVALUATE"
    assert analysis.request_plan.required_information_scopes == [
        "profile", "preferences", "active_asset", "indicator_configuration", "active_setup", "linked_strategy", "linked_bot", "bot_status",
    ]


def test_request_plan_requires_a_clarification_when_a_reference_has_no_verified_turn():
    analysis = ANALYSIS.analyze(message="Waar baseer je dat op?", conversation_context={})

    assert analysis.interaction_mode == "CLARIFICATION"
    assert "conversation_reference_without_verified_context" in analysis.unresolved_signals


@pytest.mark.parametrize("message", [
    "Welke asset bekijk ik nu?",
    "Waar staat mijn huidige workspace op?",
    "Over welke markt hebben we het momenteel?",
])
def test_active_asset_paraphrases_share_the_canonical_asset_contract(message):
    analysis = ANALYSIS.analyze(message=message, workspace_hints={"symbol": "BTC"})

    assert analysis.interaction_mode == "READ"
    assert analysis.primary_subject == "asset"
    assert analysis.request_plan.required_information_scopes == ["active_asset"]
