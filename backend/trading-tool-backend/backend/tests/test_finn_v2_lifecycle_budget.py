import asyncio
from time import monotonic

from backend.services.finn_v2_lifecycle_budget import (
    remaining_lifecycle_seconds,
    reset_lifecycle_deadline,
    set_lifecycle_deadline,
)
from backend.services.finn_v2_response_verifier_service import FinnV2ResponseVerifierService
from backend.services.finn_v2_semantic_verifier_service import FinnV2SemanticVerifierService


def test_lifecycle_budget_is_task_local_and_reserves_terminal_time():
    token = set_lifecycle_deadline(monotonic() + 1.0)
    try:
        remaining = remaining_lifecycle_seconds(reserve_seconds=0.2)
        assert remaining is not None
        assert 0.6 < remaining < 0.9
    finally:
        reset_lifecycle_deadline(token)

    assert remaining_lifecycle_seconds() is None


def test_semantic_verifier_does_not_start_provider_when_terminal_budget_is_gone(monkeypatch):
    monkeypatch.setenv("FINN_V2_SEMANTIC_VERIFIER_ENABLED", "true")
    verifier = FinnV2SemanticVerifierService()
    token = set_lifecycle_deadline(monotonic() + 0.01)
    try:
        result = asyncio.run(
            verifier.verify_async(
                mode="EVALUATE",
                user_message="Is this plan suitable?",
                sanitized_draft={},
                compact_evidence=[],
                deterministic_summary={},
            )
        )
    finally:
        reset_lifecycle_deadline(token)

    assert result.available is False
    assert result.passes is False
    assert result.reason_codes == ["semantic_verifier_budget_exhausted"]


def test_verifier_releases_database_session_before_provider_work():
    committed = []

    class Session:
        async def commit(self):
            committed.append(True)

    service = FinnV2ResponseVerifierService(Session())
    asyncio.run(service._commit_before_provider_call())

    assert committed == [True]
