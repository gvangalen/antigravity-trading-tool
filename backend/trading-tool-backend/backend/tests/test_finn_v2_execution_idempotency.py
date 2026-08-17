import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace

from backend.services.finn_v2_execution_service import FinnV2ExecutionService


class _Session:
    async def flush(self):
        return None


def test_execution_service_returns_existing_result_for_same_idempotency_key():
    service = FinnV2ExecutionService(session=_Session())
    service.repo.get_by_idempotency_key_for_user = lambda **kwargs: asyncio.sleep(
        0,
        result=SimpleNamespace(
            id="exec-1",
            proposal_id="proposal-1",
            user_id=7,
            operation_type="update_setup",
            status="succeeded",
            idempotency_key="idem-1234",
            precondition_hash="pre",
            postcondition_hash="post",
            error_codes_json=[],
            started_at=datetime.now(timezone.utc),
            completed_at=datetime.now(timezone.utc),
        ),
    )

    result = asyncio.run(
        service.execute(
            proposal_id="proposal-1",
            user_id=7,
            idempotency_key="idem-1234",
            expected_payload_hash="hash-1",
        )
    )

    assert result.status == "already_executed"
    assert result.postcondition_hash == "post"
