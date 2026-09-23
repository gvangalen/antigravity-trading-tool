"""Bounded Responses function-calling loop; FINN remains the tool authority."""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

from backend.services.finn_v2_responses_tool_catalog import (
    FinnResponsesToolCall,
    FinnResponsesToolCatalog,
    FinnResponsesToolError,
)
from backend.services.finn_v2_lifecycle_budget import remaining_lifecycle_seconds


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
        guided_operation_id: str | None = None,
    ) -> FinnResponsesResult:
        current_input: list[dict[str, Any]] = [{"role": "user", "content": message}]
        prior_id = previous_response_id
        trace: list[dict[str, Any]] = []
        seen_call_ids: set[str] = set()
        proposal_selected = False
        tool_rounds = 0
        repair_tool_name: str | None = None
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
            kwargs: dict[str, Any] = {
                "model": self.model,
                "instructions": instructions,
                "input": current_input,
                "tools": self.catalog.definitions(
                    guided_operation_id=guided_operation_id if not trace else None,
                    retry_target_domain=retry_target_domain,
                ),
                "store": True,
                "max_output_tokens": 700 if not trace else 350,
            }
            if prior_id:
                kwargs["previous_response_id"] = prior_id
            if proposal_selected or (tool_rounds >= 2 and not repair_tool_name):
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
                provider_client = (
                    self.client.with_options(max_retries=0, timeout=provider_timeout)
                    if hasattr(self.client, "with_options") else self.client
                )
                response = await asyncio.wait_for(
                    provider_client.responses.create(**kwargs),
                    timeout=provider_timeout,
                )
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
                    arguments = json.loads(getattr(item, "arguments", "") or "")
                    if isinstance(arguments, dict):
                        parsed_arguments = arguments
                    call = self.catalog.validate(tool_name, arguments)
                    remaining = remaining_lifecycle_seconds()
                    if remaining is not None and remaining <= 3.25:
                        raise FinnResponsesError("responses_lifecycle_budget_exhausted")
                    output = await asyncio.wait_for(
                        self.executor(call),
                        timeout=min(
                            self.tool_timeout_seconds,
                            remaining - 3.0 if remaining is not None else self.tool_timeout_seconds,
                        ),
                    )
                    if not isinstance(output, dict):
                        raise FinnResponsesToolError("tool_output_not_typed_json")
                    if call.operation_id is not None and output.get("status") != "retry":
                        proposal_selected = True
                        repair_tool_name = None
                except TimeoutError:
                    output = {"status": "unavailable", "reason": "tool_timeout"}
                except (ValueError, TypeError, FinnResponsesToolError) as exc:
                    output = {"status": "unavailable", "reason": str(exc)}
                    if isinstance(exc, FinnResponsesToolError):
                        output.update(exc.details)
                        if self.catalog.is_proposal_tool(tool_name):
                            repair_tool_name = tool_name
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
                })
                if self.on_tool_result is not None:
                    await self.on_tool_result(response_id, tuple(trace))
                current_input.append({
                    "type": "function_call_output",
                    "call_id": call_id,
                    "output": json.dumps(output, default=str),
                })
        raise FinnResponsesError("responses_tool_round_limit")
