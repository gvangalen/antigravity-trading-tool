"""Secret-free checks for the read-only prior-run fixture audit."""

from contextlib import contextmanager
import json

import pytest

from backend.scripts import probe_protected_trader_fixture_audit as audit
from backend.scripts.probe_protected_paper_exit_reconciliation import _stage, _review_step
from backend.scripts.run_finn_production_qa import profile_error_category


class Cursor:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.rows = None

    def execute(self, _query, _params):
        self.rows = next(self.responses)

    def fetchall(self):
        return self.rows

    def fetchone(self):
        return self.rows[0]


class Connection:
    def __init__(self, responses):
        self.cursor_value = Cursor(responses)
        self.closed = False

    @contextmanager
    def cursor(self):
        yield self.cursor_value

    def close(self):
        self.closed = True


LABEL = "audit-42502525173-1-9a72d5e4"
NAMESPACE = "qa-42502525173-1-9a72d5e4-1234abcd"


def test_audit_does_not_infer_cleanup_from_absent_fixture(monkeypatch):
    conn = Connection([[]])
    monkeypatch.setattr(audit, "_verify_prior_report", lambda *_: None)
    monkeypatch.setattr(audit.fixture, "_connection", lambda: conn)
    assert audit.run(LABEL) == {
        "fixture_state": "NO_RETAINED_FIXTURE", "cleanup_verified": False,
        "stage": "BEFORE_SEED_OR_CLEANED",
    }
    assert conn.closed


def test_audit_accepts_only_attempted_incomplete_prior_paper_run(monkeypatch):
    conn = Connection([[]])
    monkeypatch.setattr(audit.fixture, "_connection", lambda: conn)
    monkeypatch.setattr(audit.Path, "read_text", lambda *_a, **_k: json.dumps({
        "workflow_run_id": "42502525173-1",
        "profile": "trader_paper_exit_reconciliation",
        "target_sha": "9a72d5e4c8e10533a6a7359861e242efdd2c4808",
        "protected_profile_attempted": True, "outcome": "incomplete",
    }))
    assert audit.run(LABEL)["fixture_state"] == "NO_RETAINED_FIXTURE"


def test_review_audit_requires_exact_failed_review_profile(monkeypatch):
    monkeypatch.setattr(audit.fixture, "_connection", lambda: Connection([[]]))
    monkeypatch.setattr(audit.Path, "read_text", lambda *_a, **_k: json.dumps({
        "workflow_run_id": "42502525173-1", "profile": "trader_paper_exit_review_chain",
        "target_sha": "9a72d5e4c8e10533a6a7359861e242efdd2c4808",
        "protected_profile_attempted": True, "outcome": "incomplete",
    }))
    assert audit.run(LABEL, expected_profile="trader_paper_exit_review_chain")["fixture_state"] == "NO_RETAINED_FIXTURE"
    with pytest.raises(RuntimeError, match="trader_fixture_audit_prior_report_mismatch"):
        audit.run(LABEL)


def test_journey_audit_requires_exact_prior_profile_and_reports_only_status(monkeypatch):
    conn = Connection([
        [(17, False, {"qa_namespace": NAMESPACE})], [(False, False)], [(0,)],
        [(2,)], [(2,)], [(1,)], [(0,)], [(0,)], [(1,)], [(1,)],
    ])
    monkeypatch.setattr(audit.fixture, "_connection", lambda: conn)
    monkeypatch.setattr(audit.Path, "read_text", lambda *_a, **_k: json.dumps({
        "workflow_run_id": "42502525173-1", "profile": "setup_strategy_journey",
        "target_sha": "9a72d5e4c8e10533a6a7359861e242efdd2c4808",
        "protected_profile_attempted": True, "outcome": "incomplete",
    }))
    result = audit.run(LABEL, expected_profile="setup_strategy_journey")
    assert result == {
        "fixture_state": "QUARANTINED_INACTIVE", "cleanup_verified": False,
        "owner_active": False, "exchange_keys_present": False,
        "setups_present": True, "strategies_present": True, "bots_present": True,
        "active_or_live_bots_present": False, "journey_setup_present": True,
        "journey_strategy_present": True, "orders_present": False,
        "executions_present": False,
    }
    assert NAMESPACE not in str(result) and "17" not in str(result)
    assert conn.closed


def test_journey_audit_rejects_other_prior_profile_before_database(monkeypatch):
    monkeypatch.setattr(audit.fixture, "_connection", lambda: pytest.fail("database touched"))
    monkeypatch.setattr(audit.Path, "read_text", lambda *_a, **_k: json.dumps({
        "workflow_run_id": "42502525173-1", "profile": "trader_pair_score_continuity",
        "target_sha": "9a72d5e4c8e10533a6a7359861e242efdd2c4808",
        "protected_profile_attempted": True, "outcome": "incomplete",
    }))
    with pytest.raises(RuntimeError, match="trader_fixture_audit_prior_report_mismatch"):
        audit.run(LABEL, expected_profile="setup_strategy_journey")


def test_exact_journey_diagnostic_keeps_only_typed_execution_codes(monkeypatch):
    namespace = "qa-44968391213-1-e2872eb9-1234abcd"
    conn = Connection([
        [(17, False, {"qa_namespace": namespace})], [(False, False)], [(0,)],
        [(1,)], [(1,)], [(1,)], [(0,)], [(0,)], [(0,)], [(0,)],
        [("create_setup", "blocked", ["proposal_not_confirmed", "private detail 17"])],
    ])
    monkeypatch.setattr(audit, "_verify_prior_report", lambda *_args: None)
    monkeypatch.setattr(audit.fixture, "_connection", lambda: conn)
    result = audit.run(audit.JOURNEY_CLEANUP_LABEL, expected_profile="setup_strategy_journey")
    assert result["setup_execution_status"] == "blocked"
    assert result["setup_execution_codes"] == ["other", "proposal_not_confirmed"]
    assert result["replay_status"] == "not_recorded"
    assert namespace not in str(result) and "private detail" not in str(result)


@pytest.mark.parametrize("statuses,expected", [
    ([], "missing"), ([('unread',)], "unread"),
    ([('read',)], "read"), ([('resolved',)], "resolved"),
    ([('unread',), ('read',)], "multiple_or_other"),
])
def test_exact_journey_card_audit_reports_only_bounded_status(monkeypatch, statuses, expected):
    namespace = "qa-44974889786-1-76d282df-1234abcd"
    conn = Connection([
        [(17, False, {"qa_namespace": namespace})], [(False, False)], [(0,)],
        [(2,)], [(1,)], [(1,)], [(0,)], [(0,)], [(1,)], [(0,)],
        [(42,)], statuses,
    ])
    monkeypatch.setattr(audit, "_verify_prior_report", lambda *_args: None)
    monkeypatch.setattr(audit.fixture, "_connection", lambda: conn)
    result = audit.run(audit.JOURNEY_CARD_LABEL, expected_profile="setup_strategy_journey")
    assert result["strategy_card_status"] == expected
    assert result["strategy_card_count"] == len(statuses)
    assert namespace not in str(result) and "42" not in str(result)
    assert conn.closed


def test_transport_audit_reports_only_terminal_marker_and_fixed_failure(monkeypatch):
    namespace = "qa-44977345882-1-f5cfb7a3-1234abcd"
    prior = {"setup_strategy_journey": {"failure_stage": "setup_card",
        "reason": "journey_strategy_card_missing"}}
    monkeypatch.setattr(audit, "_verify_prior_report", lambda *_args: None)
    monkeypatch.setattr(audit.Path, "read_text", lambda path, **_kw:
                        "1" if path.name == "runner.exit" else json.dumps(prior))
    monkeypatch.setattr(audit.fixture, "_connection", lambda: Connection([
        [(17, False, {"qa_namespace": namespace})], [(False, False)], [(0,)],
        [(2,)], [(1,)], [(1,)], [(0,)], [(0,)], [(1,)], [(0,)],
    ]))
    result = audit.run(audit.JOURNEY_TRANSPORT_LABEL, expected_profile="setup_strategy_journey")
    assert result["runner_terminal_status"] == "failed"
    assert result["checkpoint_present"] is True
    assert result["prior_failure_stage"] == "setup_card"
    assert result["prior_failure_reason"] == "journey_strategy_card_missing"
    assert namespace not in str(result)


def test_exact_yes_diagnostic_reports_only_typed_predicates(monkeypatch):
    namespace = "qa-45006104528-1-50cc25ca-1234abcd"
    conn = Connection([
        [(17, False, {"qa_namespace": namespace})], [(False, False)], [(0,)],
        [(2,)], [(1,)], [(1,)], [(0,)], [(0,)], [(1,)], [(0,)],
        [(42,)], [("setup-conversation-private",)], [("feed-conversation-private",)],
        [("setup-conversation-private", "completed", {
            "initial_operation_id": "read_setup", "action_draft": {"operation_id": "create_strategy"},
            "supplied_inputs": {"setup_id": 42, "private": "secret"},
            "dispatch_count": 1, "attempt_count": 1,
        })],
    ])
    monkeypatch.setattr(audit, "_verify_prior_report", lambda *_args: None)
    monkeypatch.setattr(audit.fixture, "_connection", lambda: conn)
    result = audit.run(audit.JOURNEY_YES_DIAGNOSTIC_LABEL,
                       expected_profile="setup_strategy_journey")
    assert result["yes_diagnostic_state"] == "available"
    assert result["yes_status"] == "completed"
    assert result["yes_operation"] == "other"
    assert result["yes_guided_operation"] == "create_strategy"
    assert result["yes_setup_id_match"] is True
    assert result["yes_setup_conversation_match"] is True
    assert result["feed_turn_unique"] is True
    assert result["feed_setup_conversation_match"] is False
    assert result["feed_yes_conversation_match"] is False
    assert result["yes_dispatch_count"] == 1
    assert result["yes_attempt_count"] == 1
    assert "private" not in str(result) and "42" not in str(result)


def test_exact_yes_diagnostic_rejects_ambiguous_turns_without_exposing_rows(monkeypatch):
    namespace = "qa-45006104528-1-50cc25ca-1234abcd"
    conn = Connection([
        [(17, False, {"qa_namespace": namespace})], [(False, False)], [(0,)],
        [(2,)], [(1,)], [(1,)], [(0,)], [(0,)], [(1,)], [(0,)],
        [(42,)], [("private-one",), ("private-two",)], [], [],
    ])
    monkeypatch.setattr(audit, "_verify_prior_report", lambda *_args: None)
    monkeypatch.setattr(audit.fixture, "_connection", lambda: conn)
    result = audit.run(audit.JOURNEY_YES_DIAGNOSTIC_LABEL,
                       expected_profile="setup_strategy_journey")
    assert result["yes_diagnostic_state"] == "turn_missing_or_ambiguous"
    assert result["setup_turn_unique"] is False
    assert result["yes_turn_unique"] is False
    assert "private" not in str(result)


@pytest.mark.parametrize("label,namespace", [
    (audit.JOURNEY_STRATEGY_DIAGNOSTIC_LABEL, "qa-45015412389-1-999bd355-1234abcd"),
    (audit.JOURNEY_STRATEGY_RETEST_LABEL, "qa-45020771853-1-ea64f391-1234abcd"),
])
def test_exact_strategy_diagnostic_reports_failed_proposal_conditions_only(
    monkeypatch, label, namespace,
):
    conn = Connection([
        [(17, False, {"qa_namespace": namespace})], [(False, False)], [(0,)],
        [(2,)], [(1,)], [(1,)], [(0,)], [(0,)], [(1,)], [(0,)],
        [(42,)], [("conversation-private", {"action_draft": {"operation_id": "create_strategy"}})],
        [("conversation-private", "clarification_required", None,
          {"proposal_id": None, "confirmation_required": False, "content": "private answer"},
          {"initial_operation_id": "create_strategy", "action_draft": {"operation_id": "create_strategy"},
           "supplied_inputs": {"setup_id": 42, "private": "secret"},
           "dispatch_count": 1, "attempt_count": 1})],
    ])
    monkeypatch.setattr(audit, "_verify_prior_report", lambda *_args: None)
    monkeypatch.setattr(audit.fixture, "_connection", lambda: conn)
    result = audit.run(label,
                       expected_profile="setup_strategy_journey")
    assert result["strategy_diagnostic_state"] == "available"
    assert result["strategy_status"] == "clarification_required"
    assert result["strategy_operation"] == "create_strategy"
    assert result["strategy_guided_operation"] == "create_strategy"
    assert result["prior_yes_guided_operation"] == "create_strategy"
    assert result["strategy_proposal_present"] is False
    assert result["strategy_confirmation_required"] is False
    assert result["strategy_setup_id_match"] is True
    assert result["strategy_same_conversation_as_yes"] is True
    assert result["strategy_dispatch_count"] == 1
    assert result["strategy_attempt_count"] == 1
    assert result["strategy_error_code"] == "none"
    assert "private" not in str(result) and "42" not in str(result)


def test_journey_cleanup_rejects_other_label_before_database(monkeypatch):
    monkeypatch.setattr(audit.fixture, "_connection", lambda: pytest.fail("database touched"))
    with pytest.raises(RuntimeError, match="^journey_cleanup_label_not_allowed$"):
        audit.cleanup_journey(LABEL)


def test_journey_cleanup_rejects_active_child_without_write(monkeypatch):
    namespace = "qa-44968391213-1-e2872eb9-1234abcd"
    monkeypatch.setattr(audit, "_verify_prior_report", lambda *_args: None)
    monkeypatch.setattr(audit.Path, "read_text", lambda *_a, **_k: json.dumps({
        "setup_strategy_journey": {"fixture_state": "quarantined",
            "failure_stage": "setup_confirmation", "reason": "journey_replay_failed"},
    }))
    monkeypatch.setattr(audit.fixture, "_connection", lambda: Connection([
        [(17, True, {"qa_namespace": namespace})],
    ]))
    monkeypatch.setattr(audit.fixture, "_cleanup", lambda *_a, **_k: pytest.fail("write called"))
    with pytest.raises(RuntimeError, match="^journey_cleanup_owner_unsafe$"):
        audit.cleanup_journey(audit.JOURNEY_CLEANUP_LABEL)


def test_journey_cleanup_requires_failed_quarantined_report_before_database(monkeypatch):
    monkeypatch.setattr(audit.fixture, "_connection", lambda: pytest.fail("database touched"))
    monkeypatch.setattr(audit.Path, "read_text", lambda *_a, **_k: json.dumps({
        "workflow_run_id": "44968391213-1", "profile": "setup_strategy_journey",
        "target_sha": "e2872eb9ad15376beb37c4e1ac79d50ccc874b27",
        "protected_profile_attempted": True, "outcome": "failed",
        "setup_strategy_journey": {"fixture_state": "cleaned",
            "failure_stage": "setup_confirmation", "reason": "journey_replay_failed"},
    }))
    with pytest.raises(RuntimeError, match="^journey_cleanup_prior_state_mismatch$"):
        audit.cleanup_journey(audit.JOURNEY_CLEANUP_LABEL)


@pytest.mark.parametrize("blocked_index,code", [
    (2, "journey_cleanup_keys_unsafe"),
    (3, "journey_cleanup_trade_unsafe"),
    (8, "journey_cleanup_btc_row_unsafe"),
])
def test_journey_cleanup_refuses_unsafe_rows_without_write(monkeypatch, blocked_index, code):
    namespace = "qa-44968391213-1-e2872eb9-1234abcd"
    prior = {"setup_strategy_journey": {"fixture_state": "quarantined",
        "failure_stage": "setup_confirmation", "reason": "journey_replay_failed"}}
    responses = [
        [(17, False, {"qa_namespace": namespace})], [(22, False, False)],
        *([[(0,)]] * 8),
    ]
    responses[blocked_index] = [(1,)]
    monkeypatch.setattr(audit, "_verify_prior_report", lambda *_args: None)
    monkeypatch.setattr(audit.Path, "read_text", lambda *_a, **_k: json.dumps(prior))
    monkeypatch.setattr(audit.fixture, "_connection", lambda: Connection(responses))
    monkeypatch.setattr(audit.fixture, "_cleanup", lambda *_a, **_k: pytest.fail("write called"))
    with pytest.raises(RuntimeError, match=f"^{code}$"):
        audit.cleanup_journey(audit.JOURNEY_CLEANUP_LABEL)


@pytest.mark.parametrize("workflow_id,sha_prefix,target_sha", [
    ("44968391213", "e2872eb9", "e2872eb9ad15376beb37c4e1ac79d50ccc874b27"),
    ("44972794086", "da950aac", "da950aace77443e0c3660400234338b56e3da5b8"),
])
def test_journey_cleanup_removes_only_exact_safe_child_and_checks_postcondition(
    monkeypatch, workflow_id, sha_prefix, target_sha,
):
    namespace = f"qa-{workflow_id}-1-{sha_prefix}-1234abcd"
    label = f"audit-{workflow_id}-1-{sha_prefix}"
    prior = {
        "workflow_run_id": f"{workflow_id}-1", "profile": "setup_strategy_journey",
        "target_sha": target_sha,
        "protected_profile_attempted": True, "outcome": "failed",
        "setup_strategy_journey": {"fixture_state": "quarantined",
            "failure_stage": "setup_confirmation", "reason": "journey_replay_failed"},
    }
    before = Connection([
        [(17, False, {"qa_namespace": namespace})], [(22, False, False)],
        *([[(0,)]] * 8),
    ])
    after = Connection([[ (0,) ] for _ in range(8)])
    connections = iter((before, after))
    calls = []
    monkeypatch.setattr(audit.Path, "read_text", lambda *_a, **_k: json.dumps(prior))
    monkeypatch.setattr(audit.fixture, "_connection", lambda: next(connections))
    monkeypatch.setattr(audit.fixture, "_cleanup", lambda *args, **kwargs: calls.append((args, kwargs)))
    assert audit.cleanup_journey(label) == {
        "fixture_state": "CLEANED", "cleanup_verified": True,
    }
    assert calls == [((namespace, 17, 22), {"require_safe_pair_cleanup": True})]
    assert before.closed and after.closed


@pytest.mark.parametrize("new_setup,expected_error", [
    (True, None), (False, "journey_cleanup_btc_row_unsafe"),
])
def test_exact_journey_card_cleanup_requires_only_expected_saved_setup(
    monkeypatch, new_setup, expected_error,
):
    namespace = "qa-44974889786-1-76d282df-1234abcd"
    prior = {
        "workflow_run_id": "44974889786-1", "profile": "setup_strategy_journey",
        "target_sha": "76d282dfe2aab6f9c97cb3b342cf6d97e50a244b",
        "protected_profile_attempted": True, "outcome": "failed",
        "setup_strategy_journey": {"fixture_state": "quarantined",
            "failure_stage": "setup_card", "reason": "journey_strategy_card_missing"},
    }
    saved_name = f"QA BTC Setup {namespace}" if new_setup else "other BTC setup"
    before = Connection([
        [(17, False, {"qa_namespace": namespace})], [(22, False, False)],
        *([[(0,)]] * 6),
        [(namespace, "ETH"), (saved_name, "BTC")], [(namespace, "ETH")],
        [(saved_name, "BTC", "USDT")], [(0,)], [(0,)],
    ])
    after = Connection([[(0,)] for _ in range(8)])
    connections = iter((before, after))
    calls = []
    monkeypatch.setattr(audit.Path, "read_text", lambda *_a, **_k: json.dumps(prior))
    monkeypatch.setattr(audit.fixture, "_connection", lambda: next(connections))
    monkeypatch.setattr(audit.fixture, "_cleanup", lambda *args, **kwargs: calls.append((args, kwargs)))
    if expected_error:
        with pytest.raises(RuntimeError, match=f"^{expected_error}$"):
            audit.cleanup_journey(audit.JOURNEY_CARD_LABEL)
        assert not calls
    else:
        assert audit.cleanup_journey(audit.JOURNEY_CARD_LABEL) == {
            "fixture_state": "CLEANED", "cleanup_verified": True,
        }
        assert calls == [((namespace, 17, 22), {"require_safe_pair_cleanup": True})]


@pytest.mark.parametrize("terminal,expected_error", [
    ("1", None), ("", "journey_cleanup_runner_not_terminal"),
])
def test_transport_child_cleanup_requires_terminal_runner_and_exact_setup(
    monkeypatch, terminal, expected_error,
):
    namespace = "qa-44977345882-1-f5cfb7a3-1234abcd"
    saved_name = f"QA BTC Setup {namespace}"
    prior = {"setup_strategy_journey": {"fixture_state": "quarantined",
        "failure_stage": "setup_card", "reason": "journey_strategy_card_missing"}}
    before = Connection([
        [(17, False, {"qa_namespace": namespace})], [(22, False, False)],
        *([[(0,)]] * 6),
        [(namespace, "ETH"), (saved_name, "BTC")], [(namespace, "ETH")],
        [(saved_name, "BTC", "USDT")], [(0,)], [(0,)],
    ])
    after = Connection([[(0,)] for _ in range(8)])
    connections = iter((before, after))
    calls = []
    monkeypatch.setattr(audit, "_verify_prior_report", lambda *_args: None)
    monkeypatch.setattr(audit.Path, "read_text", lambda path, **_kw:
                        terminal if path.name == "runner.exit" else json.dumps(prior))
    monkeypatch.setattr(audit.fixture, "_connection", lambda: next(connections))
    monkeypatch.setattr(audit.fixture, "_cleanup", lambda *args, **kwargs: calls.append((args, kwargs)))
    if expected_error:
        with pytest.raises(RuntimeError, match=f"^{expected_error}$"):
            audit.cleanup_journey(audit.JOURNEY_TRANSPORT_LABEL)
        assert not calls
    else:
        assert audit.cleanup_journey(audit.JOURNEY_TRANSPORT_LABEL) == {
            "fixture_state": "CLEANED", "cleanup_verified": True,
        }
        assert calls == [((namespace, 17, 22), {"require_safe_pair_cleanup": True})]


@pytest.mark.parametrize("failure_stage,expected_error", [
    ("strategy_guided", None),
    ("strategy_confirmation", "journey_cleanup_prior_state_mismatch"),
])
def test_exact_short_yes_child_cleanup_requires_guided_failure_and_safe_rows(
    monkeypatch, failure_stage, expected_error,
):
    namespace = "qa-45006104528-1-50cc25ca-1234abcd"
    saved_name = f"QA BTC Setup {namespace}"
    prior = {"setup_strategy_journey": {"fixture_state": "quarantined",
        "failure_stage": failure_stage, "reason": "journey_strategy_guided_failed"}}
    before = Connection([
        [(17, False, {"qa_namespace": namespace})], [(22, False, False)],
        *([[(0,)]] * 6),
        [(namespace, "ETH"), (saved_name, "BTC")], [(namespace, "ETH")],
        [(saved_name, "BTC", "USDT")], [(0,)], [(0,)],
    ])
    after = Connection([[(0,)] for _ in range(8)])
    connections = iter((before, after))
    calls = []
    monkeypatch.setattr(audit, "_verify_prior_report", lambda *_args: None)
    monkeypatch.setattr(audit.Path, "read_text", lambda *_a, **_k: json.dumps(prior))
    monkeypatch.setattr(audit.fixture, "_connection", lambda: next(connections))
    monkeypatch.setattr(audit.fixture, "_cleanup", lambda *args, **kwargs: calls.append((args, kwargs)))
    if expected_error:
        with pytest.raises(RuntimeError, match=f"^{expected_error}$"):
            audit.cleanup_journey(audit.JOURNEY_YES_DIAGNOSTIC_LABEL)
        assert not calls
    else:
        assert audit.cleanup_journey(audit.JOURNEY_YES_DIAGNOSTIC_LABEL) == {
            "fixture_state": "CLEANED", "cleanup_verified": True,
        }
        assert calls == [((namespace, 17, 22), {"require_safe_pair_cleanup": True})]


@pytest.mark.parametrize("label,namespace", [
    (audit.JOURNEY_STRATEGY_DIAGNOSTIC_LABEL, "qa-45015412389-1-999bd355-1234abcd"),
    (audit.JOURNEY_STRATEGY_RETEST_LABEL, "qa-45020771853-1-ea64f391-1234abcd"),
])
@pytest.mark.parametrize("failure_stage,expected_error", [
    ("strategy_proposal", None),
    ("strategy_confirmation", "journey_cleanup_prior_state_mismatch"),
])
def test_exact_strategy_proposal_child_cleanup_requires_failure_and_safe_rows(
    monkeypatch, label, namespace, failure_stage, expected_error,
):
    saved_name = f"QA BTC Setup {namespace}"
    prior = {"setup_strategy_journey": {"fixture_state": "quarantined",
        "failure_stage": failure_stage, "reason": "journey_strategy_proposal_missing"}}
    before = Connection([
        [(17, False, {"qa_namespace": namespace})], [(22, False, False)],
        *([[(0,)]] * 6),
        [(namespace, "ETH"), (saved_name, "BTC")], [(namespace, "ETH")],
        [(saved_name, "BTC", "USDT")], [(0,)], [(0,)],
    ])
    after = Connection([[(0,)] for _ in range(8)])
    connections = iter((before, after))
    calls = []
    monkeypatch.setattr(audit, "_verify_prior_report", lambda *_args: None)
    monkeypatch.setattr(audit.Path, "read_text", lambda *_a, **_k: json.dumps(prior))
    monkeypatch.setattr(audit.fixture, "_connection", lambda: next(connections))
    monkeypatch.setattr(audit.fixture, "_cleanup", lambda *args, **kwargs: calls.append((args, kwargs)))
    if expected_error:
        with pytest.raises(RuntimeError, match=f"^{expected_error}$"):
            audit.cleanup_journey(label)
        assert not calls
    else:
        assert audit.cleanup_journey(label) == {
            "fixture_state": "CLEANED", "cleanup_verified": True,
        }
        assert calls == [((namespace, 17, 22), {"require_safe_pair_cleanup": True})]


@pytest.mark.parametrize("analysis_status,expected_status", [
    ("failed", "failed"), ("private_status", "other"),
])
def test_review_audit_reports_only_bounded_review_and_finn_progress(monkeypatch, analysis_status, expected_status):
    conn = Connection([
        [(17, False, {"qa_namespace": NAMESPACE})], [(False, False)], [(0,)],
        [("assessment", 1), ("paper_exit", 1)], [(1,)], [(1,)], [(1,)],
        [(analysis_status,)], [(1,)],
    ])
    monkeypatch.setattr(audit, "_verify_prior_report", lambda *_: None)
    monkeypatch.setattr(audit.fixture, "_connection", lambda: conn)
    result = audit.run(LABEL, expected_profile="trader_paper_exit_review_chain")
    assert result["fixture_state"] == "QUARANTINED_INACTIVE"
    assert result["review_present"] is True
    assert result["review_analysis_status"] == expected_status
    assert result["finn_run_present"] is True
    assert NAMESPACE not in str(result) and "17" not in str(result)


def test_review_cleanup_blocks_other_profile_before_database(monkeypatch):
    monkeypatch.setattr(audit.fixture, "_connection", lambda: pytest.fail("database touched"))
    monkeypatch.setattr(audit.Path, "read_text", lambda *_a, **_k: json.dumps({
        "workflow_run_id": "42502525173-1", "profile": "trader_paper_exit_reconciliation",
        "target_sha": "9a72d5e4c8e10533a6a7359861e242efdd2c4808",
        "protected_profile_attempted": True, "outcome": "incomplete",
    }))
    with pytest.raises(RuntimeError, match="trader_fixture_audit_prior_report_mismatch"):
        audit.cleanup_review(LABEL)


def test_review_cleanup_blocks_active_child_without_deletion(monkeypatch):
    conn = Connection([[(17, True, {"qa_namespace": NAMESPACE})]])
    monkeypatch.setattr(audit, "_verify_prior_report", lambda *_: None)
    monkeypatch.setattr(audit.fixture, "_connection", lambda: conn)
    monkeypatch.setattr(audit.fixture, "_cleanup", lambda *_a, **_k: pytest.fail("cleanup called"))
    with pytest.raises(RuntimeError, match="trader_review_cleanup_owner_unsafe"):
        audit.cleanup_review(LABEL)


@pytest.mark.parametrize("keys,live_orders,code", [
    (1, 0, "trader_review_cleanup_keys_unsafe"),
    (0, 1, "trader_review_cleanup_live_order_unsafe"),
])
def test_review_cleanup_blocks_keys_and_nonpaper_orders(monkeypatch, keys, live_orders, code):
    conn = Connection([
        [(17, False, {"qa_namespace": NAMESPACE})], [(22, False, False)],
        [(keys,)], [(live_orders,)],
    ])
    monkeypatch.setattr(audit, "_verify_prior_report", lambda *_: None)
    monkeypatch.setattr(audit.fixture, "_connection", lambda: conn)
    monkeypatch.setattr(audit.fixture, "_cleanup", lambda *_a, **_k: pytest.fail("cleanup called"))
    with pytest.raises(RuntimeError, match=f"^{code}$"):
        audit.cleanup_review(LABEL)


def test_review_cleanup_verifies_child_and_review_absence(monkeypatch):
    before = Connection([
        [(17, False, {"qa_namespace": NAMESPACE})], [(22, False, False)],
        [(0,)], [(0,)],
    ])
    after = Connection([[(0,)]] * 5)
    connections = iter([before, after])
    cleaned = []
    monkeypatch.setattr(audit, "_verify_prior_report", lambda *_: None)
    monkeypatch.setattr(audit.fixture, "_connection", lambda: next(connections))
    monkeypatch.setattr(audit.fixture, "_cleanup", lambda *args, **kwargs: cleaned.append((args, kwargs)))
    assert audit.cleanup_review(LABEL) == {"fixture_state": "CLEANED", "cleanup_verified": True}
    assert cleaned == [((NAMESPACE, 17, 22), {"require_safe_review_cleanup": True})]
    assert before.closed and after.closed


def test_audit_reports_only_bounded_quarantine_state(monkeypatch):
    conn = Connection([
        [(17, False, {"qa_namespace": NAMESPACE})], [(False, False)],
        [(0,)], [("assessment", 1)], [(0,)], [(0,)], [(0,)],
    ])
    monkeypatch.setattr(audit.fixture, "_connection", lambda: conn)
    monkeypatch.setattr(audit, "_verify_prior_report", lambda *_: None)
    result = audit.run(LABEL)
    assert result == {
        "fixture_state": "QUARANTINED_INACTIVE", "cleanup_verified": False,
        "paper_open_present": True, "paper_exit_decision_present": False,
        "paper_exit_order_present": False, "paper_exit_execution_present": False,
        "paper_exit_ledger_present": False,
    }
    assert "17" not in str(result) and NAMESPACE not in str(result)
    assert conn.closed


def test_pair_audit_requires_matching_prior_pair_run_and_reports_only_fixed_presence(monkeypatch):
    conn = Connection([
        [(17, False, {"qa_namespace": NAMESPACE})], [(False, False)], [(0,)],
        [(3,)], [(2,)], [(2,)], [(2,)], [(0,)], [(0,)],
    ])
    monkeypatch.setattr(audit.fixture, "_connection", lambda: conn)
    monkeypatch.setattr(audit.Path, "read_text", lambda *_a, **_k: json.dumps({
        "workflow_run_id": "42502525173-1", "profile": "trader_pair_score_continuity",
        "target_sha": "9a72d5e4c8e10533a6a7359861e242efdd2c4808",
        "protected_profile_attempted": True, "outcome": "incomplete",
    }))
    assert audit.run(LABEL, expected_profile="trader_pair_score_continuity") == {
        "fixture_state": "QUARANTINED_INACTIVE", "cleanup_verified": False,
        "pair_configs_present": True, "pair_market_readings_present": True,
        "pair_technical_readings_present": True, "pair_scores_present": True,
        "orders_present": False, "executions_present": False,
    }
    assert conn.closed


def test_pair_audit_rejects_paper_prior_report_before_database(monkeypatch):
    monkeypatch.setattr(audit.fixture, "_connection", lambda: pytest.fail("database touched"))
    monkeypatch.setattr(audit.Path, "read_text", lambda *_a, **_k: json.dumps({
        "workflow_run_id": "42502525173-1", "profile": "trader_paper_exit_reconciliation",
        "target_sha": "9a72d5e4c8e10533a6a7359861e242efdd2c4808",
        "protected_profile_attempted": True, "outcome": "incomplete",
    }))
    with pytest.raises(RuntimeError, match="trader_fixture_audit_prior_report_mismatch"):
        audit.run(LABEL, expected_profile="trader_pair_score_continuity")


def test_pair_cleanup_requires_inactive_uncredentialed_child_and_verifies_zero_rows(monkeypatch):
    before = Connection([
        [(17, {"qa_namespace": NAMESPACE})], [(22, False, False)],
    ])
    after = Connection([[(0,)], *([[(0,)]] * 9)])
    connections = iter((before, after))
    monkeypatch.setattr(audit, "PAIR_CLEANUP_LABELS", {LABEL})
    monkeypatch.setattr(audit.fixture, "_connection", lambda: next(connections))
    monkeypatch.setattr(audit, "_verify_prior_report", lambda *_args: None)
    cleaned = []
    monkeypatch.setattr(audit.fixture, "_cleanup", lambda *args, **kwargs: cleaned.append((args, kwargs)))
    result = audit.cleanup_pair(LABEL)
    assert result == {"fixture_state": "CLEANED", "cleanup_verified": True}
    assert cleaned == [((NAMESPACE, 17, 22), {"require_safe_pair_cleanup": True})]
    assert before.closed and after.closed
    assert NAMESPACE not in str(result) and "17" not in str(result)


def test_pair_cleanup_refuses_active_or_credentialed_child_before_write(monkeypatch):
    for responses, code in (
        ([[(17, {"qa_namespace": "wrong"})]], "trader_pair_cleanup_owner_unsafe"),
        ([[(17, {"qa_namespace": NAMESPACE})], []], "trader_pair_cleanup_bot_unsafe"),
    ):
        monkeypatch.setattr(audit, "PAIR_CLEANUP_LABELS", {LABEL})
        monkeypatch.setattr(audit, "_verify_prior_report", lambda *_args: None)
        monkeypatch.setattr(audit.fixture, "_connection", lambda values=responses: Connection(values))
        monkeypatch.setattr(audit.fixture, "_cleanup", lambda *_args: pytest.fail("unexpected write"))
        with pytest.raises(RuntimeError, match=f"^{code}$"):
            audit.cleanup_pair(LABEL)


def test_pair_cleanup_label_is_bound_to_audited_runs(monkeypatch):
    assert audit.PAIR_CLEANUP_LABELS == {
        "audit-42543306392-1-20322165",
        "audit-42546922438-1-169d0252",
        "audit-42549516935-1-1d8c6a3a",
        "audit-42551140172-1-43009b2a",
        "audit-42552626218-1-a30e0117",
        "audit-42556709762-1-30a20e36",
        "audit-42559343113-1-dcc45900",
        "audit-42561696534-1-7d0267d1",
        "audit-42564612181-1-d62ddf23",
        "audit-42567582048-1-376d3a95",
        "audit-42662037346-1-b2cc1d3b",
        "audit-42665642208-1-3c0ce3f4",
        "audit-42668760580-1-e20b92fb",
    }
    monkeypatch.setattr(audit.fixture, "_connection", lambda: pytest.fail("database touched"))
    with pytest.raises(RuntimeError, match="^trader_pair_cleanup_label_not_allowed$"):
        audit.cleanup_pair("audit-42502525173-1-9a72d5e4")


@pytest.mark.parametrize("blocked_table", ["bot_decisions", "bot_orders", "bot_executions", "bot_ledger"])
def test_locked_cleanup_blocks_prior_decisions_and_trades_without_delete(monkeypatch, blocked_table):
    queries = []
    class LockedCursor:
        rowcount = 0
        def execute(self, query, params):
            queries.append(query)
        def fetchone(self):
            if len(queries) == 1:
                return ({"qa_fixture": audit.fixture.FIXTURE_MARKER,
                         "qa_namespace": NAMESPACE},)
            if len(queries) == 2:
                return (False,)
            if len(queries) == 4:
                return (0,)
            if len(queries) in (5, 6, 7, 8):
                return (int(blocked_table in queries[-1]),)
            raise AssertionError("unexpected query")
        def fetchall(self):
            return [(22, False, False)]
    class LockedConnection:
        rolled_back = False
        committed = False
        @contextmanager
        def cursor(self):
            yield LockedCursor()
        def rollback(self):
            self.rolled_back = True
        def commit(self):
            self.committed = True
        def close(self):
            pass
    conn = LockedConnection()
    monkeypatch.setattr(audit.fixture, "_connection", lambda: conn)
    with pytest.raises(RuntimeError, match="^fixture_cleanup_failed$"):
        audit.fixture._cleanup(NAMESPACE, 17, 22, require_safe_pair_cleanup=True)
    assert conn.rolled_back and not conn.committed
    assert "FOR UPDATE" in queries[0] and "FOR UPDATE" in queries[2]
    assert blocked_table in queries[-1]
    assert not any("DELETE FROM" in query for query in queries)


@pytest.mark.parametrize("blocked_query", ["exchange_keys", "execution_environment"])
def test_locked_review_cleanup_blocks_keys_or_nonpaper_orders(monkeypatch, blocked_query):
    queries = []
    class LockedCursor:
        def execute(self, query, _params):
            queries.append(query)
        def fetchone(self):
            query = queries[-1]
            if "SELECT ai_preferences" in query:
                return ({"qa_fixture": audit.fixture.FIXTURE_MARKER,
                         "qa_namespace": NAMESPACE},)
            if "SELECT is_active" in query:
                return (False,)
            if "SELECT COUNT" in query:
                return (int(blocked_query in query),)
            raise AssertionError("unexpected query")
        def fetchall(self):
            return [(22, False, False)]
    class LockedConnection:
        rolled_back = False
        committed = False
        @contextmanager
        def cursor(self):
            yield LockedCursor()
        def rollback(self):
            self.rolled_back = True
        def commit(self):
            self.committed = True
        def close(self):
            pass
    conn = LockedConnection()
    monkeypatch.setattr(audit.fixture, "_connection", lambda: conn)
    with pytest.raises(RuntimeError, match="^fixture_cleanup_failed$"):
        audit.fixture._cleanup(NAMESPACE, 17, 22, require_safe_review_cleanup=True)
    assert conn.rolled_back and not conn.committed
    assert not any("DELETE FROM" in query for query in queries)


def test_audit_rejects_unscoped_label_before_database(monkeypatch):
    monkeypatch.setattr(audit.fixture, "_connection", lambda: pytest.fail("database touched"))
    with pytest.raises(RuntimeError, match="trader_fixture_audit_label_invalid"):
        audit.run("audit-not-a-run")


def test_audit_requires_matching_prior_paper_report(monkeypatch):
    monkeypatch.setattr(audit.fixture, "_connection", lambda: pytest.fail("database touched"))
    def unavailable(*_args, **_kwargs):
        raise OSError("private path")
    monkeypatch.setattr(audit.Path, "read_text", unavailable)
    with pytest.raises(RuntimeError, match="trader_fixture_audit_prior_report_unavailable"):
        audit.run(LABEL)


def test_audit_rejects_another_prior_profile(monkeypatch):
    monkeypatch.setattr(audit.fixture, "_connection", lambda: pytest.fail("database touched"))
    monkeypatch.setattr(audit.Path, "read_text", lambda *_a, **_k: json.dumps({
        "workflow_run_id": "42502525173-1", "profile": "auth_preflight",
        "target_sha": "9a72d5e4c8e10533a6a7359861e242efdd2c4808",
    }))
    with pytest.raises(RuntimeError, match="trader_fixture_audit_prior_report_mismatch"):
        audit.run(LABEL)


@pytest.mark.parametrize("attempted,outcome", [(False, "incomplete"), (True, "passed")])
def test_audit_rejects_unattempted_or_successful_prior_run(monkeypatch, attempted, outcome):
    monkeypatch.setattr(audit.fixture, "_connection", lambda: pytest.fail("database touched"))
    monkeypatch.setattr(audit.Path, "read_text", lambda *_a, **_k: json.dumps({
        "workflow_run_id": "42502525173-1",
        "profile": "trader_paper_exit_reconciliation",
        "target_sha": "9a72d5e4c8e10533a6a7359861e242efdd2c4808",
        "protected_profile_attempted": attempted, "outcome": outcome,
    }))
    with pytest.raises(RuntimeError, match="trader_fixture_audit_prior_report_mismatch"):
        audit.run(LABEL)


def test_paper_exit_stage_codes_hide_exception_text():
    with pytest.raises(RuntimeError, match="^paper_exit_paper_open_failed$") as caught:
        with _stage("paper_open"):
            raise TypeError("private fixture data")
    assert caught.value.probe_phase == "paper_open"
    with pytest.raises(RuntimeError, match="private fixture data") as caught:
        with _stage("review_chain"):
            raise RuntimeError("private fixture data")
    assert caught.value.probe_phase == "review_chain"
    with pytest.raises(RuntimeError, match="private fixture data") as caught:
        with _review_step("projection_analysis"):
            raise RuntimeError("private fixture data")
    assert caught.value.review_step == "projection_analysis"
    assert profile_error_category("trader_paper_exit_review_chain", RuntimeError(
        "closed_paper_review_ai_unavailable:timeout")) == "paper_exit_review_ai_unavailable_timeout"
    assert profile_error_category("trader_paper_exit_review_chain", RuntimeError(
        "closed_paper_review_ai_unavailable:private")) == "paper_exit_probe_runtime_error"
    assert profile_error_category(
        "trader_paper_exit_reconciliation", RuntimeError("paper_exit_paper_open_failed")
    ) == "paper_exit_paper_open_failed"
    assert profile_error_category(
        "trader_paper_exit_fixture_audit", RuntimeError("private fixture data")
    ) == "trader_fixture_audit_runtime_error"
