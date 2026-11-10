from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
import pytest

from backend.scripts import probe_protected_aapl_quote_coach as probe
from backend.scripts.run_finn_production_qa import ALLOWED_PROFILES, profile_error_category


def test_old_quote_is_rejected_only_when_mislabeled_current():
    assert probe._old_claimed_current("De actuele AAPL-koerssnapshot is USD 351,19.")
    assert not probe._old_claimed_current("Het historische rapport noemde USD 351,19 om 19:03 UTC.")
    assert not probe._old_claimed_current("USD 351,19 is niet actueel; het is de oude rapportkoers.")
    assert probe._old_claimed_current("De oude rapportkoers USD 351,19 is ook de actuele koerssnapshot.")


def test_market_and_owner_evidence_bind_both_distinct_moments():
    source = {"price": Decimal("350.49"),
              "at": datetime(2026, 11, 9, 20, 59, tzinfo=timezone.utc)}
    rows = [
        {"scope": "read_market_snapshot", "status": "completed", "data": {
            "symbol": "AAPL", "price": 350.49, "quote_currency": "USD",
            "as_of": "2026-11-09T20:59:00+00:00"}},
        {"scope": "read_latest_report", "status": "completed", "data": {
            "score_source_snapshot": {"assets": [{"symbol": "AAPL", "market_snapshot": {
                "price": 351.19, "quote_currency": "USD",
                "as_of": "2026-11-09T19:03:00+00:00"}}]}}},
        {"scope": "read_bot_status", "status": "completed", "data": {
            "is_live": False, "latest_decision": {"reason_code": "market_price_stale"}}},
    ]
    assert probe._market_evidence(rows, source)["source_match"] is True
    assert probe._owner_evidence(rows) == {
        "old_report_match": True, "paper_bot_stale_reason": True,
    }
    rows[0]["data"]["as_of"] = "2026-11-09T19:03:00+00:00"
    assert probe._market_evidence(rows, source)["source_match"] is False
    rows[1]["data"]["score_source_snapshot"]["assets"][0]["market_snapshot"]["price"] = 350.49
    assert probe._owner_evidence(rows)["old_report_match"] is False


def test_plan_and_score_reads_must_be_aapl_and_materialized():
    rows = [{"scope": scope, "status": "completed", "data": {
        "symbol": "AAPL", **({"reported_scores": {"macro_score": 20}} if scope == "read_asset_scores" else {})}}
        for scope in ("read_active_setup", "read_linked_strategy", "read_asset_scores")]
    assert probe._plan_score_evidence(rows)
    rows[-1]["data"]["reported_scores"] = {"macro_score": None}
    assert not probe._plan_score_evidence(rows)
    rows[-1]["data"]["reported_scores"] = {"macro_score": 20}
    rows[0]["data"]["symbol"] = "ETH"
    assert not probe._plan_score_evidence(rows)


def test_answer_checks_require_current_price_and_distinct_source_moments():
    moment = datetime(2026, 11, 9, 20, 59, tzinfo=timezone.utc)
    answer = "Actuele AAPL-bron: USD 350,49 om 20:59 UTC. Oud rapport: USD 351,19 om 19:03 UTC."
    assert probe._answer_current_price(answer, Decimal("350.48999"))
    assert all(probe._answer_moments(answer, moment).values())
    assert not probe._old_claimed_current(answer)
    assert not probe._answer_current_price("USD 351,19 was de actuele koers.", Decimal("350.48999"))
    assert not all(probe._answer_moments("USD 350,49", moment).values())


def test_profile_is_protected_and_errors_are_allowlisted():
    assert "aapl_paper_quote_coach" in ALLOWED_PROFILES
    assert profile_error_category("aapl_paper_quote_coach", RuntimeError("aapl_source_unavailable")) == "aapl_source_unavailable"
    assert profile_error_category("aapl_paper_quote_coach", RuntimeError("secret owner=17")) == "aapl_probe_runtime_error"
    root = Path(__file__).resolve().parents[4]
    workflow = (root / ".github/workflows/finn-production-qa.yml").read_text()
    dispatcher = (root / "ops/qa/run_finn_production_qa.sh").read_text()
    assert "aapl_paper_quote_coach" in workflow and "aapl_paper_quote_coach" in dispatcher
    assert 'FINN_QA_ALLOW_AAPL_QUOTE_FIXTURE=0' in workflow
    assert 'FINN_QA_ALLOW_AAPL_QUOTE_FIXTURE=1' in workflow


def test_probe_rejects_unprotected_invocation(monkeypatch):
    monkeypatch.delenv("FINN_QA_ALLOW_AAPL_QUOTE_FIXTURE", raising=False)
    with pytest.raises(RuntimeError, match="aapl_fixture_not_authorized"):
        probe.run("qa-123456-1-abcdef12-abcdef12")
