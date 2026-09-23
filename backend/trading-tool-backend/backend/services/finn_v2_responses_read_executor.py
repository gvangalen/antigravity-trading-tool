"""Expose existing owner-scoped FINN read adapters to the Responses loop."""

from __future__ import annotations

from typing import Any, Callable

from backend.services.finn_v2_json_safety import to_json_safe
from backend.services.finn_v2_responses_tool_catalog import FinnResponsesToolCall
from backend.services.finn_v2_tool_execution_service import FinnV2ToolExecutionService


class FinnResponsesReadExecutor:
    def __init__(
        self, *, session: Any = None, session_factory: Callable[[], Any] | None = None,
        user_id: int, run_id: str,
    ) -> None:
        if session is None and session_factory is None:
            raise ValueError("read_session_required")
        self.user_id = user_id
        self.run_id = run_id
        self.session_factory = session_factory
        self.reads = FinnV2ToolExecutionService(session) if session is not None else None

    async def __call__(self, call: FinnResponsesToolCall) -> dict[str, Any]:
        if call.name == "answer_directly":
            return {
                "status": "completed", "results": [],
                "evidence_boundary": (
                    "No owner-scoped or market facts have been fetched. General educational explanation "
                    "is allowed. For any judgment about this user's plan, profile, portfolio, indicators "
                    "or current market, call relevant FINN read tools before the final answer."
                ),
            }
        if call.operation_id is not None:
            return {
                "status": "unavailable",
                "reason": "proposal_runtime_not_connected",
                "missing_inputs": list(call.missing_inputs),
            }
        results: list[dict[str, Any]] = []
        shared_state: dict[str, Any] = {}
        for read_tool in call.read_tools:
            if getattr(self, "session_factory", None) is not None:
                async with self.session_factory() as session:
                    result = await FinnV2ToolExecutionService(session).execute_tool(
                        run_id=self.run_id, user_id=self.user_id, tool_name=read_tool,
                        selector=call.inputs, shared_state=shared_state,
                    )
                    data = to_json_safe(result.result) if result.success else None
                    as_of = self._as_of(data)
            else:
                result = await self.reads.execute_tool(
                    run_id=self.run_id, user_id=self.user_id, tool_name=read_tool,
                    selector=call.inputs, shared_state=shared_state,
                )
                data = to_json_safe(result.result) if result.success else None
                as_of = self._as_of(data)
            results.append({
                "scope": read_tool,
                "status": "completed" if result.success else "unavailable",
                "availability": result.availability,
                "freshness": result.freshness_status,
                "source": result.source,
                "as_of": as_of,
                "asset": result.asset or call.inputs.get("asset"),
                "data": data,
                "reason": result.error_codes[0] if result.error_codes else None,
            })
        return {
            "status": "completed" if all(item["status"] == "completed" for item in results) else "partial",
            "tool": call.name,
            "results": results,
        }

    @staticmethod
    def _as_of(data: Any) -> str | None:
        if isinstance(data, dict):
            value = data.get("as_of") or data.get("timestamp")
            if value:
                return str(value)
        return None
