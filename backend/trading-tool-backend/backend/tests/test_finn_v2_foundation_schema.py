from typing import get_args

import pytest
from pydantic import ValidationError

from backend.schemas.finn_v2_schema import (
    AgentRunRequest,
    InteractionMode,
    ResponseSource,
    RunStatus,
    VerifiedResponse,
)


def test_finn_v2_schema_literals_match_contract():
    assert get_args(InteractionMode) == (
        "FACT",
        "EVALUATION",
        "PROPOSAL",
        "ACTION",
        "CLARIFICATION",
        "UNAVAILABLE",
    )
    assert get_args(RunStatus) == (
        "created",
        "collecting",
        "planned",
        "blocked",
        "completed",
        "failed",
        "canceled",
    )
    assert get_args(ResponseSource) == (
        "foundation_placeholder",
        "v1_adapter",
        "v2_runtime",
    )


def test_agent_run_request_enforces_message_limits():
    with pytest.raises(ValidationError):
        AgentRunRequest(message="")
    with pytest.raises(ValidationError):
        AgentRunRequest(message="x" * 4001)
    assert AgentRunRequest(message="ok").message == "ok"


def test_agent_run_request_mutable_defaults_are_isolated():
    left = AgentRunRequest(message="left")
    right = AgentRunRequest(message="right")

    left.workspace_hints["asset"] = "BTC"
    left.client_context["surface"] = "assistant"

    assert right.workspace_hints == {}
    assert right.client_context == {}


def test_agent_run_request_rejects_user_owned_or_action_fields():
    with pytest.raises(ValidationError):
        AgentRunRequest(message="hi", user_id=7)
    with pytest.raises(ValidationError):
        AgentRunRequest(message="hi", action={"type": "execute"})
    with pytest.raises(ValidationError):
        AgentRunRequest(message="hi", tools=["bad"])


def test_verified_response_defaults_are_safe_placeholders():
    response = VerifiedResponse()

    assert response.mode == "UNAVAILABLE"
    assert response.response_source == "foundation_placeholder"
    assert response.verifier_status == "not_run"
    assert response.evidence == []
    assert response.uncertainty == []
    assert response.confirmation_required is False
