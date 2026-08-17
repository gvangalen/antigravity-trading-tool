import asyncio

from backend.services.finn_v2_tool_execution_service import FinnV2ToolExecutionService


class _FakeToolCallRepo:
    async def redact_results_older_than(self, cutoff):
        return 2

    async def delete_metadata_older_than(self, cutoff):
        return 4


def test_tool_retention_redacts_results_before_metadata_deletion():
    service = FinnV2ToolExecutionService(session=object())
    service.calls = _FakeToolCallRepo()

    result = asyncio.run(service.apply_retention())

    assert result == {"tool_results_redacted": 2, "tool_metadata_deleted": 4}

