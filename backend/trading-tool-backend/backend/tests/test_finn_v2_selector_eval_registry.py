from pathlib import Path

import pytest

from backend.services.finn_v2_selector_eval_registry import load_and_validate


FIXTURES = Path(__file__).parent / "fixtures"


def _paths():
    return [FIXTURES / f"finn_v2_selector_{name}.json" for name in ("development", "regression", "holdout")]


def test_selector_eval_registry_covers_each_dataset_without_leakage():
    cases = load_and_validate(_paths())

    assert len(cases) >= 52
    assert {case.dataset for case in cases} == {"development", "regression", "holdout"}
    assert all(case.provider_call_expected for case in cases)


def test_selector_eval_registry_rejects_duplicate_cross_dataset_queries(tmp_path):
    paths = _paths()
    duplicate = tmp_path / "finn_v2_selector_holdout.json"
    duplicate.write_text(paths[-1].read_text(encoding="utf-8"), encoding="utf-8")
    data = duplicate.read_text(encoding="utf-8").replace(
        "Waar dient MACD voor bij technische analyse?", "Wat betekent RSI?"
    )
    duplicate.write_text(data, encoding="utf-8")

    with pytest.raises(ValueError, match="duplicate_query"):
        load_and_validate([paths[0], paths[1], duplicate])
