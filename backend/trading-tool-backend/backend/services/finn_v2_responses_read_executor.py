"""Expose existing owner-scoped FINN read adapters to the Responses loop."""

from __future__ import annotations

import os
from typing import Any, Callable

from backend.domain.macro_indicator_catalog import get_active_macro_indicator_definitions
from backend.domain.finn_v2_operation_registry import FinnV2OperationRegistry
from backend.domain.finn_v2_tools import TOOL_FRESHNESS_MAX_AGE_SECONDS
from backend.domain.strategy_level_geometry import strategy_level_geometry
from backend.schemas.finn_v2_evidence_schema import ActiveSetupData
from backend.services.finn_v2_json_safety import to_json_safe
from backend.services.finn_v2_responses_tool_catalog import FinnResponsesToolCall
from backend.services.finn_v2_tool_execution_service import FinnV2ToolExecutionService


class FinnResponsesReadExecutor:
    @staticmethod
    def _facts_only_local_experiment() -> bool:
        return (
            os.getenv("APP_ENV") == "local_finn"
            and (
                os.getenv("FINN_SIMPLE_COACH_EXPERIMENT") == "1"
                or os.getenv("FINN_FACTS_ONLY_TOOL_RESULTS_EXPERIMENT") == "1"
            )
        )

    @staticmethod
    def _setup_facts_for_local_experiment(data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        saved = data.get("data") if isinstance(data.get("data"), dict) else data
        fields = (
            "name", "symbol", "timeframe", "setup_type", "dca_frequency",
            "dca_day_name", "dca_month_day", "min_investment",
        )
        return {
            "fields": {key: saved[key] for key in fields if saved.get(key) is not None},
            "available_setup_fields": [
                key for key in fields if key in getattr(ActiveSetupData, "model_fields", ActiveSetupData.__fields__)
            ],
            "not_recorded_fields": [
                key for key in fields if saved.get(key) is None and (
                    (key == "dca_day_name" and saved.get("dca_frequency") == "weekly")
                    or (key == "dca_month_day" and saved.get("dca_frequency") == "monthly")
                )
            ],
            "setups": [
                {key: row[key] for key in ("name", "symbol", "timeframe", "setup_type")
                 if row.get(key) is not None}
                for row in saved.get("setups") or [] if isinstance(row, dict)
            ],
        }

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
                    as_of = str(result.as_of) if getattr(result, "as_of", None) else self._as_of(data)
            else:
                result = await self.reads.execute_tool(
                    run_id=self.run_id, user_id=self.user_id, tool_name=read_tool,
                    selector=call.inputs, shared_state=shared_state,
                )
                data = to_json_safe(result.result) if result.success else None
                as_of = str(result.as_of) if getattr(result, "as_of", None) else self._as_of(data)
            if read_tool == "read_linked_strategy" and isinstance(data, dict):
                data = {**data, "level_geometry": strategy_level_geometry(
                    data.get("entry"), data.get("stop_loss"), data.get("targets"),
                )}
            if read_tool == "read_active_setup" and self._facts_only_local_experiment():
                data = self._setup_facts_for_local_experiment(data)
            evidence = {
                "scope": read_tool,
                "status": "completed" if result.success else "unavailable",
                "availability": result.availability,
                "freshness": result.freshness_status,
                "source": result.source,
                "as_of": as_of,
                "asset": result.asset or call.inputs.get("asset"),
                "data": data,
                "reason": result.error_codes[0] if result.error_codes else None,
            }
            if read_tool == "read_active_asset" and result.success:
                evidence["resolution_source"] = shared_state.get("resolution_source")
            results.append(evidence)
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
            if "hypothetical_change" in contract.optional_inputs and call.inputs.get("hypothetical_change"):
                output["hypothetical_scenario"] = {
                    "change": call.inputs["hypothetical_change"],
                    "status": "user_proposed_not_saved",
                    "assessment": "not_established_by_scenario_alone",
                }
            def scope_available(scope: str, tool: str) -> bool:
                for item in results:
                    if item["scope"] != tool or item["status"] != "completed":
                        continue
                    if scope == "profile" and not (
                        isinstance(item.get("data"), dict)
                        and item["data"].get("has_profile") is True
                    ):
                        return False
                    if TOOL_FRESHNESS_MAX_AGE_SECONDS.get(tool) is not None:
                        return item.get("freshness") == "fresh" and bool(item.get("as_of"))
                    return True
                return False

            output["missing_required_scopes"] = [
                scope for scope, tool in contract.scope_tool_bindings
                if scope in contract.required_scopes and not scope_available(scope, tool)
            ]
            output["assessment_status"] = (
                "insufficient_evidence" if output["missing_required_scopes"]
                else "evidence_collected_not_yet_judged"
            )
            available_scopes = {
                scope for scope, tool in contract.scope_tool_bindings
                if scope_available(scope, tool)
            }
            dimensions = (("full_assessment", contract.required_scopes),) + contract.evidence_dimensions
            output["evidence_coverage"] = {
                name: {
                    "status": "available" if set(scopes) <= available_scopes else "incomplete",
                    "missing_scopes": [scope for scope in scopes if scope not in available_scopes],
                }
                for name, scopes in dimensions
            }
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
            if contract.operation_id == "evaluate_portfolio":
                output["assessment_boundary"] += (
                    " A Paper bot is configuration, not a live position or executed trade; "
                    "is_active does not override is_live=false. A budget limit is not available "
                    "cash, invested capital, or realized performance. An empty profile limits "
                    "personal suitability assessment, even when the profile read succeeded. "
                    "Do not suggest putting money to work merely because invested value is zero."
                )
        if call.name == "get_active_plan_and_strategy":
            output["evidence_boundary"] = (
                "This is a read of saved setup and strategy configuration, not a current market "
                "or owner-scoped risk evaluation. A numeric dca_day is a stored weekday code, "
                "not a user-facing day; use dca_day_name and translate it into the answer language. "
                "A chart timeframe, DCA frequency, and broad profile goal do not record the "
                "owner's holding horizon. Ask for the intended period before classifying the "
                "saved setup as long-term accumulation or short-term trading. "
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
        if call.name == "get_portfolio_and_exposure":
            output["evidence_boundary"] = (
                "Each bots[].budget_total_eur is that saved Paper-bot's own budget. "
                "global.total_budget_limit is the sum across the selected bots, not a "
                "separate budget for one bot. When asked about a particular bot's budget, "
                "use its matching bot row and never say its budget is missing when that "
                "field is present. A budget limit is not available cash or invested capital. "
                "data.read_at is when FINN fetched the records, not the date of a market price. "
                "A bot's price_as_of is its market-price date; the outer as_of is the oldest "
                "required price date when a valuation is available. If valuation_available is "
                "false, do not infer cash or equity from budgets. Translate technical field "
                "names such as as_of into natural language."
            )
        if any(
            item["scope"] == "read_asset_scores" and item["status"] == "completed"
            for item in results
        ):
            output["evidence_boundary"] = (
                "A dated score is a historical report, not a current market reading. "
                "When reporting exact saved scores, name their report date and actual freshness status. "
                "Use one short paragraph without headings or a raw backend inventory. "
                "Do not infer a present trading signal, personal suitability, or a missing score as zero. "
                "Do not offer to refresh or repeat a score assessment when no fresh score source is available."
            )
        if self._facts_only_local_experiment():
            output.pop("evidence_boundary", None)
            output.pop("assessment_boundary", None)
            if call.name == "get_my_profile_and_risk_style":
                output["evidence_kind"] = "saved_profile_preferences"
                output["assessment_status"] = "not_assessed"
            elif call.name == "get_active_plan_and_strategy":
                output["evidence_kind"] = "saved_plan_configuration"
                output["assessment_status"] = "not_assessed"
        return output

    @staticmethod
    def _as_of(data: Any) -> str | None:
        if isinstance(data, dict):
            value = data.get("as_of") or data.get("timestamp")
            if value:
                return str(value)
            daily_scores = data.get("daily_scores")
            if isinstance(daily_scores, dict) and daily_scores.get("report_date"):
                return str(daily_scores["report_date"])
            master_score = data.get("master_score")
            if isinstance(master_score, dict) and master_score.get("date"):
                return str(master_score["date"])
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
