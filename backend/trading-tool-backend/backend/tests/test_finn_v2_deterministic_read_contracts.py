from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from backend.schemas.finn_v2_orchestrator_schema import RequestPlan
from backend.schemas.finn_v2_reasoning_context_schema import (
    ReasoningContextPackage,
    ReasoningEvidenceItem,
    ReasoningPolicyContext,
)
from backend.schemas.finn_v2_response_schema import ResponseDraft
from backend.domain.finn_v2_operation_registry import FinnV2OperationRegistry
from backend.services.finn_v2_reasoning_fallback_service import FinnV2ReasoningFallbackService
from backend.services.finn_v2_reasoning_context_service import FinnV2ReasoningContextService
from backend.services.finn_v2_response_verifier_service import FinnV2ResponseVerifierService
from backend.schemas.finn_v2_evidence_schema import parse_tool_payload
from backend.services.finn_v2_tool_adapters.setup_tool_adapter import SetupToolAdapter


def _context(*, operation_id, required_scope, message, evidence, locale="nl-NL"):
    required_scopes = required_scope if isinstance(required_scope, list) else [required_scope]
    return ReasoningContextPackage(
        run_id="run-read-contract",
        user_id=406,
        user_message=message,
        locale=locale,
        interaction_mode="READ",
        subject_scopes=required_scopes,
        required_domains=[],
        orchestrator_result_id="orchestrator-read-contract",
        snapshot_id="snapshot-read-contract",
        validation_id="validation-read-contract",
        policy_decision_id="policy-read-contract",
        evidence_set_hash="read-contract-hash",
        evidence=evidence,
        policy=ReasoningPolicyContext(
            policy_class="read_only",
            allowed=True,
            proposal_allowed=False,
            confirmation_required=False,
            step_up_required=False,
            execution_allowed=False,
        ),
        request_plan={
            "operation_id": operation_id,
            "required_information_scopes": required_scopes,
        },
    )


@pytest.mark.parametrize(
    ("operation_id", "required_scope", "message", "evidence"),
    [
        (
            "read_active_asset",
            "active_asset",
            "Wat is mijn actieve asset?",
            [
                ReasoningEvidenceItem(
                    evidence_id="Easset",
                    artifact_id="artifact-asset",
                    tool_name="read_active_asset",
                    information_scope="active_asset",
                    domain="identity_context",
                    entity_type="asset",
                    entity_id="BTC",
                    asset="BTC",
                    source="workspace",
                    freshness="fresh",
                    confidence="high",
                    facts={"symbol": "BTC", "asset_class": "crypto"},
                )
            ],
        ),
        (
            "read_indicator_configuration",
            ["active_asset", "indicator_configuration"],
            "Welke indicatoren staan voor BTC ingesteld?",
            [
                ReasoningEvidenceItem(
                    evidence_id="Easset",
                    artifact_id="artifact-active-asset",
                    tool_name="read_active_asset",
                    information_scope="active_asset",
                    domain="identity_context",
                    entity_type="asset",
                    asset="BTC",
                    source="workspace",
                    freshness="fresh",
                    confidence="high",
                    facts={"symbol": "BTC", "asset_class": "crypto"},
                ),
                ReasoningEvidenceItem(
                    evidence_id="Econfig",
                    artifact_id="artifact-indicators",
                    tool_name="read_indicator_configuration",
                    information_scope="indicator_configuration",
                    domain="market_context",
                    entity_type="indicator_configuration",
                    asset="BTC",
                    source="user_indicator_rule_overrides",
                    freshness="fresh",
                    confidence="high",
                    facts={
                        "symbol": "BTC",
                        "configured_count": 3,
                        "configured_indicators": [
                            {"category": "market", "indicator": "volume"},
                            {"category": "technical", "indicator": "rsi"},
                            {"category": "technical", "indicator": "ma_200"},
                        ],
                    },
                )
            ],
        ),
    ],
)
def test_registry_read_contracts_carry_required_evidence_into_verifier(
    operation_id, required_scope, message, evidence
):
    required_scopes = required_scope if isinstance(required_scope, list) else [required_scope]
    context = _context(
        operation_id=operation_id,
        required_scope=required_scope,
        message=message,
        evidence=evidence,
    )
    reasoning = FinnV2ReasoningFallbackService().grounded_read_draft(
        run_id=context.run_id,
        user_id=context.user_id,
        context=context,
        model="deterministic",
        error_codes=[],
    )
    draft = ResponseDraft(
        draft_id="draft-read-contract",
        run_id=context.run_id,
        user_id=context.user_id,
        mode=reasoning.mode,
        direct_answer=reasoning.direct_answer,
        main_observation=reasoning.main_observation,
        claims=reasoning.claims,
        uncertainty_summary=reasoning.uncertainty_summary,
        uncertainty_codes=reasoning.uncertainty_codes,
        evidence_refs_used=reasoning.evidence_refs_used,
        evidence_set_hash=context.evidence_set_hash,
        created_at=datetime.now(timezone.utc),
    )
    verifier = FinnV2ResponseVerifierService(session=object())._deterministic_verify(
        run=SimpleNamespace(id=context.run_id, user_id=context.user_id, message=message, conversation_id="conversation-read-contract"),
        orchestrator_result=SimpleNamespace(
            analysis=SimpleNamespace(
                subject_scopes=required_scopes,
                request_plan=RequestPlan(
                    interaction_mode="READ",
                    required_information_scopes=required_scopes,
                    operation_id=operation_id,
                    operation_contract_version=FinnV2OperationRegistry.VERSION,
                ),
            ),
            selected_clarification=None,
        ),
        policy=SimpleNamespace(allowed=True, proposal_allowed=False, confirmation_required=False, operation_type=None),
        context=SimpleNamespace(evidence=evidence, uncertainty_codes=[]),
        validation=SimpleNamespace(id="validation-read-contract", evidence_set_hash=context.evidence_set_hash, integrity_status="valid"),
        draft=draft,
        repair_attempt=0,
        force_action="deliver",
    )

    assert reasoning.evidence_refs_used
    assert reasoning.claims
    assert verifier.coverage.coverage_ok is True
    assert verifier.passed is True


def test_linked_bot_read_preserves_the_complete_registry_graph_for_delivery():
    required_scopes = ["active_asset", "active_setup", "linked_strategy", "linked_bot", "bot_status"]
    evidence = [
        ReasoningEvidenceItem(evidence_id="Easset", artifact_id="asset", tool_name="read_active_asset", information_scope="active_asset", domain="identity_context", entity_type="asset", entity_id="BTC", asset="BTC", source="workspace", freshness="fresh", confidence="high", facts={"symbol": "BTC"}),
        ReasoningEvidenceItem(evidence_id="Esetup", artifact_id="setup", tool_name="read_active_setup", information_scope="active_setup", domain="plan_context", entity_type="setup", entity_id="309", asset="BTC", source="setups", freshness="fresh", confidence="high", facts={"setup_id": 309, "name": "BTC swing", "timeframe": "4H", "symbol": "BTC"}),
        ReasoningEvidenceItem(evidence_id="Estrat", artifact_id="strategy", tool_name="read_linked_strategy", information_scope="linked_strategy", domain="plan_context", entity_type="strategy", entity_id="325", asset="BTC", source="strategies", freshness="fresh", confidence="high", facts={"strategy_id": 325, "setup_id": 309, "name": "BTC Fixed"}),
        ReasoningEvidenceItem(evidence_id="Ebot", artifact_id="bot", tool_name="read_linked_bot", information_scope="linked_bot", domain="automation_context", entity_type="bot", entity_id="186", asset="BTC", source="bot_configs", freshness="fresh", confidence="high", facts={"bot_id": 186, "strategy_id": 325, "name": "BTC Paper"}),
        ReasoningEvidenceItem(evidence_id="Estatus", artifact_id="status", tool_name="read_bot_status", information_scope="bot_status", domain="automation_context", entity_type="bot_status", entity_id="186", asset="BTC", source="bot_configs", freshness="fresh", confidence="high", facts={"bot_id": 186, "is_live": False}),
    ]
    context = _context(
        operation_id="read_linked_bot",
        required_scope=required_scopes,
        message="Welke setup, strategie en bot heb ik voor mijn actieve asset?",
        evidence=evidence,
    )
    reasoning = FinnV2ReasoningFallbackService().grounded_read_draft(
        run_id=context.run_id, user_id=context.user_id, context=context, model="deterministic", error_codes=[]
    )
    assert reasoning.mode == "READ"
    assert {"Easset", "Esetup", "Estrat", "Ebot", "Estatus"}.issubset(reasoning.evidence_refs_used)
    assert "strategie BTC Fixed" in reasoning.direct_answer
    assert "bot BTC Paper" in reasoning.direct_answer
    assert "325" not in reasoning.direct_answer
    assert "186" not in reasoning.direct_answer


def test_linked_bot_budget_read_mentions_the_typed_persisted_budget():
    required_scopes = ["active_asset", "active_setup", "linked_strategy", "linked_bot", "bot_status"]
    evidence = [
        ReasoningEvidenceItem(evidence_id="Easset", artifact_id="asset", tool_name="read_active_asset", information_scope="active_asset", domain="identity_context", entity_type="asset", entity_id="BTC", asset="BTC", source="workspace", freshness="fresh", confidence="high", facts={"symbol": "BTC"}),
        ReasoningEvidenceItem(evidence_id="Esetup", artifact_id="setup", tool_name="read_active_setup", information_scope="active_setup", domain="plan_context", entity_type="setup", entity_id="309", asset="BTC", source="setups", freshness="fresh", confidence="high", facts={"setup_id": 309, "name": "BTC swing", "timeframe": "4H", "symbol": "BTC"}),
        ReasoningEvidenceItem(evidence_id="Estrat", artifact_id="strategy", tool_name="read_linked_strategy", information_scope="linked_strategy", domain="plan_context", entity_type="strategy", entity_id="325", asset="BTC", source="strategies", freshness="fresh", confidence="high", facts={"strategy_id": 325, "setup_id": 309, "name": "BTC Fixed"}),
        ReasoningEvidenceItem(evidence_id="Ebot", artifact_id="bot", tool_name="read_linked_bot", information_scope="linked_bot", domain="automation_context", entity_type="bot", entity_id="186", asset="BTC", source="bot_configs", freshness="fresh", confidence="high", facts={"bot_id": 186, "strategy_id": 325, "name": "BTC Paper", "budget_total_eur": 1000.0}),
        ReasoningEvidenceItem(evidence_id="Estatus", artifact_id="status", tool_name="read_bot_status", information_scope="bot_status", domain="automation_context", entity_type="bot_status", entity_id="186", asset="BTC", source="bot_configs", freshness="fresh", confidence="high", facts={"bot_id": 186, "is_live": False}),
    ]
    context = _context(
        operation_id="read_linked_bot",
        required_scope=required_scopes,
        message="Wat is het huidige budget van mijn paper-bot?",
        evidence=evidence,
    )

    reasoning = FinnV2ReasoningFallbackService().grounded_read_draft(
        run_id=context.run_id, user_id=context.user_id, context=context, model="deterministic", error_codes=[]
    )

    assert "€1.000" in reasoning.direct_answer
    assert "BTC Paper" in reasoning.direct_answer
    assert "BTC Fixed" in reasoning.direct_answer
    assert "BTC op timeframe 4H" in reasoning.direct_answer
    assert "186" not in reasoning.direct_answer


def test_bot_status_budget_read_mentions_budget_and_live_state():
    required_scopes = ["active_asset", "active_setup", "linked_strategy", "linked_bot", "bot_status"]
    evidence = [
        ReasoningEvidenceItem(evidence_id="Easset", artifact_id="asset", tool_name="read_active_asset", information_scope="active_asset", domain="identity_context", entity_type="asset", entity_id="BTC", asset="BTC", source="workspace", freshness="fresh", confidence="high", facts={"symbol": "BTC"}),
        ReasoningEvidenceItem(evidence_id="Esetup", artifact_id="setup", tool_name="read_active_setup", information_scope="active_setup", domain="plan_context", entity_type="setup", entity_id="309", asset="BTC", source="setups", freshness="fresh", confidence="high", facts={"setup_id": 309, "name": "BTC swing", "timeframe": "4H", "symbol": "BTC"}),
        ReasoningEvidenceItem(evidence_id="Estrat", artifact_id="strategy", tool_name="read_linked_strategy", information_scope="linked_strategy", domain="plan_context", entity_type="strategy", entity_id="325", asset="BTC", source="strategies", freshness="fresh", confidence="high", facts={"strategy_id": 325, "setup_id": 309, "name": "BTC Fixed"}),
        ReasoningEvidenceItem(evidence_id="Ebot", artifact_id="bot", tool_name="read_linked_bot", information_scope="linked_bot", domain="automation_context", entity_type="bot", entity_id="186", asset="BTC", source="bot_configs", freshness="fresh", confidence="high", facts={"bot_id": 186, "strategy_id": 325, "name": "BTC Paper", "budget_total_eur": 1000.0}),
        ReasoningEvidenceItem(evidence_id="Estatus", artifact_id="status", tool_name="read_bot_status", information_scope="bot_status", domain="automation_context", entity_type="bot_status", entity_id="186", asset="BTC", source="bot_configs", freshness="fresh", confidence="high", facts={"bot_id": 186, "is_live": False}),
    ]
    context = _context(
        operation_id="read_bot_status",
        required_scope=required_scopes,
        message="Welk budget heeft mijn paper-bot en staat hij live?",
        evidence=evidence,
    )

    reasoning = FinnV2ReasoningFallbackService().grounded_read_draft(
        run_id=context.run_id, user_id=context.user_id, context=context, model="deterministic", error_codes=[]
    )

    assert reasoning.direct_answer.startswith("Je paper-bot ‘BTC Paper’ is gekoppeld aan strategie BTC Fixed")
    assert "budget van €1.000" in reasoning.direct_answer
    assert "niet live" in reasoning.main_observation
    assert "setup 309" not in reasoning.direct_answer
    assert "strategie 325" not in reasoning.direct_answer


def test_active_setup_read_uses_persisted_name_type_and_timeframe_without_strategy_fields():
    evidence = [
        ReasoningEvidenceItem(evidence_id="Easset", artifact_id="asset", tool_name="read_active_asset", information_scope="active_asset", domain="identity_context", entity_type="asset", asset="BTC", source="workspace", freshness="fresh", confidence="high", facts={"symbol": "BTC"}),
        ReasoningEvidenceItem(evidence_id="Esetup", artifact_id="setup", tool_name="read_active_setup", information_scope="active_setup", domain="plan_context", entity_type="setup", entity_id="326", asset="BTC", source="setups", freshness="fresh", confidence="high", facts={"setup_id": 326, "name": "BTC 4H Trade", "setup_type": "trade", "timeframe": "4H", "symbol": "BTC"}),
    ]
    context = _context(
        operation_id="read_active_setup",
        required_scope=["active_asset", "active_setup"],
        message="Vat mijn setup samen.",
        evidence=evidence,
    )

    reasoning = FinnV2ReasoningFallbackService().grounded_read_draft(
        run_id=context.run_id, user_id=context.user_id, context=context, model="deterministic", error_codes=[]
    )

    assert "BTC 4H Trade" in reasoning.direct_answer
    assert "trade" in reasoning.direct_answer
    assert "4H" in reasoning.direct_answer


def test_setup_overview_read_names_every_owner_scoped_asset_setup():
    evidence = [
        ReasoningEvidenceItem(evidence_id="Easset", artifact_id="asset", tool_name="read_active_asset", information_scope="active_asset", domain="identity_context", entity_type="asset", asset="BTC", source="workspace", freshness="fresh", confidence="high", facts={"symbol": "BTC"}),
        ReasoningEvidenceItem(evidence_id="Esetups", artifact_id="setups", tool_name="read_active_setup", information_scope="active_setup", domain="plan_context", entity_type="setup", entity_id="326", asset="BTC", source="setups", freshness="fresh", confidence="high", facts={
            "setup_id": 326,
            "name": "BTC DCA",
            "symbol": "BTC",
            "timeframe": "4H",
            "setups": [
                {"setup_id": 326, "name": "BTC DCA", "symbol": "BTC", "timeframe": "4H"},
                {"setup_id": 327, "name": "BTC Swing", "symbol": "BTC", "timeframe": "1D"},
            ],
            "setup_count": 2,
        }),
    ]
    context = _context(
        operation_id="read_active_setup",
        required_scope=["active_asset", "active_setup"],
        message="Welke BTC setups heb ik?",
        evidence=evidence,
    )

    reasoning = FinnV2ReasoningFallbackService().grounded_read_draft(
        run_id=context.run_id, user_id=context.user_id, context=context, model="deterministic", error_codes=[]
    )

    assert "2 BTC-setups" in reasoning.direct_answer
    assert "BTC DCA (4H)" in reasoning.direct_answer
    assert "BTC Swing (1D)" in reasoning.direct_answer


def test_setup_overview_labels_multi_asset_collection_without_workspace_leak():
    evidence = [
        ReasoningEvidenceItem(evidence_id="Esetups", artifact_id="setups", tool_name="read_active_setup", information_scope="active_setup", domain="plan_context", entity_type="setup", entity_id="326", asset=None, source="setups", freshness="fresh", confidence="high", facts={
            "setups": [
                {"setup_id": 326, "name": "BTC DCA", "symbol": "BTC", "timeframe": "4H"},
                {"setup_id": 327, "name": "Apple Swing", "symbol": "AAPL", "timeframe": "1D"},
            ],
            "setup_count": 2,
        }),
    ]
    context = _context(
        operation_id="read_active_setup",
        required_scope=["active_setup"],
        message="Welke setups heb ik voor al mijn assets?",
        evidence=evidence,
    )

    reasoning = FinnV2ReasoningFallbackService().grounded_read_draft(
        run_id=context.run_id, user_id=context.user_id, context=context, model="deterministic", error_codes=[]
    )

    assert "2 setups" in reasoning.direct_answer
    assert "BTC DCA (BTC · 4H)" in reasoning.direct_answer
    assert "Apple Swing (AAPL · 1D)" in reasoning.direct_answer
    assert "BTC-setups" not in reasoning.direct_answer


def test_active_setup_strategy_fields_explain_missing_link_without_internal_verifier_code():
    evidence = [
        ReasoningEvidenceItem(evidence_id="Easset", artifact_id="asset", tool_name="read_active_asset", information_scope="active_asset", domain="identity_context", entity_type="asset", asset="BTC", source="workspace", freshness="fresh", confidence="high", facts={"symbol": "BTC"}),
        ReasoningEvidenceItem(evidence_id="Esetup", artifact_id="setup", tool_name="read_active_setup", information_scope="active_setup", domain="plan_context", entity_type="setup", entity_id="326", asset="BTC", source="setups", freshness="fresh", confidence="high", facts={"setup_id": 326, "name": "BTC 4H Trade", "setup_type": "trade", "timeframe": "4H", "symbol": "BTC"}),
    ]
    context = _context(
        operation_id="read_active_setup",
        required_scope=["active_asset", "active_setup"],
        message="Wat is mijn entryvoorwaarde en stop-loss voor deze setup?",
        evidence=evidence,
    )

    reasoning = FinnV2ReasoningFallbackService().grounded_read_draft(
        run_id=context.run_id, user_id=context.user_id, context=context, model="deterministic", error_codes=[]
    )

    assert "gekoppelde strategie" in reasoning.main_observation
    assert "response_field_incomplete" not in reasoning.direct_answer


@pytest.mark.parametrize(
    ("locale", "execution_label", "risk_label"),
    [
        ("nl-NL", "vast", "gebalanceerd"),
        ("en-US", "fixed", "balanced"),
        ("de-DE", "fest", "ausgewogen"),
    ],
)
def test_linked_strategy_read_renders_all_persisted_strategy_fields_without_ids(
    locale, execution_label, risk_label
):
    evidence = [
        ReasoningEvidenceItem(evidence_id="Esetup", artifact_id="setup", tool_name="read_active_setup", information_scope="active_setup", domain="plan_context", entity_type="setup", entity_id="326", asset="BTC", source="setups", freshness="fresh", confidence="high", facts={"setup_id": 326, "name": "BTC DCA", "timeframe": "4H", "symbol": "BTC"}),
        ReasoningEvidenceItem(evidence_id="Estrat", artifact_id="strategy", tool_name="read_linked_strategy", information_scope="linked_strategy", domain="plan_context", entity_type="strategy", entity_id="412", asset="BTC", source="strategies", freshness="fresh", confidence="high", facts={"strategy_id": 412, "setup_id": 326, "setup_name": "BTC DCA", "name": "BTC Fixed", "symbol": "BTC", "timeframe": "4H", "execution_mode": "fixed", "base_amount": 100, "entry": 76000, "stop_loss": 72000, "targets": [80000, 84000], "risk_profile": "balanced"}),
    ]
    context = _context(
        operation_id="read_linked_strategy",
        required_scope=["active_setup", "linked_strategy"],
        message="Vat mijn strategie samen met entry, stop-loss, targets en risico.",
        evidence=evidence,
        locale=locale,
    )

    reasoning = FinnV2ReasoningFallbackService().grounded_read_draft(
        run_id=context.run_id, user_id=context.user_id, context=context, model="deterministic", error_codes=[]
    )

    for expected in ("BTC Fixed", "BTC DCA", "4H", execution_label, "100", "76000", "72000", "80000", "84000", risk_label):
        assert expected in reasoning.direct_answer
    if locale == "nl-NL":
        assert "uitvoering fixed" not in reasoning.direct_answer
        assert "risico balanced" not in reasoning.direct_answer
    assert "412" not in reasoning.direct_answer
    assert "326" not in reasoning.direct_answer


def test_active_setup_context_preserves_the_persisted_setup_type():
    facts = FinnV2ReasoningContextService(session=object())._sanitize_facts(
        {
            "setup_id": 326,
            "name": "BTC 4H Trade",
            "symbol": "BTC",
            "timeframe": "4H",
            "setup_type": "trade",
        },
        "read_active_setup",
    )

    assert facts["setup_type"] == "trade"


def test_active_setup_collection_preserves_every_matching_setup_for_overview_reads():
    facts = FinnV2ReasoningContextService(session=object())._sanitize_facts(
        {
            "setup_id": 326,
            "name": "BTC DCA",
            "symbol": "BTC",
            "timeframe": "4H",
            "setup_type": "dca",
            "setups": [
                {"setup_id": 326, "name": "BTC DCA", "symbol": "BTC", "timeframe": "4H"},
                {"setup_id": 327, "name": "BTC Swing", "symbol": "BTC", "timeframe": "1D"},
            ],
        },
        "read_active_setup",
    )

    assert facts["setup_count"] == 2
    assert [setup["name"] for setup in facts["setups"]] == ["BTC DCA", "BTC Swing"]


def test_setup_collection_survives_the_persisted_evidence_schema():
    import asyncio

    result = asyncio.run(SetupToolAdapter().execute(
        setup={"id": 326, "name": "BTC DCA", "symbol": "BTC", "timeframe": "4H"},
        setups=[
            {"id": 326, "name": "BTC DCA", "symbol": "BTC", "timeframe": "4H"},
            {"id": 327, "name": "BTC Swing", "symbol": "BTC", "timeframe": "1D"},
        ],
        resolution_source="owner_setup_collection",
    ))
    persisted = parse_tool_payload(result["schema_name"], result["data"].dict())

    assert persisted.setup_count == 2
    assert [setup["name"] for setup in persisted.setups] == ["BTC DCA", "BTC Swing"]


def test_response_projection_makes_persisted_indicator_contract_fields_visible():
    draft = ResponseDraft(
        draft_id="draft-projection-indicators", run_id="run-projection-indicators", user_id=406,
        mode="READ", direct_answer="Je opgeslagen indicatorconfiguratie is beschikbaar.",
        main_observation="Ik heb de juiste asset-scoped evidence gebruikt.",
        evidence_set_hash="projection-hash", created_at=datetime.now(timezone.utc),
    )
    evidence = [
        SimpleNamespace(tool_name="read_active_asset", facts={"symbol": "BTC"}),
        SimpleNamespace(tool_name="read_indicator_configuration", facts={
            "symbol": "BTC", "configured_count": 2,
            "configured_indicators": [{"indicator": "RSI"}, {"indicator": "VWAP"}],
        }),
    ]
    projected = FinnV2ResponseVerifierService._project_required_response_fields(
        draft=draft,
        orchestrator_result=SimpleNamespace(analysis=SimpleNamespace(request_plan=SimpleNamespace(operation_id="read_indicator_configuration"))),
        context=SimpleNamespace(evidence=evidence),
    )
    assert "2 indicatorconfiguraties" in projected.direct_answer
    assert "RSI" in projected.direct_answer and "VWAP" in projected.direct_answer
    assert FinnV2ResponseVerifierService._covered_response_fields(
        draft=projected, evidence=evidence,
        required_fields=["asset", "configured_count", "indicator_names"],
    ) == ["asset", "configured_count", "indicator_names"]


def test_response_projection_preserves_an_empty_indicator_contract_as_complete():
    draft = ResponseDraft(
        draft_id="draft-projection-empty-indicators", run_id="run-projection-empty-indicators", user_id=406,
        mode="READ", direct_answer="Je opgeslagen indicatorconfiguratie is beschikbaar.",
        main_observation="Ik heb de juiste asset-scoped evidence gebruikt.",
        evidence_set_hash="projection-empty-hash", created_at=datetime.now(timezone.utc),
    )
    evidence = [
        SimpleNamespace(tool_name="read_active_asset", facts={"symbol": "BTC"}),
        SimpleNamespace(tool_name="read_indicator_configuration", facts={
            "symbol": "BTC", "configured_count": 0, "configured_indicators": [],
        }),
    ]

    projected = FinnV2ResponseVerifierService._project_required_response_fields(
        draft=draft,
        orchestrator_result=SimpleNamespace(analysis=SimpleNamespace(request_plan=SimpleNamespace(operation_id="read_indicator_configuration"))),
        context=SimpleNamespace(evidence=evidence),
    )

    assert "0 indicatorconfiguraties" in projected.direct_answer
    assert "geen indicatoren" in projected.direct_answer
    assert FinnV2ResponseVerifierService._covered_response_fields(
        draft=projected, evidence=evidence,
        required_fields=["asset", "configured_count", "indicator_names"],
    ) == ["asset", "configured_count", "indicator_names"]


def test_response_projection_makes_bot_and_status_visible():
    draft = ResponseDraft(
        draft_id="draft-projection-bot", run_id="run-projection-bot", user_id=406,
        mode="READ", direct_answer="Ik heb je botcontext gecontroleerd.",
        main_observation="De gekoppelde configuratie is beschikbaar.",
        evidence_set_hash="projection-hash", created_at=datetime.now(timezone.utc),
    )
    evidence = [
        SimpleNamespace(tool_name="read_linked_bot", facts={"bot_id": 170, "name": "BTC paper bot"}),
        SimpleNamespace(tool_name="read_bot_status", facts={"bot_id": 170, "is_live": False}),
    ]
    projected = FinnV2ResponseVerifierService._project_required_response_fields(
        draft=draft,
        orchestrator_result=SimpleNamespace(analysis=SimpleNamespace(request_plan=SimpleNamespace(operation_id="read_bot_status"))),
        context=SimpleNamespace(evidence=evidence),
    )
    assert "BTC paper bot staat niet live" in projected.direct_answer
    assert "170" not in projected.direct_answer
    assert FinnV2ResponseVerifierService._covered_response_fields(
        draft=projected, evidence=evidence, required_fields=["bot", "bot_status"],
    ) == ["bot", "bot_status"]


def test_response_projection_makes_setup_and_strategy_contract_fields_visible():
    draft = ResponseDraft(
        draft_id="draft-projection-plan",
        run_id="run-projection-plan",
        user_id=406,
        mode="READ",
        direct_answer="Ik heb je opgeslagen plancontext gevonden.",
        main_observation="De gegevens zijn owner-scoped geladen.",
        evidence_set_hash="projection-plan-hash",
        created_at=datetime.now(timezone.utc),
    )
    evidence = [
        SimpleNamespace(
            tool_name="read_active_setup",
            facts={
                "setup_id": 326,
                "name": "BTC 4H Trade",
                "setup_type": "trade",
                "timeframe": "4H",
            },
        ),
        SimpleNamespace(
            tool_name="read_linked_strategy",
            facts={
                "strategy_id": 412,
                "name": "BTC breakout",
                "symbol": "BTC",
                "timeframe": "4H",
                "execution_mode": "fixed",
            },
        ),
    ]

    projected = FinnV2ResponseVerifierService._project_required_response_fields(
        draft=draft,
        orchestrator_result=SimpleNamespace(
            analysis=SimpleNamespace(
                request_plan=SimpleNamespace(operation_id="read_linked_strategy")
            )
        ),
        context=SimpleNamespace(evidence=evidence),
    )

    assert "BTC 4H Trade" in projected.direct_answer
    assert "trade" in projected.direct_answer
    assert "BTC breakout" in projected.direct_answer
    assert "fixed" in projected.direct_answer
    assert FinnV2ResponseVerifierService._covered_response_fields(
        draft=projected,
        evidence=evidence,
        required_fields=["setup", "strategy"],
    ) == ["setup", "strategy"]


def test_evaluate_plan_projection_keeps_profile_and_indicator_grounding_visible():
    draft = ResponseDraft(
        draft_id="draft-evaluate-projection", run_id="run-evaluate-projection", user_id=406,
        mode="EVALUATE", direct_answer="De BTC-setup is actief.",
        main_observation="De bot staat niet live.", evidence_set_hash="projection-hash",
        created_at=datetime.now(timezone.utc),
    )
    evidence = [
        SimpleNamespace(tool_name="read_profile", facts={"trader_profile": {"risk_profile": "gematigd", "primary_timeframe": "4H"}}),
        SimpleNamespace(tool_name="read_indicator_configuration", facts={"configured_indicators": [{"indicator": "RSI"}, {"indicator": "VWAP"}]}),
    ]

    projected = FinnV2ResponseVerifierService._project_required_response_fields(
        draft=draft,
        orchestrator_result=SimpleNamespace(analysis=SimpleNamespace(request_plan=SimpleNamespace(operation_id="evaluate_plan"))),
        context=SimpleNamespace(evidence=evidence),
    )

    assert "gematigd" in projected.direct_answer
    assert "RSI" in projected.direct_answer and "VWAP" in projected.direct_answer
