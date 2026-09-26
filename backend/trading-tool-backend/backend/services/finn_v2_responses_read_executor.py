"""Expose existing owner-scoped FINN read adapters to the Responses loop."""

from __future__ import annotations

from typing import Any, Callable

from backend.domain.macro_indicator_catalog import get_active_macro_indicator_definitions
from backend.domain.finn_v2_operation_registry import FinnV2OperationRegistry
from backend.domain.strategy_level_geometry import strategy_level_geometry
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
                    "Explain only the preceding verified answer and its already verified evidence. "
                    "Do not turn a stored DCA setup into a saved strategy or infer personal fit "
                    "that the preceding answer explicitly withheld. No new facts were fetched."
                    if call.inputs.get("uses_previous_response") else
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
            if read_tool == "read_linked_strategy" and isinstance(data, dict):
                data = {**data, "level_geometry": strategy_level_geometry(
                    data.get("entry"), data.get("stop_loss"), data.get("targets"),
                )}
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
            if read_tool == "read_indicator_configuration":
                results.append(self._macro_catalog_evidence())
        output = {
            "status": "completed" if all(item["status"] == "completed" for item in results) else "partial",
            "tool": call.name,
            "results": results,
        }
        if call.name == "get_my_profile_and_risk_style":
            output["evidence_boundary"] = (
                "These are saved owner preferences, not a suitability assessment or a trading "
                "recommendation. If asked what FINN can help with, briefly offer to explain "
                "saved choices, examine a plan with additional evidence, or prepare an action "
                "for explicit confirmation. Do not infer that a particular strategy, method, "
                "asset, timeframe or expected growth is safe or suitable from profile labels. "
                "Do not promise protected returns or secure investment methods. If the profile "
                "is empty, ask naturally for the user's goal and risk style."
            )
        if call.evaluation_operation_id:
            contract = FinnV2OperationRegistry().require_supported(call.evaluation_operation_id)
            if contract.mode != "EVALUATE":
                return {"status": "unavailable", "reason": "evaluation_contract_invalid"}
            completed = {item["scope"] for item in results if item["status"] == "completed"}
            output["evaluation_operation_id"] = contract.operation_id
            output["missing_required_scopes"] = [
                scope for scope, tool in contract.scope_tool_bindings
                if scope in contract.required_scopes and tool not in completed
            ]
            output["assessment_status"] = (
                "insufficient_evidence" if output["missing_required_scopes"]
                else "evidence_collected_not_yet_judged"
            )
            output["resolved_entity_kinds"] = {
                "setup": "read_active_setup" in completed,
                "strategy": "read_linked_strategy" in completed,
                "bot": "read_linked_bot" in completed,
            }
            output["assessment_boundary"] = (
                "These are owner-scoped source facts, not an assessment. A saved setup is not a "
                "saved strategy. When assessment_status is insufficient_evidence, do not assert "
                "personal suitability, risk alignment, or a trading recommendation. Explain which "
                "required source is missing and what the user can decide next. Write a brief coach "
                "answer with a conclusion, a reason and one relevant next step; do not enumerate "
                "profile fields or suggest an indicator unless the user asked for one. "
                "Static level_geometry from a verified linked strategy may be explained even "
                "when live market sources are missing. Its ratios do not establish current "
                "entry conditions, probability of success, or personal suitability. When the "
                "user requests a review, distinguish one verifiable structural strength from "
                "one concrete missing or risky condition and one next check; do not replace "
                "that review with only a missing-data statement."
            )
            if contract.operation_id == "evaluate_indicator_configuration":
                output["assessment_boundary"] += (
                    " A saved configuration and the catalog can establish which indicator "
                    "is not configured even when live market snapshots are unavailable. If the "
                    "user asks for a missing indicator, name at most one catalog-supported "
                    "candidate and explain its general role. Do not claim it improves returns "
                    "or is personally suitable without a separate assessment."
                )
        if call.name == "get_active_plan_and_strategy":
            output["evidence_boundary"] = (
                "This is a read of saved setup and strategy configuration, not a current market "
                "or owner-scoped risk evaluation. A numeric dca_day is a stored weekday code, "
                "not a user-facing day; use dca_day_name and translate it into the answer language. "
                "A chart timeframe and DCA frequency do not record the owner's holding horizon. "
                "Stored entry, stop-loss, target and amount values "
                "must be described as existing settings, never as an instruction to trade at "
                "those levels or as proof that this plan suits the user's goals or risk style. "
                "For a factual readback, answer only the fields the user asked about; do not add "
                "an unsolicited suitability warning or suggest a trade. For a question about "
                "following a rule the user says they have, distinguish that user statement "
                "from verified saved fields. Give a brief conditional process answer: what "
                "the rule would require checking and why FOMO alone does not prove its "
                "conditions are met. Do not recite unrelated setup fields. Do not claim "
                "the current market satisfies the rule. If the user asks whether a trade "
                "is personally suitable now, say which evaluation is still needed."
            )
        return output

    @staticmethod
    def _as_of(data: Any) -> str | None:
        if isinstance(data, dict):
            value = data.get("as_of") or data.get("timestamp")
            if value:
                return str(value)
        return None

    @staticmethod
    def _macro_catalog_evidence() -> dict[str, Any]:
        return {
            "scope": "available_macro_indicator_catalog",
            "status": "completed", "availability": "available", "freshness": "not_applicable",
            "source": "macro_indicator_catalog", "as_of": None, "asset": None,
            "data": {
                "supported_options": [
                    {"name": item["name"], "display_name": item["display_name"]}
                    for item in get_active_macro_indicator_definitions()
                ],
                "proposal_operation_id": "create_indicator_configuration",
            },
            "reason": None,
        }
