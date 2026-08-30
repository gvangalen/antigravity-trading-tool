from pathlib import Path
import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace

from backend.schemas.finn_v2_response_schema import ResponseDraft
from backend.schemas.finn_v2_verifier_schema import CoverageVerification, VerifierResult
from backend.services.finn_v2_response_verifier_service import FinnV2ResponseVerifierService, FinnV2VerifierRejected


ROOT = Path(__file__).resolve().parents[1]


def test_verifier_persistence_is_append_only_and_versioned():
    verifier_repo = (ROOT / "infrastructure" / "repositories" / "finn_v2_verifier_repository.py").read_text(encoding="utf-8")
    verified_repo = (ROOT / "infrastructure" / "repositories" / "finn_v2_verified_response_repository.py").read_text(encoding="utf-8")
    migration_source = (ROOT / "scripts" / "migrations" / "2026_08_17_finn_v2_verified_delivery.py").read_text(encoding="utf-8")

    assert "async def create" in verifier_repo
    assert ".update(" not in verifier_repo
    assert "UNIQUE (run_id, response_version)" in migration_source
    assert "async def create" in verified_repo


def test_verifier_persistence_serializes_datetime_payloads():
    service = FinnV2ResponseVerifierService(session=object())
    verifier_captured = {}
    response_captured = {}

    async def _create_verifier(**kwargs):
        verifier_captured.update(kwargs)
        return SimpleNamespace(id=kwargs["id"])

    async def _create_verified(**kwargs):
        response_captured.update(kwargs)
        return SimpleNamespace(**kwargs)

    service.verifiers.create = _create_verifier
    service.verified.create = _create_verified

    run = SimpleNamespace(id="run-1", user_id=7)
    draft = ResponseDraft(
        draft_id="draft-1",
        run_id="run-1",
        user_id=7,
        mode="UNAVAILABLE",
        direct_answer="Niet beschikbaar.",
        main_observation="Er is nog geen veilige verified output.",
        supporting_points=[],
        claims=[],
        uncertainty_summary=None,
        uncertainty_codes=[],
        next_step=None,
        follow_up_question=None,
        proposal_candidate=None,
        reasoning_result_id="reasoning-1",
        evidence_set_hash="hash-1",
        created_at=datetime.now(timezone.utc),
    )
    verifier = VerifierResult(
        verifier_result_id="verifier-1",
        run_id="run-1",
        user_id=7,
        draft_id="draft-1",
        passed=True,
        action="deliver",
        claim_results=[],
        coverage=CoverageVerification(required_scopes=[], covered_scopes=[], missing_scopes=[], coverage_ok=True),
        schema_ok=True,
        ownership_ok=True,
        evidence_ok=True,
        relevance_ok=True,
        mode_purity_ok=True,
        uncertainty_ok=True,
        follow_up_ok=True,
        proposal_ok=True,
        policy_ok=True,
        safety_ok=True,
        reason_codes=[],
        semantic_verifier_used=False,
        created_at=datetime.now(timezone.utc),
    )

    persisted = asyncio.run(
        service._persist_verified_response(
            run=run,
            draft=draft,
            verifier=verifier,
            proposal_id=None,
            confirmation_required=False,
        )
    )

    assert isinstance(verifier_captured["result_json"]["created_at"], str)
    assert isinstance(response_captured["response_json"]["created_at"], str)
    assert persisted.created_at == response_captured["created_at"]


def test_verifier_rejects_indicator_configuration_as_a_causal_plan_judgment():
    service = FinnV2ResponseVerifierService(session=object())
    evidence = [
        SimpleNamespace(
            tool_name="read_indicator_configuration",
            facts={"configured_count": 0, "configured_indicators": []},
            asset="BTC",
        )
    ]

    support, reason_codes, supported = service._evaluate_claim_support(
        "De indicatorconfiguratie is een tekortkoming, omdat er geen indicatoren zijn ingesteld.",
        evidence,
        "evaluation",
    )

    assert support == "unsupported"
    assert reason_codes == ["unsupported_configuration_causality"]
    assert supported is False


def test_verifier_rejects_configuration_that_claims_to_weaken_a_strategy():
    service = FinnV2ResponseVerifierService(session=object())
    evidence = [
        SimpleNamespace(
            tool_name="read_indicator_configuration",
            facts={"configured_count": 0, "configured_indicators": []},
            asset="BTC",
        )
    ]

    support, reason_codes, supported = service._evaluate_claim_support(
        "De ontbrekende indicatorconfiguratie kan de onderbouwing van de strategie verzwakken.",
        evidence,
        "evaluation",
    )

    assert support == "unsupported"
    assert reason_codes == ["unsupported_configuration_causality"]
    assert supported is False


def test_verifier_reject_persists_a_typed_result_without_a_verified_response():
    service = FinnV2ResponseVerifierService(session=object())
    persisted = {}
    traces = []

    async def _create_verifier(**kwargs):
        persisted.update(kwargs)
        return SimpleNamespace(id=kwargs["id"])

    async def _append_trace(**kwargs):
        traces.append(kwargs)

    async def _unexpected_verified_create(**_kwargs):
        raise AssertionError("a reject must not create a VerifiedResponse")

    service.verifiers.create = _create_verifier
    service.verified.create = _unexpected_verified_create
    service._append_trace = _append_trace
    service._deterministic_verify = lambda **_kwargs: VerifierResult(
        verifier_result_id="verifier-rejected-1",
        run_id="run-rejected-1",
        user_id=7,
        draft_id="draft-rejected-1",
        passed=False,
        action="reject",
        claim_results=[],
        coverage=CoverageVerification(
            required_scopes=["profile"],
            covered_scopes=[],
            missing_scopes=["profile"],
            coverage_ok=False,
        ),
        schema_ok=True,
        ownership_ok=True,
        evidence_ok=False,
        relevance_ok=True,
        mode_purity_ok=True,
        uncertainty_ok=True,
        follow_up_ok=True,
        proposal_ok=True,
        policy_ok=True,
        safety_ok=True,
        reason_codes=["response_scope_incomplete"],
        semantic_verifier_used=False,
        created_at=datetime.now(timezone.utc),
    )

    run = SimpleNamespace(id="run-rejected-1", user_id=7)
    draft = ResponseDraft(
        draft_id="draft-rejected-1",
        run_id=run.id,
        user_id=run.user_id,
        mode="EVALUATE",
        direct_answer="Een antwoord zonder voldoende onderbouwing.",
        main_observation="Onderbouwing ontbreekt.",
        supporting_points=[],
        claims=[],
        uncertainty_summary=None,
        uncertainty_codes=[],
        next_step=None,
        follow_up_question=None,
        proposal_candidate=None,
        reasoning_result_id="reasoning-rejected-1",
        evidence_refs_used=["evidence-b", "evidence-a"],
        evidence_set_hash="hash-rejected-1",
        created_at=datetime.now(timezone.utc),
    )

    try:
        asyncio.run(
            service._verify_draft(
                run=run,
                orchestrator_result=SimpleNamespace(),
                policy=SimpleNamespace(),
                context=SimpleNamespace(),
                validation=SimpleNamespace(),
                draft=draft,
                trace_id="trace-rejected-1",
                repair_attempt=0,
            )
        )
    except FinnV2VerifierRejected as exc:
        assert exc.verifier.verifier_result_id == "verifier-rejected-1"
    else:
        raise AssertionError("expected a typed verifier reject")

    assert persisted["reasoning_result_id"] == "reasoning-rejected-1"
    assert persisted["result_json"]["coverage"]["coverage_ok"] is False
    assert traces[-1]["event_type"] == "response_rejected"
    assert traces[-1]["payload"]["reason_codes"] == ["response_scope_incomplete"]
    assert traces[-1]["payload"]["evidence_refs"] == ["evidence-a", "evidence-b"]


def test_verifier_uses_latest_terminal_reasoning_before_reusable_model_attempt():
    """A safe terminal repair must win over an earlier reusable model record."""
    service = FinnV2ResponseVerifierService(session=object())
    latest_row = SimpleNamespace(id="reasoning-terminal")
    expected = SimpleNamespace(id="verified-terminal")

    service.runs.get_by_id_for_user = lambda **_kwargs: asyncio.sleep(0, result=SimpleNamespace(id="run-1", user_id=7))
    service.orchestrators.get_for_run_version = lambda **_kwargs: asyncio.sleep(0, result=SimpleNamespace())
    service._latest_reasoning_for_run = lambda **_kwargs: asyncio.sleep(0, result=latest_row)

    async def _unexpected_reuse(**_kwargs):
        raise AssertionError("a newer terminal reasoning record must not be bypassed")

    service.reasoning.get_reusable_result = _unexpected_reuse
    service._reasoning_record_from_row = lambda _row: SimpleNamespace(validation_id="validation-1", snapshot_id="snapshot-1")
    service._orchestrator_result_from_row = lambda _row: SimpleNamespace()
    service.validations.get_by_id_for_user = lambda **_kwargs: asyncio.sleep(0, result=SimpleNamespace())
    service.snapshots.get_by_id_for_user = lambda **_kwargs: asyncio.sleep(0, result=SimpleNamespace())
    service.policies.get_for_run_version = lambda **_kwargs: asyncio.sleep(
        0,
        result=SimpleNamespace(
            decision_json={
                "policy_decision_id": "policy-1",
                "run_id": "run-1",
                "user_id": 7,
                "policy_class": "read",
                "allowed": True,
                "proposal_allowed": False,
                "confirmation_required": False,
                "step_up_required": False,
                "execution_allowed": False,
                "shadow_safe": True,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
        ),
    )
    service.contexts.build = lambda **_kwargs: asyncio.sleep(0, result=SimpleNamespace())
    service.drafts.build = lambda **_kwargs: SimpleNamespace(draft_id="draft-1", mode="EVALUATE")
    service._project_required_response_fields = lambda **_kwargs: SimpleNamespace(draft_id="draft-1", mode="EVALUATE")
    service._append_trace = lambda **_kwargs: asyncio.sleep(0)
    service._verify_draft = lambda **_kwargs: asyncio.sleep(0, result=expected)

    assert asyncio.run(service.verify_run(user_id=7, run_id="run-1", trace_id="trace-1")) is expected
