from backend.domain.finn_v2_operation_registry import FinnV2OperationRegistry
from backend.services.finn_v2_structured_operation_selector_service import FinnV2StructuredOperationSelectorService
from backend.utils import openai_client
from backend.utils.openai_client import StructuredOutputSpec
from types import SimpleNamespace


def test_selector_responses_payload_wraps_raw_schema_exactly_once():
    registry = FinnV2OperationRegistry()
    schema = FinnV2StructuredOperationSelectorService._schema((
        registry.get("explain_financial_concept").operation_id,
        registry.get("clarify_request").operation_id,
    ))
    request = openai_client.build_structured_response_request(
        model_name="gpt-test",
        prompt="Wat betekent RSI?",
        system_role="select",
        output_spec=StructuredOutputSpec("finn_v2_operation_selection", schema),
        max_output_tokens=100,
    )

    payload = request["text"]["format"]
    assert payload["type"] == "json_schema"
    assert payload["name"] == "finn_v2_operation_selection"
    assert payload["strict"] is True
    assert payload["schema"]["type"] == "object"
    assert payload["schema"]["additionalProperties"] is False
    assert payload["schema"]["properties"]["operation_id"]["enum"] == [
        "explain_financial_concept", "clarify_request"
    ]
    assert payload["schema"]["properties"]["entities"] == {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "concept": {"type": ["string", "null"]},
            "asset": {"type": ["string", "null"]},
            "setup_id": {"type": ["string", "null"]},
            "strategy_id": {"type": ["string", "null"]},
            "bot_id": {"type": ["string", "null"]},
            "setup_type": {"type": ["string", "null"]},
            "timeframe": {"type": ["string", "null"]},
            "name": {"type": ["string", "null"]},
        },
        "required": [
            "concept", "asset", "setup_id", "strategy_id", "bot_id",
            "setup_type", "timeframe", "name",
        ],
    }
    assert set(payload["schema"]["required"]) == {
        "operation_id", "confidence", "entities", "target_asset",
        "conversation_reference", "missing_inputs", "ambiguity_reason", "semantic_frame",
    }
    assert payload["schema"]["properties"]["semantic_frame"]["additionalProperties"] is False
    assert "schema" not in payload["schema"]


def test_transport_timeout_is_not_sent_as_a_responses_payload_field():
    request = openai_client.build_structured_response_request(
        model_name="gpt-test",
        prompt="x",
        system_role="x",
        output_spec=StructuredOutputSpec("test", {"type": "object", "properties": {}, "required": [], "additionalProperties": False}),
        max_output_tokens=10,
        timeout_seconds=10,
    )

    assert "timeout" not in request


def test_wrapped_schema_is_rejected_before_network_or_rate_limit(monkeypatch):
    called = False

    def should_not_call():
        nonlocal called
        called = True
        return True

    monkeypatch.setattr(openai_client, "_rate_limit_allows_call", should_not_call)
    result = openai_client.ask_gpt_structured_response(
        prompt="x",
        system_role="x",
        output_spec=StructuredOutputSpec(
            "bad",
            {"name": "bad", "strict": True, "schema": {"type": "object"}},
        ),
    )

    assert result == {
        "error": "structured_schema_contract_error",
        "error_detail": "structured_output_provider_wrapper_rejected",
    }
    assert called is False


def test_provider_schema_400_maps_to_selector_schema_contract_error():
    selector = FinnV2StructuredOperationSelectorService(
        provider=lambda **_kwargs: {
            "error": "structured_schema_contract_error",
            "error_detail": "provider_rejected_schema",
        }
    )
    selection, error = selector.select(
        message="Wat betekent RSI?",
        candidate_contracts=(FinnV2OperationRegistry().get("explain_financial_concept"),),
        facts={},
        verified_context=None,
    )

    assert selection is None
    assert error == "selector_schema_contract_error"


def test_provider_429_remains_rate_limited_for_the_selector():
    selector = FinnV2StructuredOperationSelectorService(
        provider=lambda **_kwargs: {"error": "ai_rate_limited"}
    )
    selection, error = selector.select(
        message="Wat betekent RSI?",
        candidate_contracts=(FinnV2OperationRegistry().get("explain_financial_concept"),),
        facts={},
        verified_context=None,
    )

    assert selection is None
    assert error == "selector_ai_rate_limited"


def test_provider_rate_limit_metadata_preserves_retry_after():
    error = Exception("rate limit reached")
    error.response = SimpleNamespace(status_code=429, headers={"retry-after": "7", "x-request-id": "req-rate"})

    assert openai_client._is_rate_limited_exception(error) is True
    assert openai_client._retry_after_seconds(error) == 7.0
    assert openai_client._read_request_id(error) == "req-rate"
