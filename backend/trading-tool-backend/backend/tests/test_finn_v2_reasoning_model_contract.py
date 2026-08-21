import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from backend.schemas.finn_v2_reasoning_context_schema import ReasoningContextPackage
from backend.schemas.finn_v2_reasoning_schema import ReasoningResult
from backend.services.finn_v2_reasoning_service import FinnV2ReasoningService


def _context():
    return ReasoningContextPackage.parse_obj(
        {
            "run_id": "run-1",
            "user_id": 7,
            "user_message": "Wat ontbreekt er aan mijn BTC-plan?",
            "locale": "nl",
            "interaction_mode": "EVALUATE",
            "subject_scopes": ["setup"],
            "required_domains": ["plan_context"],
            "orchestrator_result_id": "orchestrator-1",
            "snapshot_id": "snapshot-1",
            "validation_id": "validation-1",
            "policy_decision_id": "policy-1",
            "evidence_set_hash": "hash-1",
            "evidence": [
                {
                    "evidence_id": "E1",
                    "artifact_id": "artifact-1",
                    "tool_name": "read_active_setup",
                    "domain": "plan_context",
                    "entity_type": "setup",
                    "entity_id": "309",
                    "asset": "BTC",
                    "source": "setup_repository",
                    "freshness": "fresh",
                    "confidence": "high",
                    "facts": {"timeframe": "4H"},
                }
            ],
            "policy": {
                "policy_class": "advice",
                "allowed": True,
                "proposal_allowed": False,
                "confirmation_required": False,
                "step_up_required": False,
                "execution_allowed": False,
            },
        }
    )


def _model_output(*, claim_type="evaluation"):
    return {
        "mode": "EVALUATE",
        "direct_answer": "Je BTC-plan heeft een duidelijke 4H-setup.",
        "main_observation": "De setup is onderbouwd met de aanwezige evidence.",
        "supporting_points": [],
        "claims": [
            {
                "claim_id": "C1",
                "claim_type": claim_type,
                "text": "Setup 309 gebruikt timeframe 4H.",
                "evidence_refs": ["E1"],
                "confidence": "high",
            }
        ],
        "uncertainty_summary": None,
        "uncertainty_codes": [],
        "next_step": None,
        "follow_up_question": None,
        "proposal_candidate": None,
        "evidence_refs_used": ["E1"],
    }


def test_model_schema_error_repairs_once_with_sanitized_field_paths(monkeypatch):
    service = FinnV2ReasoningService(session=object())
    context = _context()
    persisted = {}
    prompts = []
    responses = iter(
        [
            {"parsed": _model_output(claim_type="observation"), "model": "gpt-4o-mini", "provider_metadata": {"response_status": "completed", "response_id": "resp-primary", "parsed_source": "response_output_text"}},
            {"parsed": _model_output(), "model": "gpt-4o-mini", "provider_metadata": {"response_status": "completed", "response_id": "resp-repair", "parsed_source": "response_output_text"}},
        ]
    )

    async def _persist_record(**kwargs):
        persisted.update(kwargs)
        return kwargs

    async def _append_trace(*_args, **_kwargs):
        return None

    def _call_provider(**kwargs):
        prompts.append(kwargs["prompt"])
        return next(responses)

    service._persist_record = _persist_record
    service._append_trace = _append_trace
    monkeypatch.setattr(service.flags, "reasoning_max_retries", lambda: 1)
    monkeypatch.setattr(service.flags, "reasoning_timeout_seconds", lambda: 5)
    monkeypatch.setattr(service.flags, "reasoning_max_output_tokens", lambda: 600)
    monkeypatch.setattr("backend.services.finn_v2_reasoning_service.openai_client.ask_gpt_structured_response", _call_provider)

    result = asyncio.run(
        service._run_model_reasoning(
            run_id="run-1",
            user_id=7,
            trace_id="trace-1",
            orchestrator_result=SimpleNamespace(orchestrator_result_id="orchestrator-1"),
            policy=SimpleNamespace(policy_decision_id="policy-1"),
            snapshot=SimpleNamespace(id="snapshot-1"),
            validation=SimpleNamespace(id="validation-1"),
            context=context,
            model_name="gpt-4o-mini",
            input_hash="hash-input",
        )
    )

    assert result["status"] == "ready"
    assert persisted["result"].reasoning_provenance["reasoning_source"] == "model_repair"
    assert persisted["result"].reasoning_provenance["validation_status"] == "passed"
    assert "claims.0.claim_type" in prompts[1]
    assert "observation" not in prompts[1]


def test_missing_required_model_field_has_a_sanitized_validation_error():
    service = FinnV2ReasoningService(session=object())
    payload = _model_output()
    payload.pop("direct_answer")

    with pytest.raises(ValidationError) as exc_info:
        ReasoningResult.parse_obj(
            {
                **payload,
                "reasoning_result_id": "reasoning-1",
                "run_id": "run-1",
                "user_id": 7,
                "model": "gpt-4o-mini",
                "created_at": datetime.now(timezone.utc),
            }
        )

    assert service._validation_error_details(exc_info.value) == [
        {"path": "direct_answer", "code": "value_error.missing"}
    ]
