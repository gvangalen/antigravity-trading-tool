import asyncio

from backend.services.finn_v2_tool_execution_service import FinnV2ToolExecutionService


class _Repo:
    def __init__(self, count):
        self.count = count

    async def redact_payloads_older_than(self, cutoff):
        return self.count


class _ToolCallsRepo:
    async def redact_results_older_than(self, cutoff):
        return 1

    async def delete_metadata_older_than(self, cutoff):
        return 2


def test_state_retention_redacts_evidence_state_and_validation_payloads():
    service = FinnV2ToolExecutionService(session=object())
    service.calls = _ToolCallsRepo()
    service.evidence_repo = _Repo(3)
    service.state_repo = _Repo(4)
    service.validation_repo = _Repo(5)

    result = asyncio.run(service.apply_retention())

    assert result["evidence_payloads_redacted"] == 3
    assert result["state_payloads_redacted"] == 4
    assert result["validation_payloads_redacted"] == 5

