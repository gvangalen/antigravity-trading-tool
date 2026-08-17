"""Evaluate FINN V2 release gates from the latest or a specific eval run."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.infrastructure.database import async_session_factory
from backend.infrastructure.repositories.finn_v2_eval_repository import FinnV2EvalRepository
from backend.services.finn_v2_release_gate_service import FinnV2ReleaseGateService


async def _run(eval_run_id: str | None) -> dict:
    async with async_session_factory() as session:
        repo = FinnV2EvalRepository(session)
        eval_run = await repo.latest_run()
        if eval_run is None:
            raise RuntimeError("No FINN V2 eval run found.")
        if eval_run_id and eval_run.id != eval_run_id:
            raise RuntimeError(f"Requested eval run {eval_run_id} is not the latest persisted run in this environment.")
        result = await FinnV2ReleaseGateService(session).evaluate(eval_run=eval_run)
        await session.commit()
        return result.dict()


def main() -> None:
    parser = argparse.ArgumentParser(description="Run FINN V2 release gates.")
    parser.add_argument("--eval-run-id", default=None, help="Optional eval run id. The latest persisted run is used by default.")
    args = parser.parse_args()
    result = asyncio.run(_run(args.eval_run_id))
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
