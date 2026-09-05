#!/usr/bin/env python3
"""Run one safe, authenticated FINN V2 capability smoke through production.

The public transport gate verifies API creation, polling and SSE. This wrapper
adds read-only persistence assertions on the server so a release cannot pass
on health markers alone while run creation or dispatch durability is broken.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
from typing import Any, Dict

from sqlalchemy import select

from backend.infrastructure.database import async_session_factory
from backend.infrastructure.models import FinnV2RunDispatch, FinnV2RuntimeContract
from backend.scripts.run_finn_v2_persisted_runtime_gate import run_gate


DEFAULT_CAPABILITY_MESSAGE = "Wat kun je voor mij doen?"


async def _load_persisted_records(*, run_id: str) -> Dict[str, Any]:
    async with async_session_factory() as session:
        contract = (
            await session.execute(
                select(FinnV2RuntimeContract).where(FinnV2RuntimeContract.run_id == run_id)
            )
        ).scalars().first()
        dispatches = list(
            (await session.execute(
                select(FinnV2RunDispatch).where(FinnV2RunDispatch.run_id == run_id)
            )).scalars().all()
        )
    return {"contract": contract, "dispatches": dispatches}


def _assert_persisted_smoke(*, run_result: Dict[str, Any], persisted: Dict[str, Any]) -> Dict[str, Any]:
    contract = persisted.get("contract")
    dispatches = list(persisted.get("dispatches") or [])
    run_id = run_result["run_id"]

    if contract is None or contract.run_id != run_id:
        raise AssertionError("authenticated_smoke_runtime_contract_missing")
    projection = dict(contract.terminal_projection_json or {})
    if not projection or projection.get("run_id") != run_id:
        raise AssertionError("authenticated_smoke_typed_terminal_projection_missing")
    if not projection.get("terminal_status") or not projection.get("terminal_response_type"):
        raise AssertionError("authenticated_smoke_terminal_projection_untyped")
    if len(dispatches) != 1:
        raise AssertionError(f"authenticated_smoke_dispatch_count_{len(dispatches)}")
    dispatch = dispatches[0]
    if int(dispatch.attempt_count or 0) > 1:
        raise AssertionError("authenticated_smoke_dispatch_attempt_count_exceeded")

    return {
        **run_result,
        "persistence_verified": True,
        "terminal_projection_typed": True,
        "dispatch_id": dispatch.dispatch_id,
        "dispatch_count": 1,
        "dispatch_attempt_count": int(dispatch.attempt_count or 0),
    }


def run_authenticated_smoke(*, base_url: str, bearer_token: str, timeout_seconds: float) -> Dict[str, Any]:
    run_result = run_gate(
        base_url=base_url,
        bearer_token=bearer_token,
        message=DEFAULT_CAPABILITY_MESSAGE,
        timeout_seconds=timeout_seconds,
    )
    persisted = asyncio.run(_load_persisted_records(run_id=run_result["run_id"]))
    return _assert_persisted_smoke(run_result=run_result, persisted=persisted)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--token-env", default="FINN_QA_BEARER_TOKEN")
    parser.add_argument("--timeout-seconds", type=float, default=30.0)
    args = parser.parse_args()
    token = os.environ.get(args.token_env, "")
    if not token.strip():
        raise ValueError("authenticated_smoke_requires_explicit_qa_bearer_token")
    print(json.dumps(run_authenticated_smoke(
        base_url=args.base_url,
        bearer_token=token,
        timeout_seconds=args.timeout_seconds,
    ), sort_keys=True))


if __name__ == "__main__":
    main()
