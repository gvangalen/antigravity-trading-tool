from types import SimpleNamespace
import asyncio

from backend.services.finn_v2_tool_execution_service import FinnV2ToolExecutionService


class _MissingRunRepo:
    async def get_by_id_for_user(self, *, run_id, user_id):
        return None


def test_tool_execution_hides_run_ownership_details():
    service = FinnV2ToolExecutionService(session=object())
    service.runs = _MissingRunRepo()
    service.flags.is_tool_registry_enabled = lambda: True
    service.flags.is_tool_registry_readonly = lambda: True

    result = asyncio.run(service.execute_tool(run_id="run-1", user_id=7, tool_name="read_profile", selector={}))

    assert result.error_codes == ["tool_run_not_owned"]
