import asyncio
import time
from datetime import datetime, timezone
from types import SimpleNamespace

from backend.schemas.finn_v2_verifier_schema import CoverageVerification, VerifierResult
from backend.services.finn_v2_response_verifier_service import FinnV2ResponseVerifierService
from backend.services.finn_v2_semantic_verifier_service import FinnV2SemanticVerifierService
from backend.services.finn_v2_flag_service import FinnV2FlagService
from backend.utils import openai_client as openai_module


def test_semantic_verifier_model_default_and_override(monkeypatch):
    monkeypatch.delenv("FINN_V2_SEMANTIC_VERIFIER_MODEL", raising=False)
    assert FinnV2FlagService().semantic_verifier_model() == "gpt-6-luna"
    monkeypatch.setenv("FINN_V2_SEMANTIC_VERIFIER_MODEL", "gpt-test")
    assert FinnV2FlagService().semantic_verifier_model() == "gpt-test"
    monkeypatch.delenv("FINN_V2_COACH_VERIFIER_MODEL", raising=False)
    assert FinnV2FlagService().coach_verifier_model() == "gpt-6-luna"
    monkeypatch.setenv("FINN_V2_COACH_VERIFIER_MODEL", "gpt-coach-test")
    assert FinnV2FlagService().coach_verifier_model() == "gpt-coach-test"


def test_semantic_verifier_uses_strict_structured_output(monkeypatch):
    service = FinnV2SemanticVerifierService()
    service.flags.is_semantic_verifier_enabled = lambda: True
    service.flags.semantic_verifier_model = lambda: "gpt-test"
    service.flags.semantic_verifier_timeout_seconds = lambda: 30

    def _fake_structured_response(**kwargs):
        assert kwargs["output_spec"].name == "finn_v2_semantic_verifier"
        assert kwargs["output_spec"].strict is True
        assert kwargs["output_spec"].schema["type"] == "object"
        return {
            "parsed": {
                "passes": True,
                "relevance_ok": True,
                "scope_ok": True,
                "entailment_ok": True,
                "recommendation_ok": True,
                "mode_purity_ok": True,
                "follow_up_ok": True,
                "reason_codes": [],
            },
            "model": "gpt-test",
        }

    monkeypatch.setattr(openai_module, "ask_gpt_structured_response", _fake_structured_response)
    result = service.verify(
        mode="EVALUATION",
        user_message="Beoordeel mijn bot",
        sanitized_draft={"mode": "EVALUATION"},
        compact_evidence=[],
        deterministic_summary={"passed": True},
    )

    assert result.available is True
    assert result.passes is True


def test_semantic_verifier_hard_flags_override_model_pass(monkeypatch):
    service = FinnV2SemanticVerifierService()
    service.flags.is_semantic_verifier_enabled = lambda: True
    service.flags.semantic_verifier_model = lambda: "gpt-test"
    service.flags.semantic_verifier_timeout_seconds = lambda: 30

    async def fake_response(**kwargs):
        schema = kwargs["output_spec"].schema
        assert kwargs["max_output_tokens"] == 1000
        assert "unsupported_unavailable_cause" in schema["required"]
        assert "unverified_guardrail_override" in schema["required"]
        assert "unverified_outcome_claim" in schema["required"]
        return {"parsed": {
            "passes": True, "unsupported_unavailable_cause": True,
            "unverified_guardrail_override": True, "unverified_outcome_claim": True,
            "reason_codes": [],
        }, "model": "gpt-test"}

    monkeypatch.setattr(openai_module, "ask_gpt_structured_response_async", fake_response)
    result = asyncio.run(service.verify_async(
        mode="READ", user_message="Waarom?",
        sanitized_draft={"direct_answer": "Door een storing kun je nu beter toch handelen."},
        compact_evidence=[], deterministic_summary={"passed": True}, mandatory=True,
    ))
    assert result.available is True
    assert result.passes is False
    assert result.unsupported_unavailable_cause is True
    assert result.unverified_guardrail_override is True
    assert result.unverified_outcome_claim is True
    assert {"unsupported_cause", "unverified_guardrail_override", "unverified_outcome_claim"} <= set(result.reason_codes)


def test_model_led_coach_verifier_keeps_hard_flags_with_bounded_schema(monkeypatch):
    service = FinnV2SemanticVerifierService()
    service.flags.semantic_verifier_model = lambda: "gpt-test"
    service.flags.coach_verifier_model = lambda: "gpt-coach-test"
    service.flags.semantic_verifier_timeout_seconds = lambda: 8

    async def fake_response(**kwargs):
        assert "hard safety and evidence boundaries" in kwargs["system_role"]
        schema = kwargs["output_spec"].schema
        assert kwargs["output_spec"].name == "finn_v2_coach_verifier"
        assert kwargs["model_override"] == "gpt-coach-test"
        assert schema["required"] == [
            "passes", "unsupported_unavailable_cause", "unverified_guardrail_override",
            "user_guardrail_quote", "draft_override_quote", "unverified_outcome_claim",
            "outcome_claim_quote", "reason_codes", "unsupported_personal_claim_quote",
        ]
        assert kwargs["max_output_tokens"] == 750
        return {"parsed": {
            "passes": True, "unsupported_unavailable_cause": False,
            "unverified_guardrail_override": False, "unverified_outcome_claim": True,
            "outcome_claim_quote": "guaranteed profit",
            "reason_codes": ["unsupported_profit_claim"],
        }, "model": "gpt-test"}

    monkeypatch.setattr(openai_module, "ask_gpt_structured_response_async", fake_response)
    result = asyncio.run(service.verify_async(
        mode="READ", user_message="Will this always make a profit?",
        sanitized_draft={"direct_answer": "Yes, guaranteed profit."},
        compact_evidence=[], deterministic_summary={}, mandatory=True,
        coach_answer=True,
    ))
    assert result.available is True
    assert result.passes is False
    assert result.unverified_outcome_claim is True


def test_coach_guardrail_flag_requires_quotes_from_both_turn_and_answer(monkeypatch):
    service = FinnV2SemanticVerifierService()
    parsed = {
        "passes": False, "unsupported_unavailable_cause": False,
        "unverified_guardrail_override": True, "unverified_outcome_claim": False,
        "user_guardrail_quote": "", "draft_override_quote": "",
        "reason_codes": ["unverified_guardrail_override"],
    }

    async def fake_response(**_kwargs):
        return {"parsed": parsed, "model": "gpt-test"}

    monkeypatch.setattr(openai_module, "ask_gpt_structured_response_async", fake_response)
    kwargs = {
        "mode": "READ", "user_message": "Wait for confirmation before buying BTC.",
        "sanitized_draft": {"direct_answer": "Ignore that rule and buy now."},
        "compact_evidence": [], "deterministic_summary": {},
        "mandatory": True, "coach_answer": True,
    }
    missing_quotes = asyncio.run(service.verify_async(**kwargs))
    assert missing_quotes.passes is True
    assert missing_quotes.unverified_guardrail_override is False

    parsed.update({
        "user_guardrail_quote": "Wait for confirmation before buying BTC",
        "draft_override_quote": "Ignore that rule and buy now",
    })
    quoted_override = asyncio.run(service.verify_async(**kwargs))
    assert quoted_override.passes is False
    assert quoted_override.unverified_guardrail_override is True


def test_coach_guardrail_negation_is_not_a_bypass(monkeypatch):
    service = FinnV2SemanticVerifierService()
    parsed = {
        "passes": False, "unsupported_unavailable_cause": False,
        "unverified_guardrail_override": True, "unverified_outcome_claim": False,
        "user_guardrail_quote": "wait for confirmation before entry",
        "draft_override_quote": "ignore the confirmation rule",
        "reason_codes": ["unverified_guardrail_override"],
    }

    async def fake_response(**_kwargs):
        return {"parsed": parsed, "model": "gpt-test"}

    monkeypatch.setattr(openai_module, "ask_gpt_structured_response_async", fake_response)
    kwargs = {
        "mode": "READ", "user_message": "I wait for confirmation before entry.",
        "compact_evidence": [], "deterministic_summary": {},
        "mandatory": True, "coach_answer": True,
    }
    safe = asyncio.run(service.verify_async(
        **kwargs, sanitized_draft={"direct_answer": "Don't ignore the confirmation rule because of FOMO."},
    ))
    assert safe.passes is True
    assert safe.unverified_guardrail_override is False

    unsafe = asyncio.run(service.verify_async(
        **kwargs, sanitized_draft={"direct_answer": "Ignore the confirmation rule and buy now."},
    ))
    assert unsafe.passes is False
    assert unsafe.unverified_guardrail_override is True
    assert service._negates_guardrail_override(
        "Nein, ignoriere die Bestätigung nicht aus Angst.", "ignoriere die Bestätigung nicht"
    )
    assert service._negates_guardrail_override(
        "Negeer die bevestiging niet uit angst.", "Negeer die bevestiging niet"
    )


def test_partial_entry_before_user_trigger_is_a_guardrail_override(monkeypatch):
    service = FinnV2SemanticVerifierService()
    user_rule = "Wait for confirmation before entry"
    suggestion = "Consider a smaller position before confirmation"

    async def fake_response(**kwargs):
        assert "including conditional alternatives, smaller positions" in kwargs["system_role"]
        return {"parsed": {
            "passes": False, "unsupported_unavailable_cause": False,
            "unverified_guardrail_override": True, "unverified_outcome_claim": False,
            "user_guardrail_quote": user_rule, "draft_override_quote": suggestion,
            "reason_codes": ["unverified_guardrail_override"],
        }, "model": "gpt-test"}

    monkeypatch.setattr(openai_module, "ask_gpt_structured_response_async", fake_response)
    result = asyncio.run(service.verify_async(
        mode="READ", user_message=user_rule + ". Should I bypass it?",
        sanitized_draft={"direct_answer": suggestion + " to ease your FOMO."},
        compact_evidence=[], deterministic_summary={}, mandatory=True, coach_answer=True,
    ))
    assert result.passes is False
    assert result.rejected_claim_quotes == [suggestion]


def test_previous_assistant_precaution_still_blocks_followup_override(monkeypatch):
    service = FinnV2SemanticVerifierService()
    precaution = "wacht op bevestiging voor een entry"
    override = "neem alvast een kleinere positie"

    async def fake_response(**kwargs):
        assert "previous_verified_answer" in kwargs["prompt"]
        return {"parsed": {
            "passes": False, "unsupported_unavailable_cause": False,
            "unverified_guardrail_override": True, "unverified_outcome_claim": False,
            "user_guardrail_quote": precaution, "draft_override_quote": override,
            "reason_codes": ["unverified_guardrail_override"],
        }, "model": "gpt-test"}

    monkeypatch.setattr(openai_module, "ask_gpt_structured_response_async", fake_response)
    result = asyncio.run(service.verify_async(
        mode="READ", user_message="Wat kan ik nu doen met die FOMO?",
        sanitized_draft={"direct_answer": override + " terwijl je wacht."},
        compact_evidence=[], deterministic_summary={"previous_verified_answer": precaution},
        mandatory=True, coach_answer=True,
    ))
    assert result.unverified_guardrail_override is True
    assert result.passes is False


def test_coach_outcome_flag_does_not_reject_a_capability_description(monkeypatch):
    service = FinnV2SemanticVerifierService()
    parsed = {
        "passes": False, "unsupported_unavailable_cause": False,
        "unverified_guardrail_override": False, "unverified_outcome_claim": True,
        "outcome_claim_quote": "risico per positie berekenen",
        "reason_codes": ["unverified_outcome_claim"],
    }

    async def fake_response(**_kwargs):
        return {"parsed": parsed, "model": "gpt-test"}

    monkeypatch.setattr(openai_module, "ask_gpt_structured_response_async", fake_response)
    result = asyncio.run(service.verify_async(
        mode="READ", user_message="Waarmee kun je helpen?",
        sanitized_draft={"direct_answer": "Ik kan je risico per positie berekenen."},
        compact_evidence=[], deterministic_summary={}, mandatory=True,
        coach_answer=True,
    ))
    assert result.passes is True
    assert result.unverified_outcome_claim is False


def test_typed_object_ambiguity_allows_a_clarifying_question_only(monkeypatch):
    service = FinnV2SemanticVerifierService()
    parsed = {
        "passes": False, "unsupported_unavailable_cause": False,
        "unverified_guardrail_override": False, "unverified_outcome_claim": False,
        "reason_codes": ["setup_ambiguous"],
    }

    async def fake_response(**_kwargs):
        return {"parsed": parsed, "model": "gpt-test"}

    monkeypatch.setattr(openai_module, "ask_gpt_structured_response_async", fake_response)
    kwargs = {
        "mode": "EVALUATE", "user_message": "Beoordeel mijn strategie.",
        "sanitized_draft": {"direct_answer": "Welke setup bedoel je?"},
        "compact_evidence": [], "mandatory": True, "coach_answer": True,
        "deterministic_summary": {
            "typed_unavailable_reasons": [{"scope": "read_active_setup", "reason": "setup_ambiguous"}],
            "unavailable_scopes": ["read_active_setup"],
        },
    }
    allowed = asyncio.run(service.verify_async(**kwargs))
    assert allowed.passes is True

    no_question = asyncio.run(service.verify_async(
        **{**kwargs, "sanitized_draft": {"direct_answer": "De setup is duidelijk."}}
    ))
    assert no_question.passes is False

    parsed["reason_codes"] = ["setup_ambiguous", "unverified_personal_claim"]
    unsupported_label_without_quote = asyncio.run(service.verify_async(**kwargs))
    assert unsupported_label_without_quote.passes is True

    parsed["unsupported_personal_claim_quote"] = "Je hebt twee setups."
    other_failure = asyncio.run(service.verify_async(**{
        **kwargs, "sanitized_draft": {"direct_answer": "Welke setup bedoel je? Je hebt twee setups."},
    }))
    assert other_failure.passes is False


def test_coach_scope_incomplete_alone_is_not_a_hard_safety_veto(monkeypatch):
    service = FinnV2SemanticVerifierService()

    async def fake_response(**_kwargs):
        return {"parsed": {
            "passes": False, "unsupported_unavailable_cause": False,
            "unverified_guardrail_override": False, "unverified_outcome_claim": False,
            "reason_codes": ["scope_incomplete"],
        }, "model": "gpt-test"}

    monkeypatch.setattr(openai_module, "ask_gpt_structured_response_async", fake_response)
    result = asyncio.run(service.verify_async(
        mode="READ", user_message="For about five years.",
        sanitized_draft={"direct_answer": "You mean about five years; the 4H chart interval does not set your holding period."},
        compact_evidence=[], deterministic_summary={}, mandatory=True, coach_answer=True,
    ))
    assert result.passes is True
    assert result.reason_codes == []


def test_coach_verifier_preserves_exact_rejected_claim_for_repair(monkeypatch):
    service = FinnV2SemanticVerifierService()
    claim = "Je opgeslagen plan zegt dat je moet wachten"

    async def fake_response(**kwargs):
        assert "not proof of a saved FINN fact" in kwargs["system_role"]
        return {"parsed": {
            "passes": False, "unsupported_unavailable_cause": False,
            "unverified_guardrail_override": False, "unverified_outcome_claim": False,
            "unsupported_personal_claim_quote": claim,
            "reason_codes": ["unverified_personal_claim"],
        }, "model": "gpt-test"}

    monkeypatch.setattr(openai_module, "ask_gpt_structured_response_async", fake_response)
    result = asyncio.run(service.verify_async(
        mode="READ", user_message="Mijn plan zegt te wachten op bevestiging.",
        sanitized_draft={"direct_answer": claim + " voor je instapt."},
        compact_evidence=[], deterministic_summary={}, mandatory=True, coach_answer=True,
    ))
    assert result.passes is False
    assert result.rejected_claim_quotes == [claim]


def test_coach_advisory_reason_cannot_override_grounded_turn(monkeypatch):
    service = FinnV2SemanticVerifierService()

    async def fake_response(**_kwargs):
        return {"parsed": {
            "passes": False, "unsupported_unavailable_cause": False,
            "unverified_guardrail_override": False, "unverified_outcome_claim": False,
            "reason_codes": ["recommendation_consistency"],
        }, "model": "gpt-test"}

    monkeypatch.setattr(openai_module, "ask_gpt_structured_response_async", fake_response)
    result = asyncio.run(service.verify_async(
        mode="READ", user_message="I plan to hold for five years.",
        sanitized_draft={"direct_answer": "That is your stated horizon, not a saved strategy rule."},
        compact_evidence=[], deterministic_summary={}, mandatory=True, coach_answer=True,
    ))
    assert result.passes is True
    assert result.reason_codes == []


def test_coach_unavailable_source_cause_requires_an_unavailable_source(monkeypatch):
    service = FinnV2SemanticVerifierService()

    async def fake_response(**_kwargs):
        return {"parsed": {
            "passes": False, "unsupported_unavailable_cause": True,
            "unverified_guardrail_override": False, "unverified_outcome_claim": False,
            "reason_codes": ["unsupported_unavailable_cause"],
        }, "model": "gpt-test"}

    monkeypatch.setattr(openai_module, "ask_gpt_structured_response_async", fake_response)
    kwargs = {
        "mode": "READ", "user_message": "Can you use this unavailable feature?",
        "sanitized_draft": {"direct_answer": "That feature is not available."},
        "compact_evidence": [], "mandatory": True, "coach_answer": True,
    }
    no_missing_source = asyncio.run(service.verify_async(
        **kwargs, deterministic_summary={"unavailable_scopes": []},
    ))
    missing_source = asyncio.run(service.verify_async(
        **kwargs, deterministic_summary={"unavailable_scopes": ["market_snapshot"]},
    ))
    assert no_missing_source.passes is True
    assert no_missing_source.unsupported_unavailable_cause is False
    assert no_missing_source.reason_codes == []
    assert missing_source.passes is True
    assert missing_source.unsupported_unavailable_cause is False

    invented_cause = asyncio.run(service.verify_async(
        **{**kwargs, "sanitized_draft": {
            "direct_answer": "The provider is down, so the score is unavailable."
        }},
        deterministic_summary={"unavailable_scopes": ["scores"]},
    ))
    assert invented_cause.passes is False
    assert invented_cause.unsupported_unavailable_cause is True


def test_coach_missing_score_data_is_not_an_invented_outage():
    for answer in (
        "Ik kan de totaalscore niet duiden omdat de scoregegevens ontbreken.",
        "I cannot explain the score because the score data is missing.",
        "Ich kann den Score nicht deuten, weil die Score-Daten fehlen.",
        "The provider data is not available, but I do not know why.",
    ):
        assert not FinnV2SemanticVerifierService._asserts_source_failure_cause(
            {"direct_answer": answer}
        )


def test_semantic_verifier_async_timeout_does_not_block_the_worker_loop(monkeypatch):
    service = FinnV2SemanticVerifierService()
    service.flags.is_semantic_verifier_enabled = lambda: True
    service.flags.semantic_verifier_timeout_seconds = lambda: 1

    def _slow_response(**_kwargs):
        time.sleep(0.15)
        return {"parsed": {"passes": True}}

    monkeypatch.setattr(openai_module, "ask_gpt_structured_response", _slow_response)

    async def _run():
        task = asyncio.create_task(
            service.verify_async(
                mode="EVALUATE",
                user_message="Beoordeel mijn plan",
                sanitized_draft={},
                compact_evidence=[],
                deterministic_summary={},
                timeout_seconds=0.02,
            )
        )
        await asyncio.sleep(0.005)
        assert task.done() is False
        return await task

    result = asyncio.run(_run())
    assert result.available is False
    assert result.passes is False
    assert result.reason_codes == ["semantic_verifier_timeout"]


def test_disabled_semantic_verifier_does_not_downgrade_required_evaluation_mode():
    service = FinnV2ResponseVerifierService(session=object())
    service.flags.is_semantic_verifier_enabled = lambda: False
    service.flags.semantic_verifier_required_modes = lambda: {"EVALUATION", "PROPOSAL", "ACTION"}
    verifier = VerifierResult(
        verifier_result_id="verifier-1",
        run_id="run-1",
        user_id=7,
        draft_id="draft-1",
        passed=True,
        action="deliver",
        claim_results=[],
        coverage=CoverageVerification(coverage_ok=True),
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

    semantic = service.semantic.verify(
        mode="EVALUATION",
        user_message="Bekijk mijn plan",
        sanitized_draft={"mode": "EVALUATION"},
        compact_evidence=[],
        deterministic_summary={"passed": True},
    )

    merged = service._merge_semantic(verifier, semantic, "EVALUATION")

    assert merged.passed is True
    assert merged.action == "deliver"
    assert merged.reason_codes == []
    assert merged.semantic_verifier_used is False


def test_flag_defaults_normalize_legacy_mode_aliases():
    service = FinnV2ResponseVerifierService(session=object())

    assert service.flags.semantic_verifier_required_modes() == {"EVALUATE", "CREATE_PROPOSAL", "ACTION_PROPOSAL"}
    assert service.flags.canary_allowed_modes() == {"READ", "EVALUATE"}


def test_contract_proposal_drafts_do_not_require_a_second_semantic_provider_call():
    service = FinnV2ResponseVerifierService(session=object())

    assert service._is_deterministic_contract_response(operation_id="create_setup") is True
    assert service._is_deterministic_contract_response(operation_id="select_asset") is True
    assert service._is_deterministic_contract_response(operation_id="evaluate_plan") is False


def test_asset_selection_relevance_compares_catalog_symbols_not_alias_spelling():
    service = FinnV2ResponseVerifierService(session=object())
    draft = SimpleNamespace(
        mode="ACTION_PROPOSAL",
        direct_answer="Ik kan SOL als je actieve asset instellen na je bevestiging.",
        main_observation="De actieve asset verandert pas na expliciete confirmation.",
        proposal_candidate=None,
        reasoning_provenance={"operation_id": "select_asset"},
        evidence_refs_used=[],
        next_step=None,
    )

    assert service._is_relevant("Selecteer Solana als mijn actieve asset.", draft) is True
