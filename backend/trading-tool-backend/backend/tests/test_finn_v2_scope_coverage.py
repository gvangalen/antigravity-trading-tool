from datetime import datetime, timezone
from types import SimpleNamespace

from backend.schemas.finn_v2_orchestrator_schema import RequestPlan
from backend.schemas.finn_v2_reasoning_schema import ProposalCandidate, ReasoningNextStep, ReasoningSupportingPoint
from backend.schemas.finn_v2_response_schema import ResponseClaim, ResponseDraft
from backend.domain.finn_v2_operation_registry import FinnV2OperationRegistry
from backend.services.finn_v2_response_verifier_service import FinnV2ResponseVerifierService


CONTRACT_VERSION = FinnV2OperationRegistry.VERSION


def test_lineage_evidence_response_remains_relevant_after_an_off_topic_turn():
    draft = ResponseDraft(
        draft_id="draft-lineage-evidence",
        run_id="run-lineage-evidence",
        user_id=7,
        mode="EVALUATE",
        direct_answer="De eerdere beperkte beoordeling baseert zich uitsluitend op opgeslagen FINN-evidence.",
        main_observation="Die evidence bevestigt geen nieuwe financiële conclusie.",
        evidence_set_hash="hash-lineage-evidence",
        reasoning_provenance={
            "reasoning_source": "lineage_evidence",
            "operation_id": "explain_previous_evidence",
        },
        created_at=datetime.now(timezone.utc),
    )

    assert FinnV2ResponseVerifierService(session=object())._is_relevant(
        "Onderbouw nu weer je eerdere BTC-conclusie met de opgeslagen evidence.", draft
    ) is True


def test_integrated_plan_verifier_requires_a_grounded_strength_and_limitation():
    draft = ResponseDraft(
        draft_id="draft-plan-quality",
        run_id="run-plan-quality",
        user_id=7,
        mode="EVALUATE",
        direct_answer="Het plan heeft een bruikbare basis, maar de beschikbare gegevens bewijzen nog geen complete zwakteanalyse.",
        main_observation="De setup en indicatoren vormen een feitelijke basis; de ontbrekende relatie tussen die gegevens is onzeker.",
        supporting_points=[
            ReasoningSupportingPoint(title="Feitelijke basis", explanation="De opgeslagen setup is aanwezig.", evidence_refs=["E1"]),
            ReasoningSupportingPoint(title="Begrensde onzekerheid", explanation="De evidence bewijst geen causaal zwak punt.", evidence_refs=["E2"]),
        ],
        claims=[
            ResponseClaim(claim_id="fact", claim_type="fact", text="Setup 295 is opgeslagen.", evidence_refs=["E1"], confidence="high"),
            ResponseClaim(claim_id="limit", claim_type="uncertainty", text="Een causaal zwak punt is niet bewezen.", evidence_refs=["E2"], confidence="medium"),
        ],
        next_step=ReasoningNextStep(title="Verifieer de regel", instruction="Leg de ontbrekende beslisregel vast voordat je die beoordeelt.", requires_confirmation=False),
        evidence_set_hash="hash-plan-quality",
        created_at=datetime.now(timezone.utc),
    )

    assert FinnV2ResponseVerifierService._evaluate_plan_content_ok(operation_id="evaluate_plan", draft=draft) is True
    draft.supporting_points = draft.supporting_points[:1]
    assert FinnV2ResponseVerifierService._evaluate_plan_content_ok(operation_id="evaluate_plan", draft=draft) is False


def test_response_coverage_requires_the_contractual_setup_strategy_bot_graph():
    draft = ResponseDraft(
        draft_id="draft-graph-response",
        run_id="run-graph-response",
        user_id=7,
        mode="READ",
        direct_answer="Je actieve BTC-plan gebruikt setup 293, strategie 309 en bot 170.",
        main_observation="Bot 170 staat niet live.",
        evidence_refs_used=["E1", "E2", "E3", "E4"],
        evidence_set_hash="hash-graph-response",
        created_at=datetime.now(timezone.utc),
    )
    evidence = [
        SimpleNamespace(tool_name="read_active_setup", facts={"setup_id": 293, "name": "BTC swing", "timeframe": "4H"}),
        SimpleNamespace(tool_name="read_linked_strategy", facts={"strategy_id": 309, "name": "BTC strategy"}),
        SimpleNamespace(tool_name="read_linked_bot", facts={"bot_id": 170, "name": "BTC paper bot"}),
        SimpleNamespace(tool_name="read_bot_status", facts={"is_live": False}),
    ]

    covered = FinnV2ResponseVerifierService._covered_response_fields(
        draft=draft,
        evidence=evidence,
        required_fields=["setup", "strategy", "bot", "bot_status"],
    )

    assert covered == ["setup", "strategy", "bot", "bot_status"]


def test_response_coverage_does_not_treat_collected_graph_evidence_as_a_visible_answer():
    draft = ResponseDraft(
        draft_id="draft-hidden-graph",
        run_id="run-hidden-graph",
        user_id=7,
        mode="READ",
        direct_answer="Je plancontext is beschikbaar.",
        main_observation="Ik heb de opgeslagen relaties gecontroleerd.",
        evidence_set_hash="hash-hidden-graph",
        created_at=datetime.now(timezone.utc),
    )
    evidence = [
        SimpleNamespace(tool_name="read_active_setup", facts={"setup_id": 293}),
        SimpleNamespace(tool_name="read_linked_strategy", facts={"strategy_id": 309}),
        SimpleNamespace(tool_name="read_linked_bot", facts={"bot_id": 170}),
        SimpleNamespace(tool_name="read_bot_status", facts={"is_live": False}),
    ]

    covered = FinnV2ResponseVerifierService._covered_response_fields(
        draft=draft,
        evidence=evidence,
        required_fields=["setup", "strategy", "bot", "bot_status"],
    )

    assert covered == []


def test_empty_indicator_configuration_is_a_complete_typed_response():
    draft = ResponseDraft(
        draft_id="draft-empty-indicators",
        run_id="run-empty-indicators",
        user_id=7,
        mode="READ",
        direct_answer="Voor BTC staan 0 indicatoren ingesteld: geen indicatoren.",
        main_observation="Deze configuratie komt uit de opgeslagen BTC-regels.",
        evidence_refs_used=["E1", "E2"],
        evidence_set_hash="hash-empty-indicators",
        created_at=datetime.now(timezone.utc),
    )
    evidence = [
        SimpleNamespace(tool_name="read_active_asset", facts={"symbol": "BTC"}),
        SimpleNamespace(
            tool_name="read_indicator_configuration",
            facts={"symbol": "BTC", "configured_count": 0, "configured_indicators": []},
        ),
    ]

    covered = FinnV2ResponseVerifierService._covered_response_fields(
        draft=draft,
        evidence=evidence,
        required_fields=["asset", "configured_count", "indicator_names"],
    )

    assert covered == ["asset", "configured_count", "indicator_names"]


def test_scope_coverage_fails_when_a1_reduces_to_indicator_only():
    service = FinnV2ResponseVerifierService(session=object())
    draft = ResponseDraft(
        draft_id="draft-1",
        run_id="run-1",
        user_id=7,
        mode="EVALUATE",
        direct_answer="Je RSI staat goed.",
        main_observation="De indicatoren ogen sterk.",
        claims=[ResponseClaim(claim_id="C1", claim_type="evaluation", text="RSI is sterk.", evidence_refs=["E1"], confidence="high")],
        evidence_set_hash="hash-1",
        created_at=datetime.now(timezone.utc),
    )
    verifier = service._deterministic_verify(
        run=SimpleNamespace(id="run-1", user_id=7, message="Beoordeel profiel, indicators, setup, strategy en bot", conversation_id="conv-1"),
        orchestrator_result=SimpleNamespace(analysis=SimpleNamespace(subject_scopes=["profile", "indicators", "setup", "strategy", "bot"]), selected_clarification=None),
        policy=SimpleNamespace(allowed=True, proposal_allowed=True, confirmation_required=False, operation_type=None),
        context=SimpleNamespace(
            evidence=[SimpleNamespace(evidence_id="E1", domain="market_context", tool_name="read_indicator_configuration", entity_type="indicator_configuration", entity_id=None, asset="BTC", freshness="fresh", confidence="high", facts={"configured_indicators": [{"indicator": "rsi"}]})],
            uncertainty_codes=[],
        ),
        validation=SimpleNamespace(id="validation-1", evidence_set_hash="hash-1", integrity_status="valid"),
        draft=draft,
        repair_attempt=0,
        force_action="deliver",
    )

    assert verifier.coverage.coverage_ok is False
    assert verifier.passed is False
    assert "response_scope_incomplete" in verifier.reason_codes


def test_request_plan_coverage_does_not_substitute_a_broad_domain_for_evidence_scope():
    service = FinnV2ResponseVerifierService(session=object())
    draft = ResponseDraft(
        draft_id="draft-exact-scope",
        run_id="run-exact-scope",
        user_id=7,
        mode="READ",
        direct_answer="Je actieve asset is BTC.",
        main_observation="BTC is de asset in je workspace.",
        claims=[ResponseClaim(claim_id="C1", claim_type="fact", text="Je actieve asset is BTC.", evidence_refs=["E1"], confidence="high")],
        evidence_set_hash="hash-exact-scope",
        created_at=datetime.now(timezone.utc),
    )
    verifier = service._deterministic_verify(
        run=SimpleNamespace(id="run-exact-scope", user_id=7, message="Welke asset bekijk ik nu?", conversation_id="conv-1"),
        orchestrator_result=SimpleNamespace(
            analysis=SimpleNamespace(
                subject_scopes=["asset"],
                request_plan=RequestPlan(
                    operation_id="read_active_asset",
                    operation_contract_version=CONTRACT_VERSION,
                    interaction_mode="READ",
                    required_information_scopes=["profile", "active_asset"],
                ),
            ),
            selected_clarification=None,
        ),
        policy=SimpleNamespace(allowed=True, proposal_allowed=True, confirmation_required=False, operation_type=None),
        context=SimpleNamespace(
                evidence=[SimpleNamespace(evidence_id="E1", domain="identity_context", tool_name="read_active_asset", information_scope="active_asset", entity_type="asset", entity_id="BTC", asset="BTC", freshness="fresh", availability="available", confidence="high", facts={"symbol": "BTC"})],
            uncertainty_codes=[],
        ),
        validation=SimpleNamespace(id="validation-exact-scope", evidence_set_hash="hash-exact-scope", integrity_status="valid"),
        draft=draft,
        repair_attempt=0,
        force_action="deliver",
    )

    assert verifier.coverage.covered_scopes == ["active_asset"]
    assert verifier.coverage.missing_scopes == []
    assert verifier.coverage.coverage_ok is True


def test_new_request_plan_does_not_infer_scope_from_a_legacy_tool_name():
    service = FinnV2ResponseVerifierService(session=object())
    draft = ResponseDraft(
        draft_id="draft-no-persisted-scope",
        run_id="run-no-persisted-scope",
        user_id=7,
        mode="READ",
        direct_answer="Je actieve asset is BTC.",
        main_observation="BTC is de asset in je workspace.",
        claims=[ResponseClaim(claim_id="C1", claim_type="fact", text="Je actieve asset is BTC.", evidence_refs=["E1"], confidence="high")],
        evidence_set_hash="hash-no-persisted-scope",
        created_at=datetime.now(timezone.utc),
    )
    verifier = service._deterministic_verify(
        run=SimpleNamespace(id="run-no-persisted-scope", user_id=7, message="Welke asset bekijk ik nu?", conversation_id="conv-1"),
        orchestrator_result=SimpleNamespace(
            analysis=SimpleNamespace(
                subject_scopes=["asset"],
                request_plan=RequestPlan(
                    operation_id="read_active_asset",
                    operation_contract_version=CONTRACT_VERSION,
                    interaction_mode="READ",
                    required_information_scopes=["active_asset"],
                ),
            ),
            selected_clarification=None,
        ),
        policy=SimpleNamespace(allowed=True, proposal_allowed=True, confirmation_required=False, operation_type=None),
        context=SimpleNamespace(
            evidence=[SimpleNamespace(evidence_id="E1", domain="identity_context", tool_name="read_active_asset", entity_type="asset", entity_id="BTC", asset="BTC", freshness="fresh", availability="available", confidence="high", facts={"symbol": "BTC"})],
            uncertainty_codes=[],
        ),
        validation=SimpleNamespace(id="validation-no-persisted-scope", evidence_set_hash="hash-no-persisted-scope", integrity_status="valid"),
        draft=draft,
        repair_attempt=0,
        force_action="deliver",
    )

    assert verifier.coverage.covered_scopes == []
    assert verifier.coverage.missing_scopes == ["active_asset"]


def test_verifier_reconstruction_preserves_the_persisted_operation_contract():
    service = FinnV2ResponseVerifierService(session=object())
    row = SimpleNamespace(
        id="orchestrator-linked-bot",
        run_id="run-linked-bot",
        user_id=406,
        interaction_mode="READ",
        subject_scopes_json=["asset", "setup", "strategy", "bot", "profile", "indicators"],
        required_domains_json=["identity_context", "plan_context", "automation_context"],
        optional_domains_json=["market_context"],
        tool_plan_json={
            "run_id": "run-linked-bot",
            "interaction_mode": "READ",
            "primary_subject": "bot",
            "entity_selectors": {"asset": "BTC", "setup_id": 309, "strategy_id": 325, "bot_id": 186},
            "request_plan": RequestPlan(
                interaction_mode="READ",
                operation_id="read_linked_bot",
                required_information_scopes=["active_asset", "active_setup", "linked_strategy", "linked_bot", "bot_status"],
            ).dict(),
            "required_domains": ["identity_context", "plan_context", "automation_context"],
            "optional_domains": ["market_context"],
            "tool_names": ["read_active_asset", "read_active_setup", "read_linked_strategy", "read_linked_bot", "read_bot_status"],
            "required_evidence": ["active_asset", "active_setup", "linked_strategy", "linked_bot", "bot_status"],
            "max_tool_calls": 5,
        },
        snapshot_id="snapshot-linked-bot",
        validation_id="validation-linked-bot",
        outcome="reasoning_ready",
        selected_clarification_json=None,
        unavailable_codes_json=[],
        uncertainty_codes_json=[],
        orchestrator_version="finn_v2_orchestrator_v1",
        analysis_version="finn_v2_request_analysis_v1",
        created_at=datetime.now(timezone.utc),
    )

    result = service._orchestrator_result_from_row(row)

    assert result.analysis.request_plan.operation_id == "read_linked_bot"
    assert result.analysis.request_plan.required_information_scopes == [
        "active_asset", "active_setup", "linked_strategy", "linked_bot", "bot_status"
    ]
    assert result.analysis.explicit_asset == "BTC"
    assert result.analysis.explicit_setup_id == 309
    assert result.analysis.explicit_strategy_id == 325
    assert result.analysis.explicit_bot_id == 186


def test_canonical_scope_requires_available_nonempty_evidence():
    service = FinnV2ResponseVerifierService(session=object())
    draft = ResponseDraft(
        draft_id="draft-unavailable-scope",
        run_id="run-unavailable-scope",
        user_id=7,
        mode="READ",
        direct_answer="Je actieve asset is BTC.",
        main_observation="BTC is de asset in je workspace.",
        claims=[ResponseClaim(claim_id="C1", claim_type="fact", text="Je actieve asset is BTC.", evidence_refs=["E1"], confidence="high")],
        evidence_set_hash="hash-unavailable-scope",
        created_at=datetime.now(timezone.utc),
    )
    verifier = service._deterministic_verify(
        run=SimpleNamespace(id="run-unavailable-scope", user_id=7, message="Welke asset bekijk ik nu?", conversation_id="conv-1"),
        orchestrator_result=SimpleNamespace(
            analysis=SimpleNamespace(
                subject_scopes=["asset"],
                request_plan=RequestPlan(
                    operation_id="read_active_asset",
                    operation_contract_version=CONTRACT_VERSION,
                    interaction_mode="READ",
                    required_information_scopes=["active_asset"],
                ),
            ),
            selected_clarification=None,
        ),
        policy=SimpleNamespace(allowed=True, proposal_allowed=True, confirmation_required=False, operation_type=None),
        context=SimpleNamespace(
            evidence=[SimpleNamespace(evidence_id="E1", domain="identity_context", tool_name="read_active_asset", information_scope="active_asset", entity_type="asset", entity_id="BTC", asset="BTC", freshness="fresh", availability="unavailable", confidence="high", facts={})],
            uncertainty_codes=[],
        ),
        validation=SimpleNamespace(id="validation-unavailable-scope", evidence_set_hash="hash-unavailable-scope", integrity_status="valid"),
        draft=draft,
        repair_attempt=0,
        force_action="deliver",
    )

    assert verifier.coverage.covered_scopes == []
    assert verifier.coverage.missing_scopes == ["active_asset"]


def test_partial_contract_metadata_is_a_typed_failure_not_a_legacy_fallback():
    service = FinnV2ResponseVerifierService(session=object())
    draft = ResponseDraft(
        draft_id="draft-partial-contract",
        run_id="run-partial-contract",
        user_id=7,
        mode="READ",
        direct_answer="Je actieve asset is BTC.",
        main_observation="BTC is de asset in je workspace.",
        claims=[ResponseClaim(claim_id="C1", claim_type="fact", text="Je actieve asset is BTC.", evidence_refs=["E1"], confidence="high")],
        evidence_set_hash="hash-partial-contract",
        created_at=datetime.now(timezone.utc),
    )
    verifier = service._deterministic_verify(
        run=SimpleNamespace(id="run-partial-contract", user_id=7, message="Welke asset bekijk ik nu?", conversation_id="conv-1"),
        orchestrator_result=SimpleNamespace(
            analysis=SimpleNamespace(
                subject_scopes=["asset"],
                request_plan=RequestPlan(operation_id="read_active_asset", interaction_mode="READ"),
            ),
            selected_clarification=None,
        ),
        policy=SimpleNamespace(allowed=True, proposal_allowed=True, confirmation_required=False, operation_type=None),
        context=SimpleNamespace(
            evidence=[SimpleNamespace(evidence_id="E1", domain="identity_context", tool_name="read_active_asset", information_scope="active_asset", entity_type="asset", entity_id="BTC", asset="BTC", freshness="fresh", availability="available", confidence="high", facts={"symbol": "BTC"})],
            uncertainty_codes=[],
        ),
        validation=SimpleNamespace(id="validation-partial-contract", evidence_set_hash="hash-partial-contract", integrity_status="valid"),
        draft=draft,
        repair_attempt=0,
        force_action="reject",
    )

    assert verifier.passed is False
    assert "operation_contract_metadata_missing" in verifier.reason_codes


def test_scope_coverage_allows_setup_proposal_when_identity_context_is_sufficient():
    service = FinnV2ResponseVerifierService(session=object())
    draft = ResponseDraft(
        draft_id="draft-setup-proposal",
        run_id="run-setup-proposal",
        user_id=7,
        mode="CREATE_PROPOSAL",
        direct_answer="Ik kan een concept-setup voor BTC voorbereiden met 4H als primair timeframe.",
        main_observation="Deze setup is nog niet opgeslagen; het gaat om een voorstel dat eerst bevestigd moet worden.",
        claims=[],
        proposal_candidate=ProposalCandidate(
            operation_type="create_setup",
            target_type="setup",
            target_id=None,
            asset="BTC",
            proposed_changes={"setup_fields": {"symbol": "BTC", "timeframe": "4H"}},
            evidence_refs=["E1"],
            impact_summary="Er wordt een nieuwe BTC-setup voorbereid na bevestiging.",
            risk_summary="De setup wordt pas opgeslagen na bevestiging.",
            confirmation_required=True,
        ),
        evidence_set_hash="hash-setup",
        created_at=datetime.now(timezone.utc),
    )
    verifier = service._deterministic_verify(
        run=SimpleNamespace(id="run-setup-proposal", user_id=7, message="Maak een setup voor BTC swing trading met daily trend en 4H entry.", conversation_id="conv-1"),
        orchestrator_result=SimpleNamespace(
            analysis=SimpleNamespace(
                subject_scopes=["setup"],
                request_plan=RequestPlan(
                    operation_id="create_setup",
                    operation_contract_version=CONTRACT_VERSION,
                    interaction_mode="CREATE_PROPOSAL",
                    required_information_scopes=["active_asset"],
                    requested_operation="create_setup",
                ),
            ),
            selected_clarification=None,
        ),
        policy=SimpleNamespace(allowed=True, proposal_allowed=True, confirmation_required=True, operation_type=None),
        context=SimpleNamespace(
                evidence=[SimpleNamespace(evidence_id="E1", domain="identity_context", tool_name="read_active_asset", information_scope="active_asset", entity_type="asset", entity_id="BTC", asset="BTC", freshness="fresh", availability="available", confidence="high", facts={"symbol": "BTC"})],
            uncertainty_codes=[],
        ),
        validation=SimpleNamespace(id="validation-setup", evidence_set_hash="hash-setup", integrity_status="valid"),
        draft=draft,
        repair_attempt=0,
    )

    assert verifier.coverage.coverage_ok is True
    assert "response_scope_incomplete" not in verifier.reason_codes


def test_scope_coverage_uses_top_level_model_evidence_references():
    service = FinnV2ResponseVerifierService(session=object())
    draft = ResponseDraft(
        draft_id="draft-model-refs",
        run_id="run-model-refs",
        user_id=7,
        mode="EVALUATE",
        direct_answer="Je BTC-plan bevat setup 293, strategie 309 en bot 170.",
        main_observation="Je swing_trader-profiel gebruikt RSI en volume voor BTC.",
        claims=[],
        evidence_refs_used=["E1", "E2", "E3", "E4", "E5"],
        next_step=ReasoningNextStep(
            title="Leg je beslisregel vast",
            instruction="Leg vast wanneer RSI en volume samen je BTC-setup bevestigen.",
            operation_type=None,
            target_entity_type="setup",
            target_entity_id="293",
            requires_confirmation=False,
        ),
        evidence_set_hash="hash-model-refs",
        created_at=datetime.now(timezone.utc),
    )
    evidence = [
        SimpleNamespace(evidence_id="E1", domain="identity_context", tool_name="read_profile", entity_type="profile", entity_id="7", asset=None, freshness="fresh", confidence="high", facts={"trader_profile": {"trader_types": ["swing_trader"]}}),
        SimpleNamespace(evidence_id="E2", domain="market_context", tool_name="read_indicator_configuration", entity_type="indicator_configuration", entity_id=None, asset="BTC", freshness="fresh", confidence="high", facts={"configured_indicators": [{"indicator": "rsi"}]}),
        SimpleNamespace(evidence_id="E3", domain="plan_context", tool_name="read_active_setup", entity_type="setup", entity_id="293", asset="BTC", freshness="fresh", confidence="high", facts={"setup_id": 293}),
        SimpleNamespace(evidence_id="E4", domain="plan_context", tool_name="read_linked_strategy", entity_type="strategy", entity_id="309", asset="BTC", freshness="fresh", confidence="high", facts={"strategy_id": 309}),
        SimpleNamespace(evidence_id="E5", domain="automation_context", tool_name="read_linked_bot", entity_type="bot", entity_id="170", asset="BTC", freshness="fresh", confidence="high", facts={"bot_id": 170}),
    ]

    verifier = service._deterministic_verify(
        run=SimpleNamespace(id="run-model-refs", user_id=7, message="Bekijk mijn profiel, indicatoren, setup, strategie en gekoppelde bot. Geef een observatie en vervolgstap.", conversation_id="conv-1"),
        orchestrator_result=SimpleNamespace(analysis=SimpleNamespace(subject_scopes=["profile", "indicators", "setup", "strategy", "bot"]), selected_clarification=None),
        policy=SimpleNamespace(allowed=True, proposal_allowed=False, confirmation_required=False, operation_type=None),
        context=SimpleNamespace(evidence=evidence, uncertainty_codes=[]),
        validation=SimpleNamespace(id="validation-model-refs", evidence_set_hash="hash-model-refs", integrity_status="valid"),
        draft=draft,
        repair_attempt=0,
    )

    assert verifier.coverage.coverage_ok is True
    assert "response_scope_incomplete" not in verifier.reason_codes


def test_integrated_evaluation_does_not_pass_when_model_reasoning_contract_failed():
    service = FinnV2ResponseVerifierService(session=object())
    draft = ResponseDraft(
        draft_id="draft-invalid-model", run_id="run-invalid-model", user_id=7, mode="EVALUATE",
        direct_answer="Je balanced profiel met RSI, setup 293, strategie 309 en bot 170 heeft een duidelijke vervolgstap.",
        main_observation="Leg de regel vast.", claims=[], evidence_refs_used=["E1", "E2", "E3", "E4", "E5"],
        evidence_set_hash="hash-invalid-model", reasoning_provenance={"provider_called": True, "validation_status": "failed"},
        created_at=datetime.now(timezone.utc),
    )
    evidence = [
        SimpleNamespace(evidence_id="E1", domain="identity_context", tool_name="read_profile", entity_type="profile", entity_id="7", asset=None, freshness="fresh", confidence="high", facts={"trader_profile": {"risk_profile": "balanced"}}),
        SimpleNamespace(evidence_id="E2", domain="market_context", tool_name="read_indicator_configuration", entity_type="indicator_configuration", entity_id=None, asset="BTC", freshness="fresh", confidence="high", facts={"configured_indicators": [{"indicator": "rsi"}]}),
        SimpleNamespace(evidence_id="E3", domain="plan_context", tool_name="read_active_setup", entity_type="setup", entity_id="293", asset="BTC", freshness="fresh", confidence="high", facts={"setup_id": 293}),
        SimpleNamespace(evidence_id="E4", domain="plan_context", tool_name="read_linked_strategy", entity_type="strategy", entity_id="309", asset="BTC", freshness="fresh", confidence="high", facts={"strategy_id": 309}),
        SimpleNamespace(evidence_id="E5", domain="automation_context", tool_name="read_linked_bot", entity_type="bot", entity_id="170", asset="BTC", freshness="fresh", confidence="high", facts={"bot_id": 170}),
    ]
    verifier = service._deterministic_verify(
        run=SimpleNamespace(id="run-invalid-model", user_id=7, message="Bekijk mijn profiel, indicatoren, setup, strategie en gekoppelde bot. Geef een observatie en vervolgstap.", conversation_id="conv-1"),
        orchestrator_result=SimpleNamespace(analysis=SimpleNamespace(subject_scopes=["profile", "indicators", "setup", "strategy", "bot"]), selected_clarification=None),
        policy=SimpleNamespace(allowed=True, proposal_allowed=False, confirmation_required=False, operation_type=None),
        context=SimpleNamespace(evidence=evidence, uncertainty_codes=[]),
        validation=SimpleNamespace(id="validation-invalid-model", evidence_set_hash="hash-invalid-model", integrity_status="valid"),
        draft=draft,
        repair_attempt=0,
    )

    assert verifier.passed is False
    assert "model_reasoning_contract_failed" in verifier.reason_codes


def test_evidence_limited_evaluation_is_not_treated_as_a_model_contract_bypass():
    service = FinnV2ResponseVerifierService(session=object())
    draft = ResponseDraft(
        draft_id="draft-evidence-limited", run_id="run-evidence-limited", user_id=7, mode="EVALUATE",
        direct_answer="De beschikbare evidence bevestigt je opgeslagen planonderdelen, maar bewijst geen betrouwbaar causaal zwak punt.",
        main_observation="De beschikbare gegevens bewijzen geen direct verband tussen een opgeslagen veld en een plantekort.",
        # An evidence-limited result may cite the complete ledger without
        # inventing a factual claim that one isolated artifact cannot entail.
        claims=[],
        evidence_refs_used=["E1", "E2", "E3", "E4", "E5"],
        evidence_set_hash="hash-evidence-limited",
        reasoning_provenance={
            "provider_called": True,
            "reasoning_source": "contract_evidence_limitation",
            "validation_status": "evidence_limited",
        },
        created_at=datetime.now(timezone.utc),
    )
    evidence = [
        SimpleNamespace(evidence_id="E1", domain="identity_context", tool_name="read_profile", entity_type="profile", entity_id="7", asset=None, freshness="fresh", confidence="high", facts={"trader_profile": {"risk_profile": "balanced"}}),
        SimpleNamespace(evidence_id="E2", domain="market_context", tool_name="read_indicator_configuration", entity_type="indicator_configuration", entity_id=None, asset="BTC", freshness="fresh", confidence="high", facts={"configured_indicators": [{"indicator": "rsi"}]}),
        SimpleNamespace(evidence_id="E3", domain="plan_context", tool_name="read_active_setup", entity_type="setup", entity_id="293", asset="BTC", freshness="fresh", confidence="high", facts={"setup_id": 293}),
        SimpleNamespace(evidence_id="E4", domain="plan_context", tool_name="read_linked_strategy", entity_type="strategy", entity_id="309", asset="BTC", freshness="fresh", confidence="high", facts={"strategy_id": 309}),
        SimpleNamespace(evidence_id="E5", domain="automation_context", tool_name="read_linked_bot", entity_type="bot", entity_id="170", asset="BTC", freshness="fresh", confidence="high", facts={"bot_id": 170}),
    ]

    verifier = service._deterministic_verify(
        run=SimpleNamespace(id="run-evidence-limited", user_id=7, message="Beoordeel mijn plan.", conversation_id="conv-1"),
        orchestrator_result=SimpleNamespace(analysis=SimpleNamespace(subject_scopes=["profile", "indicators", "setup", "strategy", "bot"]), selected_clarification=None),
        policy=SimpleNamespace(allowed=True, proposal_allowed=False, confirmation_required=False, operation_type=None),
        context=SimpleNamespace(evidence=evidence, uncertainty_codes=[]),
        validation=SimpleNamespace(id="validation-evidence-limited", evidence_set_hash="hash-evidence-limited", integrity_status="valid"),
        draft=draft,
        repair_attempt=1,
    )

    assert "model_reasoning_contract_failed" not in verifier.reason_codes
    assert verifier.coverage.coverage_ok is True
    assert verifier.passed is True
    assert verifier.action == "deliver"


def test_mode_purity_accepts_not_executed_watchlist_proposal_wording():
    service = FinnV2ResponseVerifierService(session=object())
    draft = ResponseDraft(
        draft_id="draft-watchlist-proposal",
        run_id="run-watchlist-proposal",
        user_id=7,
        mode="ACTION_PROPOSAL",
        direct_answer="Ik kan ETH aan je watchlist toevoegen na je bevestiging.",
        main_observation="De wijziging is nog niet uitgevoerd; ik heb alleen een voorstel voor ETH voorbereid.",
        claims=[],
        evidence_set_hash="hash-watch",
        created_at=datetime.now(timezone.utc),
    )

    assert service._mode_purity_ok(draft) is True


def test_mode_purity_allows_read_response_to_reference_stored_order_reasoning():
    service = FinnV2ResponseVerifierService(session=object())
    draft = ResponseDraft(
        draft_id="draft-bot-read",
        run_id="run-bot-read",
        user_id=7,
        mode="READ",
        direct_answer="Wat ik zeker weet: bot 170 is gekoppeld, actief en niet live.",
        main_observation="Wat ik nog niet bevestigd kan afleiden: deze evidence bevat geen opgeslagen order- of positiereden die exact verklaart waarom nog geen positie is geopend.",
        claims=[],
        evidence_set_hash="hash-bot-read",
        created_at=datetime.now(timezone.utc),
    )

    assert service._mode_purity_ok(draft) is True


def test_blocked_live_bot_unavailable_is_not_marked_as_paper_live_mismatch():
    service = FinnV2ResponseVerifierService(session=object())
    draft = ResponseDraft(
        draft_id="draft-live-blocked",
        run_id="run-live-blocked",
        user_id=7,
        mode="UNAVAILABLE",
        direct_answer="Ik kan deze bot niet live activeren.",
        main_observation="De live-activatie blijft geblokkeerd door de actieve safety- en policycontroles.",
        claims=[],
        evidence_set_hash="hash-live-blocked",
        created_at=datetime.now(timezone.utc),
    )

    assert service._paper_live_mismatch(
        draft,
        {
            "E1": SimpleNamespace(facts={"is_live": False}),
        },
    ) is False


def test_read_response_marks_strategy_scope_from_linked_strategy_evidence():
    service = FinnV2ResponseVerifierService(session=object())
    draft = ResponseDraft(
        draft_id="draft-strategy-read",
        run_id="run-strategy-read",
        user_id=7,
        mode="READ",
        direct_answer="De belangrijkste expliciet opgeslagen entryvoorwaarde in je BTC-strategie 309 is nu een limit entry rond 62000.",
        main_observation="Wat nog niet bevestigd kan worden, is een extra entryfilter voor BTC.",
        claims=[
            ResponseClaim(
                claim_id="strategy-status",
                claim_type="fact",
                text="Strategie 309 voor setup 293 gebruikt execution_mode fixed.",
                evidence_refs=["E1"],
                confidence="high",
            )
        ],
        evidence_set_hash="hash-strategy-read",
        created_at=datetime.now(timezone.utc),
    )

    verifier = service._deterministic_verify(
        run=SimpleNamespace(id="run-strategy-read", user_id=7, message="Welke belangrijkste entryvoorwaarde uit mijn BTC-strategie moet bevestigd zijn voordat mijn plan een entry toestaat?", conversation_id="conv-1"),
        orchestrator_result=SimpleNamespace(analysis=SimpleNamespace(subject_scopes=["strategy"]), selected_clarification=None),
        policy=SimpleNamespace(allowed=True, proposal_allowed=False, confirmation_required=False, operation_type=None),
        context=SimpleNamespace(
            evidence=[SimpleNamespace(evidence_id="E1", domain="plan_context", tool_name="read_linked_strategy", entity_type="strategy", entity_id="309", asset="BTC", freshness="fresh", confidence="high", facts={"strategy_id": 309, "symbol": "BTC"})],
            uncertainty_codes=[],
        ),
        validation=SimpleNamespace(id="validation-strategy-read", evidence_set_hash="hash-strategy-read", integrity_status="valid"),
        draft=draft,
        repair_attempt=0,
    )

    assert verifier.coverage.coverage_ok is True
    assert verifier.relevance_ok is True
    assert "response_scope_incomplete" not in verifier.reason_codes
    assert "response_not_answering_question" not in verifier.reason_codes


def test_not_live_read_response_is_not_marked_as_live_mismatch():
    service = FinnV2ResponseVerifierService(session=object())
    draft = ResponseDraft(
        draft_id="draft-not-live-read",
        run_id="run-not-live-read",
        user_id=7,
        mode="READ",
        direct_answer="Wat ik zeker weet over je BTC-bot: bot 170 is gekoppeld, actief en niet live.",
        main_observation="Wat ik nog niet bevestigd kan worden, is waarom nog geen positie is geopend.",
        claims=[],
        evidence_set_hash="hash-not-live-read",
        created_at=datetime.now(timezone.utc),
    )

    assert service._paper_live_mismatch(
        draft,
        {
            "E1": SimpleNamespace(facts={"is_live": False}),
        },
    ) is False


def test_gate5_evaluation_rejects_generic_response_when_profile_and_indicator_grounding_exist():
    service = FinnV2ResponseVerifierService(session=object())
    draft = ResponseDraft(
        draft_id="draft-gate5-generic",
        run_id="run-gate5-generic",
        user_id=7,
        mode="EVALUATE",
        direct_answer="Het belangrijkste ontbrekende onderdeel van je plan is meer context.",
        main_observation="Je plan kan nog sterker worden met een duidelijker beoordelingskader.",
        claims=[
            ResponseClaim(
                claim_id="C1",
                claim_type="evaluation",
                text="Het plan mist nog context.",
                evidence_refs=["E1", "E2", "E3", "E4", "E5"],
                confidence="medium",
            )
        ],
        next_step=ReasoningNextStep(
            title="Werk je plan bij",
            instruction="Voeg één vervolgstap toe.",
            operation_type=None,
            target_entity_type="setup",
            target_entity_id="295",
            requires_confirmation=False,
        ),
        evidence_set_hash="hash-gate5",
        created_at=datetime.now(timezone.utc),
    )

    verifier = service._deterministic_verify(
        run=SimpleNamespace(
            id="run-gate5-generic",
            user_id=7,
            message="Bekijk mijn profiel, indicatoren, setup, strategie en gekoppelde bot. Wat is volgens jou op dit moment het belangrijkste ontbrekende onderdeel van mijn plan? Geef één concrete observatie en één vervolgstap.",
            conversation_id="conv-g5",
        ),
        orchestrator_result=SimpleNamespace(
            analysis=SimpleNamespace(subject_scopes=["profile", "indicators", "setup", "strategy", "bot"]),
            selected_clarification=None,
        ),
        policy=SimpleNamespace(allowed=True, proposal_allowed=False, confirmation_required=False, operation_type=None),
        context=SimpleNamespace(
            evidence=[
                SimpleNamespace(
                    evidence_id="E1",
                    domain="identity_context",
                    tool_name="read_profile",
                    entity_type="profile",
                    entity_id="7",
                    asset=None,
                    freshness="fresh",
                    confidence="high",
                    facts={"has_profile": True, "trader_profile": {"style": ["swing"], "risk_profile": "balanced"}},
                ),
                SimpleNamespace(
                    evidence_id="E2",
                    domain="market_context",
                    tool_name="read_indicator_configuration",
                    entity_type="indicator_configuration",
                    entity_id=None,
                    asset="BTC",
                    freshness="fresh",
                    confidence="high",
                    facts={
                        "symbol": "BTC",
                        "technical": [{"indicator": "RSI"}],
                        "market": [{"indicator": "funding_rate"}],
                        "macro": [],
                        "configured_indicators": [
                            {"indicator": "RSI", "category": "technical"},
                            {"indicator": "funding_rate", "category": "market"},
                        ],
                    },
                ),
                SimpleNamespace(
                    evidence_id="E3",
                    domain="plan_context",
                    tool_name="read_active_setup",
                    entity_type="setup",
                    entity_id="295",
                    asset="BTC",
                    freshness="fresh",
                    confidence="high",
                    facts={"setup_id": 295, "name": "BTC Swing 4H Gate Setup", "timeframe": "4H", "symbol": "BTC"},
                ),
                SimpleNamespace(
                    evidence_id="E4",
                    domain="plan_context",
                    tool_name="read_linked_strategy",
                    entity_type="strategy",
                    entity_id="311",
                    asset="BTC",
                    freshness="fresh",
                    confidence="high",
                    facts={"strategy_id": 311, "setup_id": 295, "symbol": "BTC"},
                ),
                SimpleNamespace(
                    evidence_id="E5",
                    domain="automation_context",
                    tool_name="read_linked_bot",
                    entity_type="bot",
                    entity_id="172",
                    asset="BTC",
                    freshness="fresh",
                    confidence="high",
                    facts={"bot_id": 172, "strategy_id": 311, "is_live": False},
                ),
            ],
            uncertainty_codes=[],
        ),
        validation=SimpleNamespace(id="validation-gate5", evidence_set_hash="hash-gate5", integrity_status="valid"),
        draft=draft,
        repair_attempt=0,
    )

    assert verifier.passed is False
    assert "response_insufficiently_personalized" in verifier.reason_codes
