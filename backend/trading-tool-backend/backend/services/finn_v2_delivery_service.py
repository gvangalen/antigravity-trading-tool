from __future__ import annotations

from typing import AsyncIterator, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from backend.infrastructure.repositories.finn_v2_run_repository import FinnV2RunRepository
from backend.infrastructure.repositories.finn_v2_verified_response_repository import FinnV2VerifiedResponseRepository
from backend.schemas.finn_v2_delivery_schema import FinnV2DeliveryEnvelope, FinnV2StreamEvent
from backend.schemas.finn_v2_response_schema import VerifiedResponse


class FinnV2DeliveryService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.runs = FinnV2RunRepository(session)
        self.verified = FinnV2VerifiedResponseRepository(session)

    async def get_delivery_envelope(self, *, user_id: int, run_id: str) -> FinnV2DeliveryEnvelope:
        run = await self.runs.get_by_id_for_user(run_id=run_id, user_id=user_id)
        if run is None:
            raise LookupError("FINN V2 run not found")
        row = await self.verified.get_latest_for_run(run_id=run_id, user_id=user_id)
        response = VerifiedResponse.parse_obj(row.response_json) if row is not None else None
        status = "completed" if response is not None else ("canceled" if run.status == "canceled" else "failed")
        return FinnV2DeliveryEnvelope(
            run_id=run.id,
            conversation_id=run.conversation_id,
            status=status,
            response=response,
            proposal_id=response.proposal_id if response is not None else None,
            confirmation_required=bool(response.confirmation_required) if response is not None else False,
        )

    async def stream_delivery_events(self, *, user_id: int, run_id: str) -> AsyncIterator[FinnV2StreamEvent]:
        envelope = await self.get_delivery_envelope(user_id=user_id, run_id=run_id)
        if envelope.response is not None:
            yield FinnV2StreamEvent(
                event="run.completed",
                run_id=run_id,
                payload={"response": envelope.response.dict(), "delivery_source": envelope.delivery_source},
            )
            return
        yield FinnV2StreamEvent(
            event="run.failed",
            run_id=run_id,
            payload={"delivery_source": envelope.delivery_source, "status": envelope.status},
        )
