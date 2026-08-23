import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from backend.schemas.finn_v2_reasoning_context_schema import ReasoningContextPackage
from backend.schemas.finn_v2_reasoning_schema import ReasoningResult
from backend.services.finn_v2_reasoning_prompt_service import FinnV2ReasoningPromptService
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


def test_model_mode_mismatch_repairs_to_the_requested_mode(monkeypatch):
    service = FinnV2ReasoningService(session=object())
    context = _context()
    persisted = {}
    prompts = []
    wrong_mode = _model_output()
    wrong_mode["mode"] = "READ"
    responses = iter(
        [
            {"parsed": wrong_mode, "model": "gpt-4o-mini", "provider_metadata": {"response_status": "completed", "response_id": "resp-primary", "parsed_source": "response_output_text"}},
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
    assert persisted["result"].mode == "EVALUATE"
    assert persisted["result"].reasoning_provenance["reasoning_source"] == "model_repair"
    assert '"mode" MUST be exactly "EVALUATE"' in prompts[0]
    assert "reasoning_mode_mismatch" in prompts[1]


def test_model_repairs_unsupported_configuration_causality(monkeypatch):
    service = FinnV2ReasoningService(session=object())
    context_payload = _context().dict()
    context_payload["evidence"].append(
        {
            "evidence_id": "E2",
            "artifact_id": "artifact-2",
            "tool_name": "read_linked_bot",
            "domain": "automation_context",
            "entity_type": "bot",
            "entity_id": "186",
            "asset": "BTC",
            "source": "bot_repository",
            "freshness": "fresh",
            "confidence": "high",
            "facts": {"mode": "manual", "is_live": False},
        }
    )
    context = ReasoningContextPackage.parse_obj(context_payload)
    persisted = {}
    prompts = []
    unsupported = _model_output()
    unsupported["main_observation"] = "De handmatige modus beperkt de effectiviteit van de bot."
    unsupported["claims"][0]["text"] = "De handmatige modus leidt tot gemiste kansen."
    repaired = _model_output()
    repaired["main_observation"] = "De bot staat feitelijk in handmatige modus en is niet live."
    repaired["claims"][0]["text"] = "De bot staat in manual mode en is niet live."
    responses = iter(
        [
            {"parsed": unsupported, "model": "gpt-4o-mini", "provider_metadata": {"response_status": "completed", "response_id": "resp-primary", "parsed_source": "response_output_text"}},
            {"parsed": repaired, "model": "gpt-4o-mini", "provider_metadata": {"response_status": "completed", "response_id": "resp-repair", "parsed_source": "response_output_text"}},
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
    assert "unsupported_configuration_causality" in prompts[1]


def test_model_repairs_unsupported_stale_bot_status_causality(monkeypatch):
    service = FinnV2ReasoningService(session=object())
    context_payload = _context().dict()
    context_payload["evidence"].append(
        {
            "evidence_id": "E2",
            "artifact_id": "artifact-2",
            "tool_name": "read_bot_status",
            "domain": "automation_context",
            "entity_type": "bot_status",
            "entity_id": "186",
            "asset": "BTC",
            "source": "bot_repository",
            "freshness": "fresh",
            "confidence": "high",
            "facts": {"mode": "manual", "status": "stale", "is_live": False},
        }
    )
    context = ReasoningContextPackage.parse_obj(context_payload)
    persisted = {}
    prompts = []
    unsupported = _model_output()
    unsupported["direct_answer"] = "De stale botstatus ondermijnt de effectiviteit van je plan."
    unsupported["main_observation"] = "De bot staat in handmatige modus met een stale status."
    unsupported["claims"][0]["text"] = "De stale status kan de trading-prestaties beperken."
    repaired = _model_output()
    repaired["direct_answer"] = "De botstatus is opgeslagen als stale en de bot staat niet live."
    repaired["main_observation"] = "Controleer de opgeslagen botstatus voordat je de uitvoering van je plan beoordeelt."
    repaired["claims"][0]["text"] = "De botstatus is stale en de bot staat niet live."
    responses = iter(
        [
            {"parsed": unsupported, "model": "gpt-4o-mini", "provider_metadata": {"response_status": "completed", "response_id": "resp-primary", "parsed_source": "response_output_text"}},
            {"parsed": repaired, "model": "gpt-4o-mini", "provider_metadata": {"response_status": "completed", "response_id": "resp-repair", "parsed_source": "response_output_text"}},
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
    assert "unsupported_configuration_causality" in prompts[1]
    assert "stale status" in prompts[1]


def test_model_repairs_unsupported_populated_strategy_field_absence(monkeypatch):
    service = FinnV2ReasoningService(session=object())
    context_payload = _context().dict()
    context_payload["evidence"].append(
        {
            "evidence_id": "E2",
            "artifact_id": "artifact-2",
            "tool_name": "read_linked_strategy",
            "domain": "plan_context",
            "entity_type": "strategy",
            "entity_id": "325",
            "asset": "BTC",
            "source": "strategy_repository",
            "freshness": "fresh",
            "confidence": "high",
            "facts": {"strategy_id": 325, "entry": "100", "stop_loss": "92", "targets": ["112", "125"]},
        }
    )
    context = ReasoningContextPackage.parse_obj(context_payload)
    persisted = {}
    prompts = []
    unsupported = _model_output()
    unsupported["direct_answer"] = "Je strategie heeft geen stop-loss of duidelijke exit-niveaus."
    unsupported["main_observation"] = "De entry is aanwezig, maar targets ontbreken."
    unsupported["claims"][0]["text"] = "De strategie mist een stop loss."
    repaired = _model_output()
    repaired["direct_answer"] = "Strategie 325 bevat een entry, stop-loss en targets als opgeslagen waarden."
    repaired["main_observation"] = "Leg vast hoe je deze opgeslagen waarden samen gebruikt in je plan."
    repaired["claims"][0]["text"] = "Strategie 325 bevat stop-loss 92 en targets 112 en 125."
    responses = iter(
        [
            {"parsed": unsupported, "model": "gpt-4o-mini", "provider_metadata": {"response_status": "completed", "response_id": "resp-primary", "parsed_source": "response_output_text"}},
            {"parsed": repaired, "model": "gpt-4o-mini", "provider_metadata": {"response_status": "completed", "response_id": "resp-repair", "parsed_source": "response_output_text"}},
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
    assert "unsupported_stored_field_absence" in prompts[1]
    assert "stop loss" in prompts[1]


def test_model_repairs_unsupported_indicator_configuration_inference(monkeypatch):
    service = FinnV2ReasoningService(session=object())
    context_payload = _context().dict()
    context_payload["evidence"].append(
        {
            "evidence_id": "E2",
            "artifact_id": "artifact-2",
            "tool_name": "read_indicator_configuration",
            "domain": "market_context",
            "entity_type": "indicator_configuration",
            "asset": "BTC",
            "source": "indicator_repository",
            "freshness": "fresh",
            "confidence": "high",
            "facts": {"configured_indicators": [{"indicator": "rsi"}, {"indicator": "volume"}]},
        }
    )
    context = ReasoningContextPackage.parse_obj(context_payload)
    persisted = {}
    prompts = []
    unsupported = _model_output()
    unsupported["main_observation"] = "De beperkte indicatorconfiguratie kan leiden tot een minder robuuste handelsstrategie."
    repaired = _model_output()
    repaired["main_observation"] = "Je configuratie bevat RSI en volume; de evidence toont geen expliciete beslisregel die deze signalen combineert."
    responses = iter(
        [
            {"parsed": unsupported, "model": "gpt-4o-mini", "provider_metadata": {"response_status": "completed", "response_id": "resp-primary", "parsed_source": "response_output_text"}},
            {"parsed": repaired, "model": "gpt-4o-mini", "provider_metadata": {"response_status": "completed", "response_id": "resp-repair", "parsed_source": "response_output_text"}},
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
    assert "unsupported_indicator_configuration_inference" in prompts[1]
    assert "Do not describe zero configured items in a category as a gap" in prompts[1]


def test_configuration_causality_does_not_join_unrelated_statements(monkeypatch):
    service = FinnV2ReasoningService(session=object())
    context_payload = _context().dict()
    context_payload["evidence"].append(
        {
            "evidence_id": "E2",
            "artifact_id": "artifact-2",
            "tool_name": "read_linked_bot",
            "domain": "automation_context",
            "entity_type": "bot",
            "entity_id": "186",
            "asset": "BTC",
            "source": "bot_repository",
            "freshness": "fresh",
            "confidence": "high",
            "facts": {"mode": "manual", "is_live": False},
        }
    )
    context = ReasoningContextPackage.parse_obj(context_payload)
    persisted = {}
    result = _model_output()
    result["direct_answer"] = "De bot staat in handmatige modus en is niet live."
    result["main_observation"] = "Een deel van de marktcontext is beperkt beschikbaar."
    result["claims"][0]["text"] = "Setup 309 gebruikt timeframe 4H."
    result["claims"][0]["evidence_refs"] = ["E1"]

    async def _persist_record(**kwargs):
        persisted.update(kwargs)
        return kwargs

    async def _append_trace(*_args, **_kwargs):
        return None

    service._persist_record = _persist_record
    service._append_trace = _append_trace
    monkeypatch.setattr(service.flags, "reasoning_max_retries", lambda: 0)
    monkeypatch.setattr(service.flags, "reasoning_timeout_seconds", lambda: 5)
    monkeypatch.setattr(service.flags, "reasoning_max_output_tokens", lambda: 600)
    monkeypatch.setattr(
        "backend.services.finn_v2_reasoning_service.openai_client.ask_gpt_structured_response",
        lambda **_kwargs: {"parsed": result, "model": "gpt-4o-mini", "provider_metadata": {"response_status": "completed", "response_id": "resp-primary", "parsed_source": "response_output_text"}},
    )

    persisted_result = asyncio.run(
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

    assert persisted_result["status"] == "ready"
    assert persisted["result"].reasoning_provenance["validation_status"] == "passed"


def test_model_repairs_unsupported_market_causality(monkeypatch):
    service = FinnV2ReasoningService(session=object())
    context = _context()
    persisted = {}
    prompts = []
    unsupported = _model_output()
    unsupported["main_observation"] = "De stop-loss is te nauw voor de huidige marktomstandigheden."
    unsupported["claims"][0]["text"] = "De stop-loss is te nauw gezien de volatiliteit in de crypto-markt."
    repaired = _model_output()
    repaired["main_observation"] = "Setup 309 gebruikt timeframe 4H; zonder actuele prijs- of volatiliteitsmeting kan de stop-loss niet worden beoordeeld."
    repaired["claims"][0]["text"] = "Setup 309 gebruikt timeframe 4H."
    responses = iter(
        [
            {"parsed": unsupported, "model": "gpt-4o-mini", "provider_metadata": {"response_status": "completed", "response_id": "resp-primary", "parsed_source": "response_output_text"}},
            {"parsed": repaired, "model": "gpt-4o-mini", "provider_metadata": {"response_status": "completed", "response_id": "resp-repair", "parsed_source": "response_output_text"}},
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
    assert "unsupported_market_causality" in prompts[1]


def test_model_call_commits_state_before_waiting_for_provider(monkeypatch):
    events = []

    class _Session:
        async def commit(self):
            events.append("commit")

    service = FinnV2ReasoningService(session=_Session())
    context = _context()

    async def _persist_record(**kwargs):
        return kwargs

    async def _append_trace(*_args, **kwargs):
        if _args[3] == "reasoning_started":
            events.append("reasoning_started")

    def _call_provider(**_kwargs):
        events.append("provider")
        return {"parsed": _model_output(), "model": "gpt-4o-mini", "provider_metadata": {}}

    service._persist_record = _persist_record
    service._append_trace = _append_trace
    monkeypatch.setattr(service.flags, "reasoning_max_retries", lambda: 0)
    monkeypatch.setattr(service.flags, "reasoning_timeout_seconds", lambda: 5)
    monkeypatch.setattr(service.flags, "reasoning_max_output_tokens", lambda: 600)
    monkeypatch.setattr("backend.services.finn_v2_reasoning_service.openai_client.ask_gpt_structured_response", _call_provider)

    asyncio.run(
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

    assert events == ["reasoning_started", "commit", "provider"]


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


def test_integrated_plan_evaluation_prompt_requires_full_personal_grounding():
    context = _context().copy(
        update={
            "subject_scopes": ["profile", "indicators", "setup", "strategy", "bot"],
        }
    )

    prompt = FinnV2ReasoningPromptService().build_user_prompt(context)

    assert "integrated personal plan evaluation" in prompt
    assert "profile, configured indicators, setup, strategy and bot" in prompt
    assert "evidence_refs_used" in prompt


def test_integrated_plan_evaluation_prompt_lists_required_scope_evidence_refs():
    payload = _context().dict()
    payload.update(
        {
            "subject_scopes": ["profile", "indicators", "setup", "strategy", "bot"],
            "evidence": [
                {"evidence_id": "E1", "artifact_id": "a1", "tool_name": "read_profile", "domain": "identity_context", "entity_type": "profile", "source": "profile", "freshness": "fresh", "confidence": "high"},
                {"evidence_id": "E2", "artifact_id": "a2", "tool_name": "read_indicator_configuration", "domain": "market_context", "entity_type": "indicator_configuration", "source": "indicators", "freshness": "fresh", "confidence": "high"},
                {"evidence_id": "E3", "artifact_id": "a3", "tool_name": "read_active_setup", "domain": "plan_context", "entity_type": "setup", "source": "setup", "freshness": "fresh", "confidence": "high"},
                {"evidence_id": "E4", "artifact_id": "a4", "tool_name": "read_linked_strategy", "domain": "plan_context", "entity_type": "strategy", "source": "strategy", "freshness": "fresh", "confidence": "high"},
                {"evidence_id": "E5", "artifact_id": "a5", "tool_name": "read_linked_bot", "domain": "automation_context", "entity_type": "bot", "source": "bot", "freshness": "fresh", "confidence": "high"},
            ],
        },
    )
    context = ReasoningContextPackage.parse_obj(payload)

    prompt = FinnV2ReasoningPromptService().build_user_prompt(context)

    assert '"profile":["E1"]' in prompt
    assert '"indicators":["E2"]' in prompt
    assert '"setup":["E3"]' in prompt
    assert '"strategy":["E4"]' in prompt
    assert '"bot":["E5"]' in prompt


def test_registry_integrated_plan_prompt_lists_every_canonical_required_scope():
    payload = _context().dict()
    payload.update(
        {
            "request_plan": {
                "operation_id": "evaluate_complete_plan",
                "interaction_mode": "EVALUATE",
                "required_information_scopes": [
                    "profile", "preferences", "active_asset", "indicator_configuration",
                    "active_setup", "linked_strategy", "linked_bot", "bot_status",
                ],
            },
            "evidence": [
                {"evidence_id": "Eprof", "artifact_id": "a1", "tool_name": "read_profile", "domain": "identity_context", "entity_type": "profile", "source": "profile", "freshness": "fresh", "confidence": "high"},
                {"evidence_id": "Eprefs", "artifact_id": "a2", "tool_name": "read_user_preferences", "domain": "identity_context", "entity_type": "preferences", "source": "preferences", "freshness": "fresh", "confidence": "high"},
                {"evidence_id": "Easset", "artifact_id": "a3", "tool_name": "read_active_asset", "domain": "identity_context", "entity_type": "asset", "source": "asset", "freshness": "fresh", "confidence": "high"},
                {"evidence_id": "Einds", "artifact_id": "a4", "tool_name": "read_indicator_configuration", "domain": "market_context", "entity_type": "indicator_configuration", "source": "indicators", "freshness": "fresh", "confidence": "high"},
                {"evidence_id": "Esetup", "artifact_id": "a5", "tool_name": "read_active_setup", "domain": "plan_context", "entity_type": "setup", "source": "setup", "freshness": "fresh", "confidence": "high"},
                {"evidence_id": "Estrat", "artifact_id": "a6", "tool_name": "read_linked_strategy", "domain": "plan_context", "entity_type": "strategy", "source": "strategy", "freshness": "fresh", "confidence": "high"},
                {"evidence_id": "Ebot", "artifact_id": "a7", "tool_name": "read_linked_bot", "domain": "automation_context", "entity_type": "bot", "source": "bot", "freshness": "fresh", "confidence": "high"},
                {"evidence_id": "Estatus", "artifact_id": "a8", "tool_name": "read_bot_status", "domain": "automation_context", "entity_type": "bot_status", "source": "bot", "freshness": "fresh", "confidence": "high"},
            ],
        }
    )

    prompt = FinnV2ReasoningPromptService().build_user_prompt(ReasoningContextPackage.parse_obj(payload))

    assert '"active_asset":["Easset"]' in prompt
    assert '"preferences":["Eprefs"]' in prompt
    assert '"bot_status":["Estatus"]' in prompt


def test_integrated_plan_evaluation_prompt_lists_saved_grounding_values():
    payload = _context().dict()
    payload.update(
        {
            "subject_scopes": ["profile", "indicators", "setup", "strategy", "bot"],
            "uncertainty_codes": ["bot_status_stale"],
            "evidence": [
                {"evidence_id": "E1", "artifact_id": "a1", "tool_name": "read_profile", "domain": "identity_context", "entity_type": "profile", "source": "profile", "freshness": "fresh", "confidence": "high", "facts": {"trader_profile": {"risk_profile": "balanced"}}},
                {"evidence_id": "E2", "artifact_id": "a2", "tool_name": "read_indicator_configuration", "domain": "market_context", "entity_type": "indicator_configuration", "source": "indicators", "freshness": "fresh", "confidence": "high", "facts": {"configured_indicators": [{"indicator": "rsi"}]}},
                {"evidence_id": "E3", "artifact_id": "a3", "tool_name": "read_active_setup", "domain": "plan_context", "entity_type": "setup", "entity_id": "309", "source": "setup", "freshness": "fresh", "confidence": "high", "facts": {"setup_id": 309, "timeframe": "4H"}},
                {"evidence_id": "E4", "artifact_id": "a4", "tool_name": "read_linked_strategy", "domain": "plan_context", "entity_type": "strategy", "entity_id": "325", "source": "strategy", "freshness": "fresh", "confidence": "high", "facts": {"strategy_id": 325, "entry": "100", "stop_loss": "92", "targets": ["112", "125"]}},
                {"evidence_id": "E5", "artifact_id": "a5", "tool_name": "read_linked_bot", "domain": "automation_context", "entity_type": "bot", "entity_id": "186", "source": "bot", "freshness": "fresh", "confidence": "high", "facts": {"bot_id": 186}},
            ],
        }
    )

    prompt = FinnV2ReasoningPromptService().build_user_prompt(ReasoningContextPackage.parse_obj(payload))

    assert '"profile":["balanced"]' in prompt
    assert '"indicators":["rsi"]' in prompt
    assert '"setup":["309","4H"]' in prompt
    assert '"strategy":["100","112","125","325","92"]' in prompt
    assert '"bot":["186"]' in prompt
    assert "Never say a stop loss, entry, or target is absent" in prompt
    assert "zero configured count for an indicator category is only a configuration fact" in prompt
    assert "never present it as an absent or limiting fact" in prompt
