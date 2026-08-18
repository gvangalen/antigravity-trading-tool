import asyncio

import pytest

from backend.infrastructure.repositories.finn_v2_repository_transaction_mixin import FinnV2RepositoryTransactionMixin


class _FailingSession:
    def __init__(self):
        self.rollback_calls = 0

    async def flush(self):
        raise TypeError("datetime not json serializable")

    async def rollback(self):
        self.rollback_calls += 1


class _TestRepository(FinnV2RepositoryTransactionMixin):
    def __init__(self, session):
        self.session = session


def test_flush_failure_triggers_immediate_rollback():
    session = _FailingSession()
    repo = _TestRepository(session)

    with pytest.raises(TypeError, match="datetime not json serializable"):
        asyncio.run(
            repo._flush_with_rollback(
                operation="create",
                entity_type="FinnV2Proposal",
                run_id="run-123",
            )
        )

    assert session.rollback_calls == 1
