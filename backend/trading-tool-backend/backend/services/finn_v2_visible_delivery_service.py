from __future__ import annotations

import logging
from typing import Any, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from backend.domain.finn_v2_contract import is_terminal_status
from backend.schemas.finn_v2_schema import AgentRunRequest
from backend.services.finn_v2_delivery_service import FinnV2DeliveryService
from backend.services.finn_v2_gateway_service import FinnV2GatewayService


logger = logging.getLogger(__name__)


class FinnV2VisibleDeliveryError(RuntimeError):
    def __init__(self, code: str, *, run_id: str | None, failure_stage: str):
        self.code = code
        self.run_id = run_id
        self.failure_stage = failure_stage
        super().__init__(code)


class FinnV2VisibleDeliveryService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.gateway = FinnV2GatewayService(session)
        self.delivery = FinnV2DeliveryService(session)

    async def deliver_assistant_envelope(
        self,
        *,
        user_id: int,
        message: str,
        context_payload: Optional[dict],
        transport: str,
        request_path: str,
        request_id: str,
        trace_id: str,
    ) -> dict[str, Any]:
        run_id = await self.gateway.run_foundation_now(
            user_id=user_id,
            request_payload=AgentRunRequest(
                message=message,
                workspace_hints=context_payload or {},
                client_context={"surface": "assistant_visible_v2", **(context_payload or {})},
                transport=transport,
            ).dict(),
            request_path=request_path,
            request_id=request_id,
            trace_id=trace_id,
        )
        try:
            artifacts = await self.delivery.get_delivery_artifacts(user_id=user_id, run_id=run_id)
            envelope = artifacts["delivery_envelope"]
            verified_response = artifacts.get("verified_response")
            if verified_response is None:
                status = str(envelope.get("status") or "")
                if status and not is_terminal_status(status):
                    return self._pending_contract(
                        trace_id=trace_id,
                        run_id=run_id,
                        status=status,
                    )
                logger.error(
                    "FINN V2 visible delivery missing verified response",
                    extra={
                        "trace_id": trace_id,
                        "request_id": request_id,
                        "user_id": user_id,
                        "run_id": run_id,
                        "run_status": envelope.get("status"),
                        "failure_stage": "delivery_envelope",
                        "service": "FinnV2VisibleDeliveryService",
                        "method": "deliver_assistant_envelope",
                        "error_code": envelope.get("error_code"),
                    },
                )
                return self._failed_contract(
                    trace_id=trace_id,
                    run_id=run_id,
                    status=str(envelope.get("status") or "failed"),
                    error_code=envelope.get("error_code"),
                )
            return self._assistant_contract(
                verified_response,
                trace_id=trace_id,
                run_id=run_id,
                artifacts=artifacts,
            )
        except FinnV2VisibleDeliveryError:
            raise
        except Exception as exc:
            logger.exception(
                "FINN V2 visible delivery failed",
                extra={
                    "trace_id": trace_id,
                    "request_id": request_id,
                    "user_id": user_id,
                    "run_id": run_id,
                    "failure_stage": "delivery_artifacts",
                    "service": "FinnV2VisibleDeliveryService",
                    "method": "deliver_assistant_envelope",
                    "exception_class": exc.__class__.__name__,
                },
            )
            raise FinnV2VisibleDeliveryError(
                "v2_delivery_failure",
                run_id=run_id,
                failure_stage="delivery_artifacts",
            ) from exc

    async def deliver_mission_control(
        self,
        *,
        user_id: int,
        context_payload: Optional[dict],
        request_id: str,
        trace_id: str,
    ) -> dict[str, Any]:
        envelope = await self.deliver_assistant_envelope(
            user_id=user_id,
            message="Today with FINN",
            context_payload={"surface": "today_with_finn", **(context_payload or {})},
            transport="chat",
            request_path="/api/assistant/mission-control",
            request_id=request_id,
            trace_id=trace_id,
        )
        return {
            "greeting": "Today with FINN",
            "finn_briefing": {
                "greeting": "Today with FINN",
                "summary": envelope.get("summary") or envelope.get("response"),
                "suggested_actions": [envelope.get("next_best_action")] if envelope.get("next_best_action") else [],
            },
            "generation_status": "completed",
            "response_trace": envelope.get("response_trace"),
        }

    def _assistant_contract(self, response: dict[str, Any], *, trace_id: str, run_id: str, artifacts: dict[str, Any]) -> dict[str, Any]:
        lines = [response.get("direct_answer"), response.get("main_observation")]
        lines.extend(
            [
                f"- {point.get('title')}: {point.get('explanation')}"
                for point in (response.get("supporting_points") or [])
                if point.get("title") and point.get("explanation")
            ]
        )
        if response.get("uncertainty_summary"):
            lines.append(response["uncertainty_summary"])
        next_step = response.get("next_step") or {}
        if next_step.get("instruction"):
            lines.append(next_step["instruction"])
        response_trace = {
            "trace_id": trace_id,
            "run_id": run_id,
            "pipeline_version": "finn_v2",
            "router_name": "finn_v2_orchestrator",
            "selected_handler": "FinnV2VisibleDeliveryService.deliver_assistant_envelope",
            "response_source": "finn_v2_verified",
            "verifier_status": response.get("verifier_status"),
            "mode": response.get("mode"),
            "orchestrator_result": artifacts.get("orchestrator_result"),
            "policy_result": artifacts.get("policy_result"),
            "reasoning_result": artifacts.get("reasoning_result"),
            "verifier_result": artifacts.get("verifier_result"),
            "tool_calls": artifacts.get("tool_calls") or [],
            "validation_result": artifacts.get("validation_result"),
            "financial_state_snapshot": artifacts.get("financial_state_snapshot"),
            "verified_response": artifacts.get("verified_response"),
            "delivery_envelope": artifacts.get("delivery_envelope"),
        }
        payload = {
            "response": "\n\n".join([line for line in lines if line]),
            "intent": str(response.get("mode") or "UNAVAILABLE").lower(),
            "action": None,
            "draft": None,
            "state": {"current_flow": "finn_v2_visible", "run_id": run_id, "surface": "assistant"},
            "reasoning": None,
            "trace_id": trace_id,
            "suggested_actions": [next_step.get("title")] if next_step.get("title") else [],
            "summary": response.get("main_observation"),
            "risk_summary": response.get("uncertainty_summary"),
            "next_best_action": next_step.get("title") or response.get("follow_up_question"),
            "review_reason": None,
            "response_trace": response_trace,
            "verified_response": artifacts.get("verified_response"),
            "delivery_envelope": artifacts.get("delivery_envelope"),
            "tool_calls": artifacts.get("tool_calls") or [],
            "financial_state_snapshot": artifacts.get("financial_state_snapshot"),
            "validation_result": artifacts.get("validation_result"),
            "orchestrator_result": artifacts.get("orchestrator_result"),
            "policy_result": artifacts.get("policy_result"),
            "reasoning_result": artifacts.get("reasoning_result"),
            "verifier_result": artifacts.get("verifier_result"),
            "can_confirm": bool(response.get("confirmation_required") and response.get("proposal_id")),
            "actions": [],
        }
        if response.get("proposal_id"):
            payload["actions"] = [{
                "type": "v2_proposal",
                "proposal_id": response["proposal_id"],
                "requires_confirmation": bool(response.get("confirmation_required")),
                "mode": response.get("mode"),
            }]
        return payload

    def _pending_contract(self, *, trace_id: str, run_id: str, status: str) -> dict[str, Any]:
        return {
            "response": "Ik verwerk je FINN-verzoek nog. Je run blijft actief en komt via dezelfde run-ID beschikbaar zodra de verified response klaar is.",
            "intent": "processing",
            "action": None,
            "draft": None,
            "state": {
                "current_flow": "finn_v2_visible_pending",
                "run_id": run_id,
                "surface": "assistant",
                "run_status": status,
            },
            "reasoning": None,
            "trace_id": trace_id,
            "suggested_actions": [],
            "summary": "FINN verwerkt je verzoek nog.",
            "risk_summary": None,
            "next_best_action": "Wacht kort terwijl FINN deze run afrondt.",
            "review_reason": None,
            "response_trace": {
                "trace_id": trace_id,
                "run_id": run_id,
                "response_source": "finn_v2_pending",
                "delivery_status": status,
            },
            "can_confirm": False,
            "actions": [],
        }

    def _failed_contract(self, *, trace_id: str, run_id: str, status: str, error_code: Optional[str]) -> dict[str, Any]:
        return {
            "response": "Ik kan deze FINN V2-run nu niet veilig afronden. Probeer het opnieuw of controleer de runstatus met dezelfde run-ID.",
            "intent": "unavailable",
            "action": None,
            "draft": None,
            "state": {
                "current_flow": "finn_v2_visible_terminal_failed",
                "run_id": run_id,
                "surface": "assistant",
                "run_status": status,
            },
            "reasoning": None,
            "trace_id": trace_id,
            "suggested_actions": [],
            "summary": "De FINN V2-run eindigde zonder veilige verified response.",
            "risk_summary": error_code,
            "next_best_action": None,
            "review_reason": None,
            "response_trace": {
                "trace_id": trace_id,
                "run_id": run_id,
                "response_source": "finn_v2_terminal_failure",
                "delivery_status": status,
                "error": error_code or "v2_terminal_failure",
            },
            "can_confirm": False,
            "actions": [],
        }
