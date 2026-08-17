import asyncio
from pathlib import Path

from backend.services.finn_v2_eval_runner_service import FinnV2EvalRunnerService


def test_eval_runner_returns_aggregate_scores_for_mock_dataset(monkeypatch):
    dataset_path = Path(__file__).resolve().parent / "fixtures" / "finn_v2_golden_a1_b4.json"
    monkeypatch.setattr("backend.services.finn_v2_eval_runner_service.get_ai_availability", lambda: {"available": False})

    result = asyncio.run(
        FinnV2EvalRunnerService(session=object()).run_dataset(
            dataset_path=str(dataset_path),
            model_mode="mock",
            persist_results=False,
        )
    )

    assert result.total_cases == 2
    assert result.failed_cases == 0
    assert result.aggregate_scores["verified_response_rate"] == 100.0
    assert result.model_names == ["mock"]
