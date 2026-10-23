from backend.scripts.run_finn_v2_selector_eval import _canonical_eval_conversation_context, retry_delay
from backend.services.finn_v2_selector_eval_registry import SelectorEvalCase


def test_lineage_eval_case_receives_a_canonical_non_sensitive_precondition():
    case = SelectorEvalCase(
        eval_id="runner-lineage",
        dataset="regression",
        input_query="Explain the evidence behind that answer.",
        expected_operation_id="explain_previous_evidence",
        expected_domain="system",
        expected_supported=True,
        expected_conversation_reference="previous_verified_response",
        expected_missing_inputs=[],
    )

    context = _canonical_eval_conversation_context(case)

    assert context["last_verified_context"]["verified_response_id"] == "previous_verified_response"
    assert context["last_verified_context"]["resolved_entities"]["bot_id"] == 170


def test_provider_eval_retries_transient_service_failure_but_not_contract_failure():
    transient = {
        "failure_category": "provider",
        "error": "provider_error",
        "provider_metadata": {"http_status": 503},
    }
    assert retry_delay(transient, attempt=1, base_seconds=5) == 5
    assert retry_delay({**transient, "provider_metadata": {"http_status": 401}}, attempt=1, base_seconds=5) is None
    assert retry_delay({**transient, "failure_category": "schema"}, attempt=1, base_seconds=5) is None
