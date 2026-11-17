from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
import asyncio
import pytest

from backend.schemas.finn_v2_confirmation_schema import FinnV2ConfirmationRequest
from backend.services.finn_v2_confirmation_service import FinnV2ConfirmationService


def test_superseded_proposal_cannot_be_published_or_confirmed():
    service = FinnV2ConfirmationService(session=object())
    proposal = SimpleNamespace(id="old-proposal", status="cancelled")
    service.proposals.get_by_id_for_user = lambda **_kwargs: asyncio.sleep(0, result=proposal)
    with pytest.raises(ValueError, match="proposal_not_pending_confirmation"):
        asyncio.run(service.issue_confirmation_token(proposal_id=proposal.id, user_id=7))
    with pytest.raises(ValueError, match="proposal_not_pending_confirmation"):
        asyncio.run(service.confirm(
            user_id=7,
            request=FinnV2ConfirmationRequest(
                proposal_id=proposal.id, confirmation_token="old-token",
                expected_payload_hash="old-hash",
            ),
        ))


def test_confirmation_accepts_valid_token_and_is_idempotent(monkeypatch):
    monkeypatch.setenv("FINN_V2_CONFIRMATION_SECRET", "secret")
    service = FinnV2ConfirmationService(session=object())
    workflow_events = []
    service.runtime_contracts.record_proposal_lifecycle = lambda **kwargs: asyncio.sleep(0, result=workflow_events.append(kwargs))
    service.flags.is_confirmations_enabled = lambda: True
    proposal = SimpleNamespace(
        id="proposal-1",
        run_id="run-1",
        user_id=7,
        payload_hash="payload-hash",
        operation_type="update_setup",
        status="pending_confirmation",
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
    )
    service.proposals.get_by_id_for_user = lambda **_kwargs: asyncio.sleep(0, result=proposal)
    service.proposals.update_status = lambda *_args, **_kwargs: asyncio.sleep(0, result=proposal)

    raw_token = "token-1"
    token_hash = service._token_hash(
        proposal_id="proposal-1",
        user_id=7,
        payload_hash="payload-hash",
        expires_at=proposal.expires_at,
        raw_token=raw_token,
    )
    confirmation = SimpleNamespace(
        id="confirmation-1",
        proposal_id="proposal-1",
        user_id=7,
        token_hash=token_hash,
        payload_hash="payload-hash",
        confirmed=False,
        already_confirmed=False,
        created_at=datetime.now(timezone.utc),
    )
    service.confirmations.get_for_proposal_user = lambda **_kwargs: asyncio.sleep(0, result=confirmation)
    service.confirmations.update = lambda row, **kwargs: asyncio.sleep(0, result=SimpleNamespace(**{**row.__dict__, **kwargs}))

    request = FinnV2ConfirmationRequest(proposal_id="proposal-1", confirmation_token=raw_token, expected_payload_hash="payload-hash")
    first = asyncio.run(service.confirm(user_id=7, request=request))
    confirmation.confirmed = True
    second = asyncio.run(service.confirm(user_id=7, request=request))

    assert first.confirmed is True
    assert second.already_confirmed is True
    assert [event["event"] for event in workflow_events] == ["confirmed", "confirmed"]


def test_confirmation_issue_token_accepts_route_enabled_mode_without_legacy_flag(monkeypatch):
    monkeypatch.delenv("FINN_V2_CONFIRMATION_SECRET", raising=False)
    monkeypatch.setenv("JWT_SECRET_KEY", "jwt-secret")

    service = FinnV2ConfirmationService(session=object())
    workflow_events = []
    service.runtime_contracts.record_proposal_lifecycle = lambda **kwargs: asyncio.sleep(0, result=workflow_events.append(kwargs))
    service.flags.is_confirmations_enabled = lambda: False
    service.flags.is_confirmation_routes_enabled = lambda: True
    proposal = SimpleNamespace(
        id="proposal-1",
        run_id="run-1",
        user_id=7,
        payload_hash="payload-hash",
        operation_type="create_strategy",
        status="draft",
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
    )
    service.proposals.get_by_id_for_user = lambda **_kwargs: asyncio.sleep(0, result=proposal)
    service.confirmations.get_for_proposal_user = lambda **_kwargs: asyncio.sleep(0, result=None)
    service.confirmations.create = lambda **kwargs: asyncio.sleep(0, result=SimpleNamespace(**kwargs))
    service.proposals.update_status = lambda *_args, **_kwargs: asyncio.sleep(0, result=proposal)

    raw_token, _ = asyncio.run(service.issue_confirmation_token(proposal_id="proposal-1", user_id=7))

    assert len(raw_token) >= 43
    assert workflow_events[0]["event"] == "confirmation_issued"


def test_confirmation_commits_before_returning_confirmed(monkeypatch):
    monkeypatch.setenv("FINN_V2_CONFIRMATION_SECRET", "secret")

    class Session:
        def __init__(self):
            self.commits = 0

        async def commit(self):
            self.commits += 1

    session = Session()
    service = FinnV2ConfirmationService(session=session)
    service.runtime_contracts.record_proposal_lifecycle = lambda **_kwargs: asyncio.sleep(0)
    proposal = SimpleNamespace(
        id="proposal-1", run_id="run-1", user_id=7, payload_hash="payload-hash",
        operation_type="create_strategy", status="pending_confirmation",
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
    )
    token = "token-1"
    confirmation = SimpleNamespace(
        id="confirmation-1", proposal_id="proposal-1", user_id=7,
        token_hash=service._token_hash(
            proposal_id=proposal.id, user_id=7, payload_hash=proposal.payload_hash,
            expires_at=proposal.expires_at, raw_token=token,
        ),
        payload_hash=proposal.payload_hash, confirmed=False, already_confirmed=False,
        created_at=datetime.now(timezone.utc),
    )
    service.proposals.get_by_id_for_user = lambda **_kwargs: asyncio.sleep(0, result=proposal)
    service.confirmations.get_for_proposal_user = lambda **_kwargs: asyncio.sleep(0, result=confirmation)
    service.confirmations.update = lambda row, **kwargs: asyncio.sleep(0, result=SimpleNamespace(**{**row.__dict__, **kwargs}))
    service.proposals.update_status = lambda *_args, **_kwargs: asyncio.sleep(0, result=proposal)

    result = asyncio.run(service.confirm(
        user_id=7,
        request=FinnV2ConfirmationRequest(
            proposal_id=proposal.id, confirmation_token=token, expected_payload_hash=proposal.payload_hash,
        ),
    ))

    assert result.confirmed is True
    assert session.commits == 1


def test_owner_can_cancel_draft_proposal_and_replay_is_idempotent():
    class Session:
        def __init__(self):
            self.commits = 0

        async def commit(self):
            self.commits += 1

    session = Session()
    service = FinnV2ConfirmationService(session=session)
    events = []
    proposal = SimpleNamespace(
        id="proposal-1", run_id="run-1", user_id=7, payload_hash="payload-hash",
        operation_type="update_bot", status="draft",
    )
    service.proposals.get_by_id_for_user = lambda **_kwargs: asyncio.sleep(0, result=proposal)

    async def update_status(row, *, status):
        row.status = status
        return row

    service.proposals.update_status = update_status
    service.runtime_contracts.record_proposal_lifecycle = lambda **kwargs: asyncio.sleep(0, result=events.append(kwargs))

    first = asyncio.run(service.cancel(proposal_id="proposal-1", user_id=7))
    replay = asyncio.run(service.cancel(proposal_id="proposal-1", user_id=7))

    assert first == {"proposal_id": "proposal-1", "status": "cancelled", "already_cancelled": False}
    assert replay == {"proposal_id": "proposal-1", "status": "cancelled", "already_cancelled": True}
    assert [event["event"] for event in events] == ["cancelled"]
    assert session.commits == 1


def test_cancelled_latest_proposal_retires_only_its_own_responses_cursor(monkeypatch):
    from backend.infrastructure.repositories.finn_v2_conversation_repository import FinnV2ConversationRepository
    from backend.infrastructure.repositories.finn_v2_run_repository import FinnV2RunRepository

    class Session:
        async def execute(self, _query):
            raise AssertionError("owner lookup is stubbed below")
        async def commit(self):
            pass

    session = Session()
    proposal = SimpleNamespace(
        id="proposal-1", run_id="run-1", user_id=7,
        payload_hash="hash", operation_type="update_indicator", status="draft",
    )
    service = FinnV2ConfirmationService(session=session)
    service.proposals.get_by_id_for_user = lambda **_kwargs: asyncio.sleep(0, result=proposal)
    async def update_status(row, *, status):
        row.status = status
    service.proposals.update_status = update_status
    service._record_workflow_event = lambda *_args, **_kwargs: asyncio.sleep(0)
    service._resolve_feed_proposal = lambda *_args, **_kwargs: asyncio.sleep(0)
    monkeypatch.setattr(FinnV2RunRepository, "get_by_id_for_user",
                        lambda _self, **_kwargs: asyncio.sleep(0, result=SimpleNamespace(
                            id="run-1", conversation_id="conversation-1")))
    calls = []
    async def clear(_self, **kwargs):
        calls.append(kwargs)
        return True
    monkeypatch.setattr(FinnV2ConversationRepository, "clear_cancelled_proposal_continuation", clear)
    asyncio.run(service.cancel(proposal_id="proposal-1", user_id=7))
    assert calls == [{"conversation_id": "conversation-1", "user_id": 7,
                      "run_id": "run-1", "proposal_id": "proposal-1"}]


def test_cancelled_proposal_cursor_cleanup_keeps_newer_conversation_state():
    from backend.infrastructure.repositories.finn_v2_conversation_repository import FinnV2ConversationRepository
    from backend.domain.finn_v2_runtime_contract import RuntimeContractConflictError

    row = SimpleNamespace(last_run_id="run-1", context_json={
        "session_id": "conversation-session",
        "responses_cursor": {"run_id": "run-1", "response_id": "old-response"},
        "proposal_revision": {"proposal_id": "proposal-1"},
        "active_guided_operation": {"open_proposal_id": "proposal-1"},
        "operation_state": {"status": "collecting"},
        "active_conversation_target": {"asset": "AAPL"},
    }, updated_at=None)
    repository = FinnV2ConversationRepository(SimpleNamespace())
    async def get_row(conversation_id, user_id, *, for_update=False):
        assert (conversation_id, user_id, for_update) == ("conversation-1", 7, True)
        return row
    repository.get_by_id_for_user = get_row
    flushed = []
    async def flush(**kwargs):
        flushed.append(kwargs)
    repository._flush_with_rollback = flush
    clear = lambda: repository.clear_cancelled_proposal_continuation(
        conversation_id="conversation-1", user_id=7,
        run_id="run-1", proposal_id="proposal-1",
    )
    assert asyncio.run(clear()) is True
    assert row.context_json == {"session_id": "conversation-session",
                                "cancelled_proposal_run_id": "run-1",
                                "cancelled_proposal_id": "proposal-1",
                                "active_conversation_target": {"asset": "AAPL"}}
    assert len(flushed) == 1
    asyncio.run(repository.update_context(
        conversation_id="conversation-1", user_id=7,
        context={"session_id": "conversation-session", "responses_cursor": {
            "run_id": "run-1", "response_id": "stale-snapshot",
        }, "proposal_revision": {"proposal_id": "proposal-1"},
            "active_guided_operation": {"open_proposal_id": "proposal-1"},
            "operation_state": {"status": "collecting"}},
    ))
    assert row.context_json["cancelled_proposal_run_id"] == "run-1"
    assert row.context_json["cancelled_proposal_id"] == "proposal-1"
    assert "responses_cursor" not in row.context_json
    assert "proposal_revision" not in row.context_json
    assert "active_guided_operation" not in row.context_json
    with pytest.raises(RuntimeContractConflictError, match="responses_cursor_cancelled_proposal"):
        asyncio.run(repository.set_responses_cursor(
            conversation_id="conversation-1", user_id=7,
            run_id="run-1", response_id="late-provider-response",
        ))
    assert "responses_cursor" not in row.context_json
    row.last_run_id = "run-2"
    row.context_json = {"responses_cursor": {"run_id": "run-2", "response_id": "new"}}
    assert asyncio.run(clear()) is False
    assert row.context_json["responses_cursor"]["response_id"] == "new"
    assert len(flushed) == 2
