from backend.services.finn_v2_run_service import FinnV2RunService


class _NestedTxn:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _FakeSession:
    def begin_nested(self):
        return _NestedTxn()


class _FakeRunRepo:
    def __init__(self):
        self.redact_calls = []
        self.delete_calls = []

    async def redact_messages_older_than(self, cutoff):
        self.redact_calls.append(cutoff)
        return 3

    async def delete_traces_older_than(self, cutoff):
        self.delete_calls.append(cutoff)
        return 5


async def _run_retention():
    service = FinnV2RunService(_FakeSession())
    repo = _FakeRunRepo()
    service.runs = repo
    result = await service.apply_retention(message_days=30, trace_days=90)
    return repo, result


def test_retention_redacts_old_messages_and_deletes_old_traces():
    import asyncio

    repo, result = asyncio.run(_run_retention())

    assert result["messages_redacted"] == 3
    assert result["traces_deleted"] == 5
    assert result["tool_results_redacted"] == 0
    assert result["tool_metadata_deleted"] == 0
    assert len(repo.redact_calls) == 1
    assert len(repo.delete_calls) == 1
    assert repo.delete_calls[0] < repo.redact_calls[0]
