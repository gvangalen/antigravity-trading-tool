from pathlib import Path
import json

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


def test_selector_eval_registry_requires_missing_input_expectations(tmp_path):
    source = _paths()[0]
    missing = tmp_path / "finn_v2_selector_development.json"
    cases = json.loads(source.read_text(encoding="utf-8"))
    cases[0].pop("expected_missing_inputs")
    missing.write_text(json.dumps(cases), encoding="utf-8")

    with pytest.raises(ValueError):
        load_and_validate([missing, _paths()[1], _paths()[2]])


def test_selector_eval_registry_rejects_noncanonical_action_polarity(tmp_path):
    paths = _paths()
    regression = tmp_path / "finn_v2_selector_regression.json"
    cases = json.loads(paths[1].read_text(encoding="utf-8"))
    next(case for case in cases if case["eval_id"] == "reg-watch-add-1")["expected_action_polarity"] = "create"
    regression.write_text(json.dumps(cases), encoding="utf-8")

    with pytest.raises(ValueError, match="canonical_action_polarity_mismatch:reg-watch-add-1"):
        load_and_validate([paths[0], regression, paths[2]])
