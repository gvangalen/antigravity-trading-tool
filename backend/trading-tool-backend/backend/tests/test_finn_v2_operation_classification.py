import pytest

from backend.services.finn_v2_operation_classification_service import (
    FinnV2OperationClassificationService, FinnV2OperationClassificationValidator,
    SemanticOperationClassification,
)
from backend.domain.finn_v2_operation_registry import ActionPolarity, FinnV2OperationRegistry
from backend.services.finn_v2_structured_operation_selector_service import FinnV2StructuredOperationSelection


CLASSIFIER = FinnV2OperationClassificationService()


@pytest.mark.parametrize(
    ("operation_id", "messages"),
    [
        ("capability", (
            "Wat kan FINN doen?", "Waarmee kan FINN helpen?", "Hoe helpt FINN mij?",
            "Welke mogelijkheden heeft FINN?", "What can FINN do?", "Help me begrijpen wat FINN kan.",
        )),
        ("read_active_asset", (
            "Welke asset staat actief?", "Welk instrument is geselecteerd?", "Welke coin volg ik?",
            "Welk aandeel bekijk ik?", "Waar staat mijn workspace op?", "Welke markt is actief?",
        )),
        ("read_indicator_configuration", (
            "Welke indicatoren zijn ingesteld?", "Toon mijn indicatorconfiguratie.", "Welke signalen gebruik ik?",
            "Hoe zijn mijn indicatoren geconfigureerd?", "Welke volume-indicator volg ik?", "Welke trendindicatoren gebruik ik?",
        )),
        ("read_active_setup", (
            "Welke setup gebruik ik?", "Toon mijn actieve setup.", "Welke setup staat voor BTC actief?",
            "Laat de huidige setup zien.", "Wat is mijn setup?", "Welke set-up heb ik?",
        )),
        ("evaluate_plan", (
            "Beoordeel mijn volledige plan.", "Waar zit het zwakke punt in mijn plan?", "Past mijn plan bij mijn profiel?",
            "Welke voorwaarde ontbreekt in mijn plan?", "Hoe betrouwbaar is mijn plan?", "Bekijk mijn BTC-plan en noem het risico.",
        )),
        ("create_setup", (
            "Maak een setup voor BTC.", "Ontwerp een nieuwe BTC-setup.", "Stel een setup voor BTC voor.",
            "Bereid een setup voor BTC voor.", "Create a BTC setup.", "Maak een setupconcept voor BTC.",
        )),
        ("watchlist_add", (
            "Voeg ADA toe aan mijn watchlist.", "Add ADA to my watchlist.", "Zet ADA op mijn volglijst.",
            "Voeg ADA toe aan de watchlist.", "Ik wil ADA aan mijn watchlist toevoegen.", "Volg ADA in mijn watchlist.",
        )),
        ("watchlist_remove", (
            "Verwijder ADA uit mijn watchlist.", "Remove ADA from my watchlist.", "Haal ADA van mijn volglijst.",
            "Verwijder ADA van de watchlist.", "Ik wil ADA uit mijn watchlist halen.", "Stop met ADA volgen in mijn watchlist.",
        )),
        ("activate_bot", (
            "Activeer mijn bot live.", "Schakel mijn bot live.", "Start mijn bot live.",
            "Zet mijn bot live.", "Activate my bot live.", "Maak deze bot live.",
        )),
    ],
)
def test_semantic_operation_paraphrases_select_one_contract(operation_id, messages):
    assert {CLASSIFIER.classify(message=message).operation_id for message in messages} == {operation_id}


@pytest.mark.parametrize(
    ("operation_id", "messages"),
    [
        ("explain_previous_evidence", (
            "Onderbouw die conclusie.", "Waar baseer je dat op?", "Welk bewijs ondersteunt dit?",
            "Waarom concludeerde je dat?", "Leg de eerdere conclusie uit.", "Toon de evidence achter dat antwoord.",
        )),
        ("reformulate_previous_response", (
            "Formuleer dat korter.", "Zeg die conclusie anders.", "Herformuleer het vorige antwoord.",
            "Kun je dit compacter maken?", "Vertel dat in andere woorden.", "Maak de eerdere conclusie korter.",
        )),
    ],
)
def test_follow_up_paraphrases_keep_the_verified_conversation_lineage(operation_id, messages):
    context = {
        "last_verified_context": {
            "verified_response_id": "verified-btc-1",
            "operation_id": "evaluate_plan",
            "mode": "EVALUATE",
            "conclusion": "A grounded conclusion.",
            "evidence_refs": ["artifact-1"],
        },
    }

    assert {
        CLASSIFIER.classify(message=message, conversation_context=context).operation_id
        for message in messages
    } == {operation_id}


def test_target_polarity_is_not_reversed_by_workspace_context():
    add = CLASSIFIER.classify(message="Voeg ADA toe aan mijn watchlist.")
    remove = CLASSIFIER.classify(message="Verwijder ADA uit mijn watchlist.")

    assert add.action == "add"
    assert add.operation_id == "watchlist_add"
    assert remove.action == "remove"
    assert remove.operation_id == "watchlist_remove"


def test_registry_owns_the_canonical_action_polarity_for_every_qa_write_boundary():
    registry = FinnV2OperationRegistry()

    assert registry.get("watchlist_add").action_polarity is ActionPolarity.ADD
    assert registry.get("watchlist_remove").action_polarity is ActionPolarity.REMOVE
    assert registry.get("create_setup").action_polarity is ActionPolarity.CREATE
    assert registry.get("activate_bot").action_polarity is ActionPolarity.ACTIVATE
    assert registry.get("unsupported_financial_operation").action_polarity is ActionPolarity.EXECUTE
    assert registry.get("clarify_request").action_polarity is ActionPolarity.CLARIFY


def test_validator_accepts_registry_projection_and_rejects_a_forged_polarity():
    valid = SemanticOperationClassification(
        operation_id="watchlist_add", action="add", domain="watchlist",
        discourse="operation_request", confidence="high", selector_source="structured",
    )
    forged = SemanticOperationClassification(
        operation_id="watchlist_add", action="create", domain="watchlist",
        discourse="operation_request", confidence="high", selector_source="structured",
    )
    validator = FinnV2OperationClassificationValidator()

    assert validator.validation_error(valid) is None
    assert validator.validation_error(forged) == "operation_canonical_action_mismatch"


@pytest.mark.parametrize(
    ("operation_id", "message", "discourse"),
    (
        ("explain_previous_evidence", "Waar baseer je dat op?", "evidence_follow_up"),
        ("reformulate_previous_response", "Leg dat eenvoudiger uit.", "reformulation"),
    ),
)
def test_validator_allows_safe_degraded_lineage_without_promoting_a_conclusion(operation_id, message, discourse):
    classification = SemanticOperationClassification(
        operation_id=operation_id, action="read", domain="lineage",
        discourse=discourse, confidence="high", selector_source="structured",
    )
    facts = CLASSIFIER.preprocessor.preprocess(message=message)
    context = {"last_degraded_context": {"evidence_refs": ["E1"], "reason_codes": ["response_field_incomplete"]}}

    assert FinnV2OperationClassificationValidator().validation_error(
        classification, facts=facts, conversation_context=context,
    ) is None
    assert "conclusion" not in CLASSIFIER._safe_conversation_state(context)["last_degraded_context"]


def test_typed_input_projection_does_not_treat_model_entities_as_user_supplied_slots():
    result = CLASSIFIER.classify(message="Maak een BTC breakout-setup op 4H.")

    assert result.required_inputs == ("setup_type", "timeframe", "name", "symbol")
    assert result.supplied_inputs == {"symbol": "BTC", "setup_type": "trade", "timeframe": "4H"}
    assert result.derived_inputs == {"target_asset": "BTC"}
    assert result.selected_missing_inputs == ("name",)


def test_typed_setup_slots_fill_a_lossy_structured_entity_projection():
    class Selector:
        def select(self, **_kwargs):
            return FinnV2StructuredOperationSelection(
                operation_id="create_setup", confidence=0.9, entities={"asset": "BTC", "setup_type": "position"},
                target_asset="BTC", conversation_reference=None, missing_inputs=(), ambiguity_reason=None,
                semantic_frame={},
            ), None

    result = FinnV2OperationClassificationService(structured_selector=Selector()).classify(
        message="Prepare a BTC position setup for weekly review named Capital Shield; proposal only.",
    )

    assert result.selected_entities["timeframe"] == "1W"
    assert result.selected_entities["name"] == "Capital Shield"


def test_live_order_language_uses_typed_bot_activation_polarity():
    for message in (
        "Laat mijn gekoppelde robot voortaan echte orders plaatsen.",
        "Zorg dat de gekoppelde automation live orders uitvoert.",
        "Mijn bot moet reële orders gaan versturen.",
    ):
        result = CLASSIFIER.classify(message=message)
        assert result.operation_id == "activate_bot"
        assert result.action == "activate"


def test_live_automation_enablement_is_not_a_bot_status_read():
    facts = CLASSIFIER.preprocessor.preprocess(
        message="Ik wil de gekoppelde automation live inschakelen."
    )

    assert facts.action_polarity == "activate"
    assert facts.discourse_act == "operation_request"


@pytest.mark.parametrize("message", (
    "Waar wringt mijn huidige aanpak financieel gezien het meest?",
    "Welke risico's maken mijn handelswijze het kwetsbaarst?",
    "Welk verbeterpunt is in mijn bestaande tradingaanpak het belangrijkst?",
))
def test_natural_plan_assessment_is_an_evaluation_fact(message):
    facts = CLASSIFIER.preprocessor.preprocess(message=message)

    assert facts.action_polarity == "evaluate"
    assert facts.discourse_act == "evaluation"


@pytest.mark.parametrize("message", (
    "Waar is mijn handelsaanpak het kwetsbaarst?",
    "Which part of my trading approach is least resilient?",
    "An welcher Stelle ist mein Handelsplan am fragilsten?",
    "Mijn plan is sterk, maar waar zit het resterende risico?",
    "Welk onderdeel van mijn aanpak heeft het zwakste bewijs?",
))
def test_plan_assessment_predicates_constrain_the_semantic_frame_without_routing(message):
    facts = CLASSIFIER.preprocessor.preprocess(message=message)

    assert facts.primary_entity == "plan"
    assert facts.action_polarity == "evaluate"
    assert facts.discourse_act == "evaluation"


@pytest.mark.parametrize("message", (
    "Waar staat mijn handelsaanpak opgeslagen?",
    "Is mijn trading approach gekoppeld aan een bot?",
    "Wo finde ich meinen Handelsplan?",
))
def test_non_diagnostic_plan_questions_remain_read_facts(message):
    facts = CLASSIFIER.preprocessor.preprocess(message=message)

    assert facts.action_polarity == "read"
    assert facts.discourse_act == "information_request"


def test_ambiguous_improvement_has_typed_clarification_input_and_clarify_polarity():
    result = CLASSIFIER.classify(message="Maak mijn manier van handelen beter.")

    assert result.operation_id == "clarify_request"
    assert result.action == "clarify"
    assert result.selected_missing_inputs == ("requested_change",)


def test_financial_concept_entity_is_canonicalized_after_structured_selection():
    result = CLASSIFIER.classify(
        message="Kun je in gewone taal uitleggen waarvoor ATR wordt gebruikt?"
    )

    assert result.operation_id == "explain_financial_concept"
    assert result.selected_entities["concept"] == "ATR"
    assert result.selected_missing_inputs == ()


def test_complete_setup_slots_remove_model_reported_missing_inputs():
    result = CLASSIFIER.classify(
        message="Werk voor DOT een breakout-opzet uit op 2H en noem hem Polkadot Uitbraak."
    )

    assert result.operation_id == "create_setup"
    assert result.selected_target_asset == "DOT"
    assert result.action == "create"
    assert result.selected_missing_inputs == ()
    assert result.selector_source == "structured"
    assert result.reason_code is None


@pytest.mark.parametrize(
    "message",
    (
        "Help me een nieuwe Solana-setup te maken.",
        "Could you help me prepare a new Solana setup?",
        "Hilf mir, ein neues Solana-Setup zu erstellen.",
    ),
)
def test_guided_setup_request_preserves_creation_contract_and_requires_slot_collection(message):
    result = CLASSIFIER.classify(message=message)

    assert result.operation_id == "create_setup"
    assert result.selected_missing_inputs == ("setup_type", "timeframe", "name")
    assert result.clarification_required is True


def test_direct_incomplete_setup_request_does_not_misrepresent_a_guided_exchange():
    result = CLASSIFIER.classify(message="Maak een Solana-setup.")

    assert result.operation_id == "create_setup"
    assert result.selected_missing_inputs == ("setup_type", "timeframe", "name")
    assert result.clarification_required is False


def test_explicit_message_asset_overrides_conflicting_selector_asset_projection():
    class Selector:
        def select(self, **_kwargs):
            return FinnV2StructuredOperationSelection(
                operation_id="read_indicator_configuration", confidence=0.95,
                entities={"asset": "AAPL"}, target_asset="AAPL", conversation_reference=None,
                missing_inputs=(), ambiguity_reason=None,
                semantic_frame={"goal": "read", "object": "indicator"},
            ), None

    result = FinnV2OperationClassificationService(structured_selector=Selector()).classify(
        message="De werkruimte staat op AAPL, maar lees uitsluitend mijn opgeslagen Solana-indicatoren."
    )

    assert result.selected_target_asset == "SOL"
    assert result.selected_entities["asset"] == "SOL"


def test_separable_dutch_execution_verb_selects_the_execution_contract():
    result = CLASSIFIER.classify(message="Voer dit voorstel uit.")

    assert result.operation_id == "execute_proposal"
    assert result.action == "execute"


@pytest.mark.parametrize("message", ("Maak iets nieuws.", "Wijzig mijn instellingen.", "Voeg iets toe."))
def test_ambiguous_action_without_a_domain_remains_a_clarification(message):
    assert CLASSIFIER.classify(message=message).operation_id == "clarify_request"


def test_complete_graph_request_uses_the_plan_contract():
    result = CLASSIFIER.classify(message="Welke setup, strategie en bot heb ik voor mijn actieve asset?")

    assert result.operation_id == "read_active_plan"


def test_model_first_selector_receives_read_candidates():
    captured = {}

    class Selector:
        def select(self, **kwargs):
            captured.update(kwargs)
            return type("Selection", (), {"operation_id": "read_active_setup", "confidence": 0.95})(), None

    classifier = FinnV2OperationClassificationService(structured_selector=Selector())

    result = classifier.classify(message="Welke setup of strategie gebruik ik?")

    assert result.operation_id == "read_active_setup"
    assert result.selector_source == "structured"
    offered = {contract.operation_id for contract in captured["candidate_contracts"]}
    assert {"read_active_setup", "read_linked_strategy", "clarify_request", "off_topic"}.issubset(offered)


def test_model_first_selector_receives_safe_terminal_lineage_context():
    captured = {}

    class Selector:
        def select(self, **kwargs):
            captured.update(kwargs)
            return type("Selection", (), {
                "operation_id": "explain_previous_evidence", "confidence": 0.9,
                "entities": {}, "target_asset": None, "conversation_reference": None,
                "missing_inputs": (), "ambiguity_reason": None,
            })(), None

    classifier = FinnV2OperationClassificationService(structured_selector=Selector())
    context = {
        "last_safe_terminal_context": {
            "operation_id": "off_topic", "run_id": "run-off-topic",
            "terminal_reason": "outside_finn_scope",
        },
    }

    result = classifier.classify(
        message="Waarom paste mijn vorige vraag niet binnen FINN?", conversation_context=context
    )

    assert result.operation_id == "explain_previous_evidence"
    assert captured["verified_context"]["last_safe_terminal_context"] == context["last_safe_terminal_context"]


def test_consequence_follow_up_reaches_the_model_with_typed_lineage_facts():
    captured = {}

    class Selector:
        def select(self, **kwargs):
            captured.update(kwargs)
            return type("Selection", (), {
                "operation_id": "explain_previous_evidence", "confidence": 0.9,
                "entities": {}, "target_asset": None,
                "conversation_reference": "previous_verified_response",
                "missing_inputs": (), "ambiguity_reason": None,
            })(), None

    classifier = FinnV2OperationClassificationService(structured_selector=Selector())
    result = classifier.classify(
        message="Welke controle volgt daaruit voor mijn bot?",
        conversation_context={
            "last_verified_context": {
                "verified_response_id": "verified-1", "run_id": "run-1",
                "evidence_refs": ["E1"],
            },
        },
    )

    assert result.operation_id == "explain_previous_evidence"
    assert captured["facts"]["discourse_act"] == "contextual_follow_up"


def test_typed_guided_slot_answer_reuses_pending_contract_without_provider():
    class Selector:
        def select(self, **kwargs):
            raise AssertionError("typed pending slot must not call the provider")

    classifier = FinnV2OperationClassificationService(structured_selector=Selector())
    result = classifier.classify(
        message="4H.",
        conversation_context={
            "conversation_state_version": "finn_v2.conversation-contracts.v1",
            "active_guided_operation": {
                "operation_id": "create_setup",
                "missing_required_inputs": ["timeframe"],
            },
        },
    )

    assert result.operation_id == "create_setup"
    assert result.selector_source == "guided_state"
    assert result.supplied_inputs["timeframe"] == "4H"


def test_typed_graph_scopes_resolve_to_a_complete_linked_bot_read_contract():
    class Selector:
        def select(self, **_kwargs):
            return FinnV2StructuredOperationSelection(
                operation_id="read_active_setup", confidence=0.9, entities={}, target_asset=None,
                conversation_reference=None, missing_inputs=(), ambiguity_reason=None,
                semantic_frame={"goal": "read", "object": "setup", "requested_scopes": ("setup", "strategy", "bot")},
            ), None

    result = FinnV2OperationClassificationService(structured_selector=Selector()).classify(
        message="Welke gekoppelde onderdelen horen bij mijn huidige aanpak?"
    )

    assert result.operation_id == "read_linked_bot"
    assert result.action == "read"


def test_provider_failure_is_terminal_and_never_selects_a_local_operation():
    class ExplodingSelector:
        def select(self, **_kwargs):
            return None, "selector_provider_unavailable"

    classifier = FinnV2OperationClassificationService(structured_selector=ExplodingSelector())

    result = classifier.classify(message="Maak iets nieuws.")

    assert result.operation_id == "unavailable"
    assert result.selector_source == "provider_unavailable"


def test_low_confidence_safe_terminal_selection_remains_typed():
    class Selector:
        def select(self, **_kwargs):
            return type("Selection", (), {
                "operation_id": "off_topic", "confidence": 0.0,
                "entities": {}, "target_asset": None,
                "conversation_reference": None, "missing_inputs": (),
            })(), None

    result = FinnV2OperationClassificationService(structured_selector=Selector()).classify(
        message="Schrijf een recept voor appeltaart."
    )

    assert result.operation_id == "off_topic"
    assert result.selector_source == "structured"


def test_low_confidence_lineage_selection_requires_safe_persisted_context():
    class Selector:
        def select(self, **_kwargs):
            return type("Selection", (), {
                "operation_id": "explain_previous_evidence", "confidence": 0.6,
                "entities": {}, "target_asset": None,
                "conversation_reference": "previous_verified_response", "missing_inputs": (),
            })(), None

    classifier = FinnV2OperationClassificationService(structured_selector=Selector())
    without_context = classifier.classify(message="Waarop baseer je die conclusie?")
    with_context = classifier.classify(
        message="Waarop baseer je die conclusie?",
        conversation_context={"last_verified_context": {"verified_response_id": "verified-1"}},
    )

    assert without_context.operation_id == "unavailable"
    assert with_context.operation_id == "explain_previous_evidence"


def test_manifest_candidates_exclude_contracts_without_selection_metadata():
    facts = CLASSIFIER.preprocessor.preprocess(message="Welke indicatoren gebruik ik?")

    candidates = CLASSIFIER.registry.candidate_operations(
        entities=facts.explicit_entities,
        action_polarity=facts.action_polarity,
        discourse_act=facts.discourse_act,
        has_verified_context=False,
        normalized_text=facts.normalized_text,
        primary_entity=facts.primary_entity,
    )

    assert [contract.operation_id for contract in candidates] == ["read_indicator_configuration"]


def test_explicit_target_asset_never_replaces_workspace_context_asset():
    facts = CLASSIFIER.preprocessor.preprocess(
        message="Voeg Cardano toe aan mijn watchlist.",
        workspace_hints={"symbol": "BTC"},
    )

    assert facts.workspace_context_asset == "BTC"
    assert facts.explicit_target_asset == "ADA"
    assert facts.referenced_asset == "ADA"


def test_preprocessor_distinguishes_an_explicit_plan_from_an_inferred_graph_subject():
    explicit_plan = CLASSIFIER.preprocessor.preprocess(
        message="Show my active plan with its setup, strategy, and bot."
    )
    graph_only = CLASSIFIER.preprocessor.preprocess(
        message="Which strategy and bot are linked to my active setup?"
    )

    assert explicit_plan.explicit_plan_subject is True
    assert graph_only.explicit_plan_subject is False
    assert graph_only.linked_graph_relationship is True


def test_preprocessor_recognizes_current_asset_subjects_across_supported_languages():
    for message in (
        "Op welk effect staat mijn werkruimte nu?",
        "Which security is selected in my workspace?",
        "Welches Wertpapier ist aktuell ausgewahlt?",
    ):
        facts = CLASSIFIER.preprocessor.preprocess(message=message)
        assert "asset" in facts.explicit_entities


def test_preprocessor_keeps_a_complete_graph_overview_distinct_from_a_link_relationship():
    overview = CLASSIFIER.preprocessor.preprocess(
        message="Welke setup, strategie en bot heb ik?"
    )
    german_relationship = CLASSIFIER.preprocessor.preprocess(
        message="Welche Strategie und welcher Bot sind mit meinem aktiven Setup verbunden?"
    )

    assert overview.linked_graph_relationship is False
    assert german_relationship.linked_graph_relationship is True


def test_catalog_canonicalizes_cosmos_before_selector_or_proposal_boundaries():
    facts = CLASSIFIER.preprocessor.preprocess(message="Neem Cosmos op in mijn lijst met gevolgde assets.")

    assert facts.referenced_asset == "ATOM"
    assert facts.explicit_target_asset == "ATOM"


def test_catalog_canonicalizes_ether_for_an_explicit_unsupported_execution_target():
    facts = CLASSIFIER.preprocessor.preprocess(
        message="Verkoop één ether met een echte marktorder."
    )

    assert facts.referenced_asset == "ETH"


def test_contrastive_current_turn_asset_wins_over_a_mentioned_workspace_asset():
    facts = CLASSIFIER.preprocessor.preprocess(
        message="The workspace mentions Apple, but show the saved Ethereum indicators instead."
    )

    assert facts.referenced_asset == "ETH"


def test_follow_up_requires_verified_context_in_the_contract_manifest():
    no_context = CLASSIFIER.classify(message="Onderbouw die conclusie.")
    with_context = CLASSIFIER.classify(
        message="Onderbouw die conclusie.",
        conversation_context={"last_verified_context": {"verified_response_id": "verified-1"}},
    )

    assert no_context.operation_id == "clarify_request"
    assert with_context.operation_id == "explain_previous_evidence"


def test_recorded_facts_after_an_immediate_judgment_are_lineage_facts_not_off_topic():
    facts = CLASSIFIER.preprocessor.preprocess(
        message="Noem de vastgelegde feiten achter je zojuist gegeven oordeel."
    )

    assert facts.discourse_act == "evidence_follow_up"
    assert "previous_verified_conclusion" in facts.conversation_reference_markers


def test_guided_slot_answer_offers_only_its_typed_contract_and_safe_terminals():
    class Selector:
        def select(self, **_kwargs):
            raise AssertionError("guided slot answers must not call the selector")

    classifier = FinnV2OperationClassificationService(structured_selector=Selector())
    result = classifier.classify(
        message="Gebruik de 4H-timeframe.",
        conversation_context={
            "active_guided_operation": {
                "operation_id": "create_setup",
                "contract_version": "2026-08-23.operation-contracts.v1",
                "missing_required_inputs": ["timeframe"],
            },
        },
    )

    assert result.operation_id == "create_setup"
    assert result.selector_source == "guided_state"


def test_short_setup_type_answer_keeps_the_active_contract_in_the_selector_manifest():
    class Selector:
        def select(self, **_kwargs):
            raise AssertionError("guided slot answers must not call the selector")

    classifier = FinnV2OperationClassificationService(structured_selector=Selector())
    result = classifier.classify(
        message="Kies voor de categorie trade.",
        conversation_context={
            "conversation_state_version": "finn_v2.conversation-contracts.v1",
            "active_guided_operation": {
                "operation_id": "create_setup",
                "contract_version": "2026-08-23.operation-contracts.v1",
                "missing_required_inputs": ["setup_type", "timeframe", "name"],
            },
        },
    )

    assert result.operation_id == "create_setup"
    assert result.selector_source == "guided_state"


def test_natural_guided_slot_answer_keeps_the_persisted_contract_without_provider():
    class Selector:
        def select(self, **_kwargs):
            raise AssertionError("a guided clarification answer must not reroute through the provider")

    result = FinnV2OperationClassificationService(structured_selector=Selector()).classify(
        message="Gebruik als timeframe de vieruursgrafiek.",
        conversation_context={
            "conversation_state_version": "finn_v2.conversation-contracts.v1",
            "active_guided_operation": {
                "operation_id": "create_setup",
                "contract_version": "2026-08-23.operation-contracts.v1",
                "missing_required_inputs": ["timeframe", "name"],
            },
        },
    )

    assert result.operation_id == "create_setup"
    assert result.selector_source == "guided_state"


@pytest.mark.parametrize(
    "message",
    (
        "Wat kun je voor mij doen binnen mijn handelsplan?",
        "Leg kort uit welke analyses en acties je ondersteunt.",
    ),
)
def test_capability_request_never_gets_hijacked_by_verified_or_guided_context(message):
    result = CLASSIFIER.classify(
        message=message,
        conversation_context={
            "last_verified_context": {"verified_response_id": "verified-1"},
            "active_guided_operation": {
                "operation_id": "create_setup",
                "contract_version": "2026-08-23.operation-contracts.v1",
                "missing_required_inputs": ["name"],
            },
        },
    )

    assert result.operation_id == "capability"
    assert result.selector_source == "structured"


def test_technical_configuration_is_an_indicator_read_not_a_workspace_asset_read():
    result = CLASSIFIER.classify(message="Vat mijn technische configuratie voor dit instrument samen.")

    assert result.operation_id == "read_indicator_configuration"
