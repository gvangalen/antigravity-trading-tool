"""Safety and contract checks for the bounded coach-feed production probe."""

import asyncio
from types import SimpleNamespace

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
    monkeypatch.setattr(probe, "_score_case", lambda namespace, bound, *, trace, run_async: (_ for _ in ()).throw(
        RuntimeError("private database value")
    ))
    monkeypatch.setattr(probe, "_risk_case", lambda namespace, bound, *, trace, run_async: {
        "position_risk": "passed", "paper_only": True,
    })
    result = probe.run("qa-44006750736-1-12345678-abcdef12")
    assert result == {
        "score_and_plan": {"result": "FAIL", "reason": "coach_feed_runtime_failed",
                           "failure_stage": "preflight", "fixture_state": "not_created"},
        "paper_risk": {"position_risk": "passed", "paper_only": True,
                       "fixture_state": "not_created"},
        "paper_execution_attempts": 0,
        "live_calls": 0,
        "result": "FAIL",
    }


def test_coach_probe_reports_missing_quote_as_inconclusive(monkeypatch):
    monkeypatch.setattr(probe, "_require_run", lambda namespace: 123)
    monkeypatch.setattr(probe, "_score_case", lambda namespace, bound, *, trace, run_async: (_ for _ in ()).throw(
        RuntimeError("coach_feed_source_unavailable")
    ))
    monkeypatch.setattr(probe, "_risk_case", lambda namespace, bound, *, trace, run_async: {
        "position_risk": "passed", "paper_only": True,
    })
    result = probe.run("qa-44006750736-1-12345678-abcdef12")
    assert result["result"] == "INCONCLUSIVE"
    assert result["score_and_plan"] == {
        "result": "FAIL", "reason": "coach_feed_source_unavailable",
        "failure_stage": "preflight", "fixture_state": "not_created",
    }


def test_score_probe_reports_stage_and_quarantine_without_private_error(monkeypatch):
    async def source():
        return 1.5, 1.5, object()

    quarantined = []
    monkeypatch.setattr(probe, "_require_run", lambda namespace: 123)
    monkeypatch.setattr(probe, "_fresh_eth_move", source)
    monkeypatch.setattr(probe.score, "_seed", lambda *args, **kwargs: (456, 789, "date"))
    monkeypatch.setattr(probe, "_align_child_market_reading", lambda *args, **kwargs: (
        _ for _ in ()).throw(RuntimeError("private database value")))
    monkeypatch.setattr(probe.score, "_quarantine", lambda *args: quarantined.append(True))
    monkeypatch.setattr(probe, "_risk_case", lambda namespace, bound, *, trace, run_async: {})

    result = probe.run("qa-44006750736-1-12345678-abcdef12")
    assert quarantined == [True]
    assert result["score_and_plan"] == {
        "result": "FAIL", "reason": "coach_feed_runtime_failed",
        "failure_stage": "source_alignment", "fixture_state": "quarantined",
    }
    assert "private" not in str(result)


def test_risk_probe_counts_execution_attempt_and_quarantine(monkeypatch):
    finished = []
    monkeypatch.setattr(probe, "_require_run", lambda namespace: 123)
    monkeypatch.setattr(probe, "_score_case", lambda namespace, bound, *, trace, run_async: {})
    monkeypatch.setattr(probe.paper, "_verified_source_price_eur", lambda: {"eur_price": 10})
    monkeypatch.setattr(probe.paper, "_seed", lambda *args: (456, 789, 101))
    monkeypatch.setattr(probe.paper, "_execute_and_replay", lambda *args: (
        _ for _ in ()).throw(RuntimeError("private database value")))
    monkeypatch.setattr(probe.paper, "_finish", lambda *args, **kwargs: finished.append(kwargs["passed"]))

    result = probe.run("qa-44006750736-1-12345678-abcdef12")
    assert finished == [False]
    assert result["paper_execution_attempts"] == 1
    assert result["paper_risk"] == {
        "result": "FAIL", "reason": "coach_feed_runtime_failed",
        "failure_stage": "paper_execution", "fixture_state": "quarantined",
    }
    assert "private" not in str(result)


def test_plan_review_requires_a_verified_benchmark_not_only_a_moving_quote():
    valid = {"status": "measured_move", "symbol": "ETH",
             "source_status": "available", "plan_status": "matches",
             "quote_source_observed_at": "2026-11-17T12:00:00Z"}
    assert probe._verified_plan_evidence(valid)
    assert not probe._verified_plan_evidence({**valid, "source_status": "invalid_weights"})
    assert not probe._verified_plan_evidence({**valid, "plan_status": "insufficient_data"})


def test_coach_probe_reuses_one_loop_without_asyncio_runner(monkeypatch):
    from backend.infrastructure import database

    loops = []

    async def observe_loop():
        loops.append(asyncio.get_running_loop())

    async def dispose():
        loops.append(asyncio.get_running_loop())

    def case(namespace, bound, *, trace, run_async):
        run_async(observe_loop())
        return {"result": "PASS"}

    monkeypatch.setattr(probe, "_require_run", lambda namespace: 123)
    monkeypatch.setattr(probe, "_score_case", case)
    monkeypatch.setattr(probe, "_risk_case", case)
    monkeypatch.setattr(database, "engine", SimpleNamespace(dispose=dispose))
    monkeypatch.delattr(asyncio, "Runner", raising=False)

    result = probe.run("qa-44006750736-1-12345678-abcdef12")
    assert result["result"] == "PASS"
    assert len(loops) == 3
    assert loops[0] is loops[1] is loops[2]
    assert loops[0].is_closed()


def test_coach_probe_sanitizes_pool_disposal_failure(monkeypatch):
    from backend.infrastructure import database

    async def dispose():
        raise RuntimeError("private database value")

    monkeypatch.setattr(probe, "_require_run", lambda namespace: 123)
    monkeypatch.setattr(probe, "_score_case", lambda namespace, bound, *, trace, run_async: {})
    monkeypatch.setattr(probe, "_risk_case", lambda namespace, bound, *, trace, run_async: {})
    monkeypatch.setattr(database, "engine", SimpleNamespace(dispose=dispose))

    result = probe.run("qa-44006750736-1-12345678-abcdef12")
    assert result["result"] == "FAIL"
    assert result["resource_cleanup"] == {
        "result": "FAIL", "reason": "coach_feed_runtime_failed",
    }
    assert "private" not in str(result)


def test_coach_probe_task_status_is_allowlisted():
    assert probe._safe_task_status(SimpleNamespace(state="PENDING")) == "pending_unconfirmed"
    assert probe._safe_task_status(SimpleNamespace(state="SUCCESS")) == "success"
    assert probe._safe_task_status(SimpleNamespace(state="private worker error")) == "unknown"

    class FailingTask:
        @property
        def state(self):
            raise RuntimeError("private worker error")

    assert probe._safe_task_status(FailingTask()) == "unknown"


def test_coach_probe_records_missing_card_timeout_without_task_details(monkeypatch):
    async def missing(*args, **kwargs):
        raise RuntimeError("coach_feed_improvement_card_missing")

    monkeypatch.setattr(probe, "_feed", missing)
    diagnostic = {"dispatch": "enqueued", "task_status": "unknown",
                  "card_found": False, "timed_out": False}
    with pytest.raises(RuntimeError, match="coach_feed_improvement_card_missing"):
        asyncio.run(probe._await_feed(123, "improvement_suggestion", subject="asset",
                                      timeout_seconds=0, task=SimpleNamespace(state="PENDING"),
                                      diagnostic=diagnostic))
    assert diagnostic == {"dispatch": "enqueued", "task_status": "pending_unconfirmed",
                          "card_found": False, "timed_out": True}


def test_coach_probe_records_card_and_completed_task(monkeypatch):
    async def found(*args, **kwargs):
        return {"evidence": {"suggestion_kind": "weights"}}

    monkeypatch.setattr(probe, "_feed", found)
    diagnostic = {"dispatch": "enqueued", "task_status": "unknown",
                  "card_found": False, "timed_out": False}
    card = asyncio.run(probe._await_feed(123, "improvement_suggestion", subject="asset",
                                         task=SimpleNamespace(state="SUCCESS"), diagnostic=diagnostic))
    assert card["evidence"]["suggestion_kind"] == "weights"
    assert diagnostic == {"dispatch": "enqueued", "task_status": "success",
                          "card_found": True, "timed_out": False}


def test_coach_probe_includes_only_allowlisted_improvement_diagnostic(monkeypatch):
    monkeypatch.setattr(probe, "_require_run", lambda namespace: 123)

    def score_case(namespace, bound, *, trace, run_async):
        trace["stage"] = "improvement_wait"
        trace["improvement_diagnostic"] = {
            "dispatch": "enqueued", "task_status": "failure",
            "card_found": False, "timed_out": True,
            "private_error": "private worker error",
        }
        raise RuntimeError("coach_feed_improvement_card_missing")

    monkeypatch.setattr(probe, "_score_case", score_case)
    monkeypatch.setattr(probe, "_risk_case", lambda namespace, bound, *, trace, run_async: {})
    result = probe.run("qa-44006750736-1-12345678-abcdef12")
    assert result["score_and_plan"] == {
        "result": "FAIL", "reason": "coach_feed_improvement_card_missing",
        "failure_stage": "improvement_wait", "fixture_state": "not_created",
        "improvement_diagnostic": {
            "dispatch": "enqueued", "task_status": "failure",
            "card_found": False, "timed_out": True,
        },
    }
    assert "private worker error" not in str(result)
