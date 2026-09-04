"""Run one persisted FINN V2 lifecycle gate against an isolated test user.

This intentionally uses the public gateway and worker dispatch boundary.  It
must be run only in an isolated candidate environment with a designated test
user; it never accepts a production-user default.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import time

from backend.infrastructure.database import async_session_factory
from backend.infrastructure.repositories.finn_v2_runtime_contract_repository import FinnV2RuntimeContractRepository
from backend.schemas.finn_v2_schema import AgentRunRequest
from backend.services.finn_v2_delivery_service import FinnV2DeliveryService
from backend.services.finn_v2_gateway_service import FinnV2GatewayService
from backend.services.finn_v2_run_service import FinnV2RunService


async def run_gate(*, user_id: int, message: str, timeout_seconds: float) -> dict:
    if user_id <= 0:
        raise ValueError("runtime_gate_requires_explicit_test_user")
    async with async_session_factory() as session:
        gateway = FinnV2GatewayService(session)
        run_id = await gateway.run_foundation_now(
            user_id=user_id,
            request_payload=AgentRunRequest(message=message, transport="chat").dict(),
            request_path="/internal/finn-v2-runtime-gate",
            request_id=f"runtime-gate-{time.time_ns()}",
            trace_id=f"runtime-gate-{time.time_ns()}",
        )

    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        async with async_session_factory() as session:
            run_service = FinnV2RunService(session)
            run = await run_service.runs.get_by_id_for_user(run_id=run_id, user_id=user_id)
            if run is not None and run.status in {"completed", "clarification_required", "unavailable", "downgraded", "rejected", "failed", "canceled"}:
                contract = await FinnV2RuntimeContractRepository(session).get_for_run(run_id=run_id)
                if contract is None or not contract.terminal_projection_json:
                    raise AssertionError("runtime_gate_missing_terminal_contract_projection")
                projection = dict(contract.terminal_projection_json)
                polling = await run_service.envelope_from_run(run)
                delivery = FinnV2DeliveryService(session)
                sse = [event async for event in delivery.stream_delivery_events(user_id=user_id, run_id=run_id)]
                if polling.runtime_trace != projection:
                    raise AssertionError("runtime_gate_polling_projection_mismatch")
                if not sse:
                    raise AssertionError("runtime_gate_missing_sse_event")
                return {
                    "run_id": run_id,
                    "contract_id": contract.contract_id,
                    "status": run.status,
                    "initial_operation_id": projection.get("initial_operation_id"),
                    "final_operation_id": projection.get("final_operation_id"),
                    "canonical_target": projection.get("canonical_target"),
                    "polling_sse_contract_projection": True,
                }
        await asyncio.sleep(0.25)
    raise TimeoutError("runtime_gate_timeout")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--test-user-id", type=int, required=True)
    parser.add_argument("--message", required=True)
    parser.add_argument("--timeout-seconds", type=float, default=15.0)
    args = parser.parse_args()
    print(json.dumps(asyncio.run(run_gate(user_id=args.test_user_id, message=args.message, timeout_seconds=args.timeout_seconds)), sort_keys=True))


if __name__ == "__main__":
    main()
