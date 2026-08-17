from __future__ import annotations

from typing import Any, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from backend.schemas.finn_v2_schema import AgentRunRequest
from backend.services.finn_v2_delivery_service import FinnV2DeliveryService
from backend.services.finn_v2_gateway_service import FinnV2GatewayService


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
        envelope = await self.delivery.get_delivery_envelope(user_id=user_id, run_id=run_id)
        if envelope.response is None:
            raise ValueError("v2_delivery_failure")
        return self._assistant_contract(envelope.response, trace_id=trace_id, run_id=run_id)

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

    def _assistant_contract(self, response, *, trace_id: str, run_id: str) -> dict[str, Any]:
        lines = [response.direct_answer, response.main_observation]
        lines.extend([f"- {point.title}: {point.explanation}" for point in response.supporting_points])
        if response.uncertainty_summary:
            lines.append(response.uncertainty_summary)
        if response.next_step:
            lines.append(response.next_step.instruction)
        payload = {
            "response": "\n\n".join([line for line in lines if line]),
            "intent": response.mode.lower(),
            "action": None,
            "draft": None,
            "state": {"current_flow": "finn_v2_visible", "run_id": run_id, "surface": "assistant"},
            "reasoning": None,
            "trace_id": trace_id,
            "suggested_actions": [response.next_step.title] if response.next_step else [],
            "summary": response.main_observation,
            "risk_summary": response.uncertainty_summary,
            "next_best_action": response.next_step.title if response.next_step else response.follow_up_question,
            "review_reason": None,
            "response_trace": {
                "trace_id": trace_id,
                "run_id": run_id,
                "response_source": "finn_v2_verified",
                "verifier_status": response.verifier_status,
                "mode": response.mode,
            },
            "can_confirm": bool(response.confirmation_required and response.proposal_id),
            "actions": [],
        }
        if response.proposal_id:
            payload["actions"] = [{
                "type": "v2_proposal",
                "proposal_id": response.proposal_id,
                "requires_confirmation": response.confirmation_required,
                "mode": response.mode,
            }]
        return payload

