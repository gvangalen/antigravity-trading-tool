import json
from pathlib import Path

from backend.schemas.finn_v2_eval_schema import GoldenCase


FIXTURES = Path(__file__).resolve().parent / "fixtures"


def test_golden_dataset_parses_and_contains_required_cases():
    dataset = json.loads((FIXTURES / "finn_v2_golden_dataset.json").read_text(encoding="utf-8"))
    cases = [GoldenCase.parse_obj(item) for item in dataset]

    assert len(cases) >= 11
    assert {"A1", "A3", "B1", "B4", "P1", "E1_SETUP_CREATE", "E2_WATCHLIST_ADD", "E3_SETUP_RESOLUTION_BTC", "E4_GRAPH_BTC", "E4_GRAPH_AAPL", "E5_PLAN_EVAL"}.issubset({case.case_id for case in cases})


def test_eval_account_fixture_is_account_scoped():
    accounts = json.loads((FIXTURES / "finn_v2_eval_accounts.json").read_text(encoding="utf-8"))

    assert accounts["user_a"]["primary_asset"] == "BTC"
    assert accounts["user_b"]["primary_asset"] == "AAPL"
    assert accounts["user_388"]["setup_id"] == 293
    assert accounts["user_389"]["bot_id"] == 171
    assert accounts["user_a"]["user_id"] != accounts["user_b"]["user_id"]
