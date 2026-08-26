import os
from types import SimpleNamespace

import pytest


os.environ.setdefault("JWT_SECRET_KEY", "test-jwt-secret-key-for-platform-security-tests-123")
os.environ.setdefault("ENCRYPTION_KEY", "sT0oqYH7C78mMKBYz4MWVR84zDl6QwVn-fC3jNpt7NE=")


@pytest.fixture(autouse=True)
def finn_v2_structured_selector_test_double(monkeypatch):
    """Keep offline tests provider-shaped without restoring a runtime fallback.

    Production calls OpenAI through the strict selector.  The test double only
    supplies a typed structured response, so unit tests remain deterministic
    without an API key and cannot accidentally exercise an old runtime router.
    """
    from backend.domain.finn_v2_operation_registry import FinnV2OperationRegistry
    from backend.services.finn_v2_structured_operation_selector_service import (
        FinnV2StructuredOperationSelectorService,
    )

    registry = FinnV2OperationRegistry()

    from backend.utils import openai_client

    default_provider = openai_client.ask_gpt_structured_response
    original_select = FinnV2StructuredOperationSelectorService.select

    def select(self, *, facts, verified_context, **kwargs):
        if self._provider is not default_provider:
            return original_select(self, facts=facts, verified_context=verified_context, **kwargs)
        entities = tuple(facts.get("entities") or ())
        normalized = str(facts.get("normalized_text") or "")
        discourse = str(facts.get("discourse_act") or "information_request")
        action = str(facts.get("action_polarity") or "unknown")
        state = verified_context or {}
        verified = state.get("last_verified_context") if isinstance(state, dict) else None
        guided = state.get("active_guided_operation") if isinstance(state, dict) else None
        guided = guided or (state.get("operation_state") if isinstance(state, dict) else None)
        if str(facts.get("domain_hint") or "") == "off_topic":
            operation_id = "off_topic"
        elif (
            facts.get("financial_concept")
            and discourse == "information_request"
            and not facts.get("referenced_asset")
            and normalized.startswith(("wat betekent ", "wat is ", "what is ", "what does ", "leg uit", "uitleg"))
        ):
            operation_id = "explain_financial_concept"
        elif isinstance(guided, dict) and guided.get("missing_required_inputs") and discourse == "clarification_answer":
            operation_id = str(guided["operation_id"])
        elif verified and discourse == "evidence_follow_up":
            operation_id = "explain_previous_evidence"
        elif verified and discourse == "reformulation":
            operation_id = "reformulate_previous_response"
        elif "beste trade" in normalized or "best trade" in normalized:
            operation_id = "unavailable"
        else:
            candidates = registry.candidate_operations(
                entities=entities,
                action_polarity=action,
                discourse_act="information_request" if discourse == "contextual_follow_up" and not verified else discourse,
                has_verified_context=bool(verified),
                normalized_text=normalized,
            )
            operation_id = candidates[0].operation_id if candidates else "clarify_request"
        return SimpleNamespace(operation_id=operation_id, confidence=0.95), None

    monkeypatch.setattr(FinnV2StructuredOperationSelectorService, "select", select)
