import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from backend.services.finn_v2_execution_service import FinnV2ExecutionService


class _Session:
    async def flush(self):
        return None


def test_execution_service_records_postcondition_hash_on_success():
    service = FinnV2ExecutionService(session=_Session())
    service.repo.get_by_idempotency_key_for_user = lambda **kwargs: asyncio.sleep(0, result=None)
    service.proposals.get_by_id_for_user = lambda **kwargs: asyncio.sleep(
        0,
        result=SimpleNamespace(
            id="proposal-1",
            run_id="run-1",
            user_id=7,
            operation_type="update_setup",
            payload_hash="hash-1",
            payload_json={"change": {"setup_id": 9, "changed_fields": {"name": "BTC setup"}}},
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
        ),
    )
    service.gates.check_execution_eligibility = lambda **kwargs: asyncio.sleep(
        0,
        result=SimpleNamespace(eligible=True, dict=lambda: {"eligible": True}),
    )
    service.repo.create = lambda **kwargs: asyncio.sleep(0, result=SimpleNamespace(**kwargs))
    service.adapters.get = lambda operation_type: (lambda user_id, payload: asyncio.sleep(0, result={"ok": True, "setup_id": 9}))
    service.adapters.postcondition_hash = lambda operation_type, **kwargs: asyncio.sleep(0, result="post-hash-1")

    result = asyncio.run(
        service.execute(
            proposal_id="proposal-1",
            user_id=7,
            idempotency_key="idem-5678",
            expected_payload_hash="hash-1",
        )
    )

    assert result.status == "succeeded"
    assert result.postcondition_hash == "post-hash-1"
