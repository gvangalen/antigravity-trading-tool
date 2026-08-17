"""Run the FINN V2 golden dataset eval suite."""

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
from backend.services.finn_v2_eval_runner_service import FinnV2EvalRunnerService


DEFAULT_DATASET = PROJECT_ROOT / "backend" / "tests" / "fixtures" / "finn_v2_golden_dataset.json"


async def _run(dataset: str, model_mode: str, persist_results: bool) -> dict:
    async with async_session_factory() as session:
        service = FinnV2EvalRunnerService(session)
        result = await service.run_dataset(
            dataset_path=dataset,
            model_mode=model_mode,
            persist_results=persist_results,
        )
        await session.commit()
        return result.dict()


def main() -> None:
    parser = argparse.ArgumentParser(description="Run FINN V2 golden evals.")
    parser.add_argument("--dataset", default=str(DEFAULT_DATASET), help="Path to the golden dataset JSON file.")
    parser.add_argument("--model-mode", choices=("mock", "real"), default="mock")
    parser.add_argument("--persist-results", action="store_true", help="Persist eval records in the FINN V2 tables.")
    args = parser.parse_args()
    result = asyncio.run(_run(args.dataset, args.model_mode, args.persist_results))
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
