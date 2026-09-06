from backend.services.finn_v2_request_preprocessor_service import FinnV2RequestPreprocessorService


def test_autonomous_financial_delegation_is_a_financial_execution_fact():
    facts = FinnV2RequestPreprocessorService().preprocess(
        message="Move my savings into whichever digital asset you expect to rise tomorrow."
    )

    assert facts.financial_execution_intent is True
    assert facts.action_polarity == "execute"


def test_autonomous_financial_decision_authority_is_an_execution_fact_without_trade_verb():
    service = FinnV2RequestPreprocessorService()

    dutch = service.preprocess(
        message="Mag de assistent zelfstandig beslissingen nemen voor mijn beleggingsaccount?"
    )
    english = service.preprocess(
        message="Let the assistant autonomously manage decisions for my investment account."
    )
    german = service.preprocess(
        message="Darf der Assistent autonome Entscheidungen fuer mein Anlagekonto treffen?"
    )

    for facts in (dutch, english, german):
        assert facts.financial_execution_intent is True
        assert facts.action_polarity == "execute"
        assert facts.domain_hint == "financial"


def test_non_financial_move_request_remains_outside_the_financial_execution_boundary():
    facts = FinnV2RequestPreprocessorService().preprocess(
        message="Move my calendar appointment to tomorrow."
    )

    assert facts.financial_execution_intent is False


def test_catalog_asset_compound_plan_and_german_indicator_are_typed_request_facts():
    plan = FinnV2RequestPreprocessorService().preprocess(
        message="Beoordeel mijn goudplan op risico."
    )
    indicators = FinnV2RequestPreprocessorService().preprocess(
        message="Welche Indikatoren sind für meine Solana-Konfiguration gespeichert?"
    )

    assert plan.referenced_asset == "XAU"
    assert plan.primary_entity == "plan"
    assert "plan" in plan.explicit_entities
    assert "indicator_configuration" in indicators.explicit_entities
    assert indicators.referenced_asset == "SOL"


def test_bare_causal_question_is_a_lineage_marker_not_an_off_topic_fact():
    facts = FinnV2RequestPreprocessorService().preprocess(message="Warum?")

    assert "previous_verified_conclusion" in facts.conversation_reference_markers


def test_product_capability_availability_questions_remain_financial_in_all_supported_languages():
    service = FinnV2RequestPreprocessorService()

    for message in (
        "Welke FINN-hulp is beschikbaar voor setups en analyses?",
        "What support is available from FINN for setups and analysis?",
        "Welche FINN-Hilfe ist für Setups und Analysen verfügbar?",
    ):
        facts = service.preprocess(message=message)

        assert facts.discourse_act == "capability"
        assert facts.domain_hint == "financial"


def test_concrete_asset_bound_approach_is_a_setup_but_broad_diagnosis_remains_a_plan():
    service = FinnV2RequestPreprocessorService()
    setup = service.preprocess(message="Show the concrete trading approach prepared for Ethereum.")
    plan = service.preprocess(message="Which part of my trading approach is most resilient?")

    assert setup.referenced_asset == "ETH"
    assert setup.primary_entity == "setup"
    assert "setup" in setup.explicit_entities
    assert plan.primary_entity == "plan"
