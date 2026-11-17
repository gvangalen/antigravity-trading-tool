"""Safety and contract checks for the bounded coach-feed production probe."""

import pytest

from backend.scripts import probe_protected_coach_feed as probe
from backend.scripts import run_finn_production_qa as runner


def test_coach_probe_requires_both_fixture_flags(monkeypatch):
    namespace = "qa-44006750736-1-12345678-abcdef12"
    monkeypatch.setenv("FINN_QA_USER_ID", "123")
    monkeypatch.setenv("FINN_QA_ALLOW_COACH_FEED_FIXTURE", "1")
    monkeypatch.setenv("FINN_QA_ALLOW_FIXTURE_ACTIONS", "1")
    monkeypatch.setenv("FINN_QA_ALLOW_FIXTURE_EXECUTION", "0")
    with pytest.raises(RuntimeError, match="coach_feed_fixture_not_authorized"):
        probe._require_run(namespace)
    monkeypatch.setenv("FINN_QA_ALLOW_FIXTURE_EXECUTION", "1")
    assert probe._require_run(namespace) == 123


def test_coach_probe_rejects_unscoped_namespace(monkeypatch):
    monkeypatch.setenv("FINN_QA_USER_ID", "123")
    monkeypatch.setenv("FINN_QA_ALLOW_COACH_FEED_FIXTURE", "1")
    monkeypatch.setenv("FINN_QA_ALLOW_FIXTURE_ACTIONS", "1")
    monkeypatch.setenv("FINN_QA_ALLOW_FIXTURE_EXECUTION", "1")
    with pytest.raises(RuntimeError, match="coach_feed_fixture_not_authorized"):
        probe._require_run("public-user")


def test_coach_probe_is_allowlisted_and_sanitizes_errors():
    assert "coach_feed_triggers" in runner.ALLOWED_PROFILES
    assert runner.profile_error_category(
        "coach_feed_triggers", RuntimeError("private database value")
    ) == "coach_feed_runtime_failed"
    assert runner.profile_error_category(
        "coach_feed_triggers", RuntimeError("coach_feed_risk_card_missing")
    ) == "coach_feed_risk_card_missing"


def test_coach_probe_runs_both_cases_without_leaking_exception(monkeypatch):
    monkeypatch.setattr(probe, "_require_run", lambda namespace: 123)
    monkeypatch.setattr(probe, "_score_case", lambda namespace, bound: (_ for _ in ()).throw(
        RuntimeError("private database value")
    ))
    monkeypatch.setattr(probe, "_risk_case", lambda namespace, bound: {
        "position_risk": "passed", "paper_only": True,
    })
    result = probe.run("qa-44006750736-1-12345678-abcdef12")
    assert result == {
        "score_and_plan": {"result": "FAIL", "reason": "coach_feed_runtime_failed"},
        "paper_risk": {"position_risk": "passed", "paper_only": True},
        "live_calls": 0,
        "result": "FAIL",
    }


def test_coach_probe_reports_missing_quote_as_inconclusive(monkeypatch):
    monkeypatch.setattr(probe, "_require_run", lambda namespace: 123)
    monkeypatch.setattr(probe, "_score_case", lambda namespace, bound: (_ for _ in ()).throw(
        RuntimeError("coach_feed_source_unavailable")
    ))
    monkeypatch.setattr(probe, "_risk_case", lambda namespace, bound: {
        "position_risk": "passed", "paper_only": True,
    })
    result = probe.run("qa-44006750736-1-12345678-abcdef12")
    assert result["result"] == "INCONCLUSIVE"
    assert result["score_and_plan"] == {
        "result": "FAIL", "reason": "coach_feed_source_unavailable",
    }


def test_plan_review_requires_a_verified_benchmark_not_only_a_moving_quote():
    valid = {"status": "measured_move", "symbol": "ETH",
             "source_status": "available", "plan_status": "matches",
             "quote_source_observed_at": "2026-11-17T12:00:00Z"}
    assert probe._verified_plan_evidence(valid)
    assert not probe._verified_plan_evidence({**valid, "source_status": "invalid_weights"})
    assert not probe._verified_plan_evidence({**valid, "plan_status": "insufficient_data"})
