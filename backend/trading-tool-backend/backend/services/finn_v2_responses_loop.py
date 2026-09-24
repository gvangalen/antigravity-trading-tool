"""Bounded Responses function-calling loop; FINN remains the tool authority."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

from backend.services.finn_v2_responses_tool_catalog import (
    FinnResponsesToolCall,
    FinnResponsesToolCatalog,
    FinnResponsesToolError,
)
from backend.services.finn_v2_lifecycle_budget import remaining_lifecycle_seconds


logger = logging.getLogger(__name__)


class FinnResponsesError(RuntimeError):
    """A typed provider or tool-loop failure, never a legacy-chat fallback."""


@dataclass(frozen=True)
class FinnResponsesResult:
    text: str
    response_id: str
    tool_trace: tuple[dict[str, Any], ...]


class FinnResponsesLoop:
    def __init__(
        self,
        *,
        client: Any,
        executor: Callable[[FinnResponsesToolCall], Awaitable[dict[str, Any]]],
        catalog: FinnResponsesToolCatalog | None = None,
        model: str = "gpt-4o-mini",
        max_rounds: int = 4,
        provider_timeout_seconds: float = 12.0,
        tool_timeout_seconds: float = 4.0,
        max_tool_calls: int = 10,
        on_tool_result: Callable[[str, tuple[dict[str, Any], ...]], Awaitable[None]] | None = None,
    ) -> None:
        self.client = client
        self.executor = executor
        self.catalog = catalog or FinnResponsesToolCatalog()
        self.model = model
        self.max_rounds = max_rounds
        self.provider_timeout_seconds = provider_timeout_seconds
        self.tool_timeout_seconds = tool_timeout_seconds
        self.max_tool_calls = max_tool_calls
        self.on_tool_result = on_tool_result

    async def run(
        self,
        *,
        message: str,
        instructions: str,
        previous_response_id: str | None = None,
        previous_verified_answer: str | None = None,
        guided_operation_id: str | None = None,
        resuming_clarification: bool = False,
        previous_answer_only: bool = False,
    ) -> FinnResponsesResult:
        current_input: list[dict[str, Any]] = (
            [{"role": "assistant", "content": previous_verified_answer}]
            if previous_verified_answer else []
        ) + [{"role": "user", "content": message}]
        prior_id = previous_response_id
        trace: list[dict[str, Any]] = []
        seen_call_ids: set[str] = set()
        proposal_selected = False
        tool_rounds = 0
        repair_tool_name: str | None = None
        repair_attempts: dict[str, int] = {}
        repair_exhausted = False
        for _ in range(self.max_rounds):
            remaining = remaining_lifecycle_seconds()
            if remaining is not None and remaining <= 3.25:
                raise FinnResponsesError("responses_lifecycle_budget_exhausted")
            retry_target_domain = (
                str(trace[-1]["result"].get("target_domain") or "")
                if trace and trace[-1]["status"] == "retry" else None
            )
            provider_timeout = min(
                self.provider_timeout_seconds,
                remaining - 3.5 if remaining is not None else self.provider_timeout_seconds,
            )
            definitions = self.catalog.definitions(
                guided_operation_id=guided_operation_id if not trace else None,
                retry_target_domain=retry_target_domain,
            )
            if previous_answer_only:
                definitions = [item for item in definitions if item["name"] == "answer_directly"]
            resolved_choice_read = any(
                item.get("name") == "get_active_plan_and_strategy"
                and any(
                    result.get("scope") == "read_active_setup"
                    and result.get("status") == "completed"
                    for result in (item.get("result", {}).get("results") or [])
                )
                for item in trace
            )
            if resuming_clarification and resolved_choice_read:
                definitions = [
                    item for item in definitions
                    if item["name"] in {"ask_for_clarification", "answer_directly"}
                ]
            kwargs: dict[str, Any] = {
                "model": self.model,
                "instructions": (
                    instructions
                    + "\nFor this turn, explain only the previous verified answer. "
                    "No new market facts, historical analysis, suitability claim, "
                    "risk conclusion, or advice about changing levels. If the previous "
                    "answer says a current assessment is missing, explain why stored "
                    "settings alone cannot establish suitability; do not claim the "
                    "user's actual plan is risky or fits their goals."
                    if previous_answer_only else instructions
                ),
                "input": current_input,
                "tools": definitions,
                "parallel_tool_calls": False,
                "store": True,
                "max_output_tokens": 700 if not trace else 350,
            }
            if prior_id:
                kwargs["previous_response_id"] = prior_id
            if proposal_selected or repair_exhausted or (previous_answer_only and trace) or (tool_rounds >= 2 and not repair_tool_name):
                kwargs["tool_choice"] = "none"
            elif repair_tool_name:
                kwargs["tool_choice"] = {"type": "function", "name": repair_tool_name}
            elif not trace:
                kwargs["tool_choice"] = (
                    {"type": "function", "name": self.catalog.proposal_tool_for_operation(guided_operation_id)}
                    if guided_operation_id else "required"
                )
            elif trace[-1]["status"] == "retry":
                kwargs["tool_choice"] = "required"
            try:
                provider_started = time.perf_counter()
                provider_client = (
                    self.client.with_options(max_retries=0, timeout=provider_timeout)
                    if hasattr(self.client, "with_options") else self.client
                )
                response = await asyncio.wait_for(
                    provider_client.responses.create(**kwargs),
                    timeout=provider_timeout,
                )
                provider_elapsed_ms = round((time.perf_counter() - provider_started) * 1000, 2)
            except TimeoutError as exc:
                raise FinnResponsesError("responses_provider_timeout") from exc
            except Exception as exc:
                raise FinnResponsesError("responses_provider_error") from exc
            if getattr(response, "status", "completed") != "completed":
                raise FinnResponsesError("responses_incomplete")
            response_id = str(getattr(response, "id", "") or "")
            if not response_id:
                raise FinnResponsesError("responses_missing_id")
            calls = [item for item in (getattr(response, "output", None) or []) if getattr(item, "type", None) == "function_call"]
            if not calls:
                answer = str(getattr(response, "output_text", "") or "").strip()
                if not answer:
                    answer = "\n".join(
                        str(getattr(part, "text", "") or "")
                        for item in (getattr(response, "output", None) or [])
                        if getattr(item, "type", None) == "message"
                        for part in (getattr(item, "content", None) or [])
                        if getattr(part, "type", None) == "output_text"
                    ).strip()
                if not answer:
                    raise FinnResponsesError("responses_empty_answer")
                return FinnResponsesResult(answer, response_id, tuple(trace))
            tool_rounds += 1
            prior_id = response_id
            current_input = []
            conflicting_proposals = sum(
                self.catalog.is_proposal_tool(str(getattr(item, "name", "") or ""))
                for item in calls
            ) > 1
            for item in calls:
                call_id = str(getattr(item, "call_id", "") or "")
                tool_name = str(getattr(item, "name", "") or "")
                if not call_id:
                    raise FinnResponsesError("responses_missing_call_id")
                if call_id in seen_call_ids:
                    raise FinnResponsesError("responses_duplicate_call_id")
                seen_call_ids.add(call_id)
                if len(seen_call_ids) > self.max_tool_calls:
                    raise FinnResponsesError("responses_tool_call_limit")
                parsed_arguments: dict[str, Any] | None = None
                try:
                    tool_started = time.perf_counter()
                    arguments = json.loads(getattr(item, "arguments", "") or "")
                    if isinstance(arguments, dict):
                        parsed_arguments = arguments
                    if conflicting_proposals:
                        output = {
                            "status": "retry",
                            "reason": "multiple_action_proposals",
                            "instruction": (
                                "No proposal was created. Choose exactly one action proposal for "
                                "the user's current request. A separate new object is not a "
                                "revision of an older draft."
                            ),
                        }
                        call = None
                    else:
                        call = self.catalog.validate(tool_name, arguments)
                        remaining = remaining_lifecycle_seconds()
                        if remaining is not None and remaining <= 3.25:
                            raise FinnResponsesError("responses_lifecycle_budget_exhausted")
                        output = await asyncio.wait_for(
                            self.executor(call),
                            timeout=min(
                                max(self.tool_timeout_seconds, 8.0) if call.operation_id else self.tool_timeout_seconds,
                                remaining - 3.0 if remaining is not None else (
                                    max(self.tool_timeout_seconds, 8.0) if call.operation_id else self.tool_timeout_seconds
                                ),
                            ),
                        )
                    if not isinstance(output, dict):
                        raise FinnResponsesToolError("tool_output_not_typed_json")
                    if call is not None and output.get("status") != "retry":
                        repair_tool_name = None
                    if call is not None and (
                        (call.operation_id is not None and output.get("status") != "retry")
                        or (call.name == "ask_for_clarification" and output.get("status") == "needs_input")
                    ):
                        proposal_selected = True
                        repair_tool_name = None
                except TimeoutError:
                    output = {"status": "unavailable", "reason": "tool_timeout"}
                except (ValueError, TypeError, FinnResponsesToolError) as exc:
                    output = {"status": "unavailable", "reason": str(exc)}
                    if isinstance(exc, FinnResponsesToolError):
                        output.update(exc.details)
                        if (tool_name in {definition["name"] for definition in definitions}
                                and repair_attempts.get(tool_name, 0) < 1):
                            output["instruction"] = (
                                "Retry this same tool using only its declared argument names and types. "
                                "The previous call did not run; do not answer from its missing result."
                            )
                            repair_tool_name = tool_name
                            repair_attempts[tool_name] = 1
                        else:
                            repair_tool_name = None
                            repair_exhausted = True
                except FinnResponsesError:
                    raise
                except Exception:
                    output = {"status": "error", "reason": "tool_execution_failed"}
                trace.append({
                    "call_id": call_id,
                    "name": tool_name,
                    "arguments": parsed_arguments,
                    "status": output.get("status", "error"),
                    "result": output,
                    "provider_elapsed_ms": provider_elapsed_ms,
                    "tool_elapsed_ms": round((time.perf_counter() - tool_started) * 1000, 2),
                })
                if self.on_tool_result is not None:
                    checkpoint_started = time.perf_counter()
                    await self.on_tool_result(response_id, tuple(trace))
                    checkpoint_elapsed_ms = round((time.perf_counter() - checkpoint_started) * 1000, 2)
                    if checkpoint_elapsed_ms > 1000:
                        logger.warning(
                            "FINN Responses checkpoint slow tool=%s elapsed_ms=%s",
                            tool_name, checkpoint_elapsed_ms,
                        )
                current_input.append({
                    "type": "function_call_output",
                    "call_id": call_id,
                    "output": json.dumps(output, default=str),
                })
            setup_results = [
                result for call in trace
                for result in (call.get("result", {}).get("results") or [])
                if result.get("scope") == "read_active_setup"
            ]
            if (
                not proposal_selected
                and any(result.get("reason") == "setup_ambiguous" for result in setup_results)
                and not any(result.get("status") == "completed" for result in setup_results)
            ):
                return FinnResponsesResult("A setup choice is required.", response_id, tuple(trace))
        raise FinnResponsesError("responses_tool_round_limit")
