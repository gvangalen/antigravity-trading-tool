import asyncio
from contextlib import contextmanager
import pytest
from types import SimpleNamespace

from backend.scripts import probe_protected_account_answer as probe
from backend.scripts import probe_protected_closed_paper_review as review_probe
from backend.scripts import probe_protected_paper_exit_reconciliation as exit_probe
from backend.schemas.finn_v2_schema import EvidenceItem
from backend.infrastructure import database
from backend.infrastructure.repositories import finn_v2_runtime_contract_repository as contracts
from backend.scripts.run_finn_production_qa import profile_error_category


NAMESPACE = "qa-123-1-ad9fe0d3-deadbeef"


def _tool_results(*, cadence="weekly"):
    return [
        {"scope": "read_active_setup", "status": "completed", "source": "setups",
         "data": {"setup_id": 1, "dca_frequency": cadence}},
        {"scope": "read_linked_strategy", "status": "completed", "source": "strategies",
         "data": {"strategy_id": 2, "base_amount": 10}},
        {"scope": "read_bot_status", "status": "completed", "source": "bot_configs",
         "data": {"bot_id": 3, "is_active": True, "is_live": False,
                  "latest_decision": {"decision_id": 4, "action": "hold",
                                      "decision_at": "2026-11-08T12:00:00Z"}}},
        {"scope": "read_portfolio", "status": "completed", "source": "bot_portfolios",
         "data": {"bots": [{"bot_id": 3, "position_qty": "0.01"}]}},
    ]


def _public_refs():
    return [
        EvidenceItem(entity_type=kind, entity_id=str(source_id), source=source,
                     owned_by_user=True)
        for kind, source_id, source in (
            ("setup", 1, "setups"),
            ("strategy", 2, "strategies"),
            ("bot_status", 3, "bot_configs"),
            ("portfolio", 11, "bot_portfolios"),
        )
    ]


def test_account_probe_requires_profile_authorization_before_any_fixture_write(monkeypatch):
    monkeypatch.delenv("FINN_QA_ALLOW_TRADER_ACCOUNT_FIXTURE", raising=False)
    monkeypatch.setattr(probe.fixture, "_seed", lambda *_args: pytest.fail("fixture write"))
    with pytest.raises(RuntimeError, match="^account_fixture_not_authorized$"):
        probe.run(NAMESPACE)


@pytest.mark.parametrize("answer_passed", [True, False])
def test_account_probe_cleans_only_after_three_turn_check_passes(monkeypatch, answer_passed):
    monkeypatch.setenv("FINN_QA_ALLOW_TRADER_ACCOUNT_FIXTURE", "1")
    monkeypatch.setenv("FINN_QA_USER_ID", "7")
    steps = []
    monkeypatch.setattr(probe.fixture, "_seed", lambda *_args: (11, 22, "today"))
    monkeypatch.setattr(probe, "_prepare", lambda *_args: steps.append("prepare"))
    counts = {table: 0 for table in probe.BUSINESS_TABLES}
    counts["broker_orders"] = 0
    monkeypatch.setattr(probe, "_business_state", lambda *_args: {
        "counts": counts.copy(),
        "fingerprints": {table: b"unchanged" for table in probe.BUSINESS_TABLES},
    })
    @contextmanager
    def live_guard():
        yield []
    monkeypatch.setattr(exit_probe, "_guard_live_exchange", live_guard)
    async def turns(*_args):
        steps.append("turns")
        return {"result": "PASS" if answer_passed else "FAIL",
                "failed_checks": [] if answer_passed else ["answer_plan_omitted"]}
    monkeypatch.setattr(probe, "_probe_turns", turns)
    monkeypatch.setattr(probe.fixture, "_cleanup", lambda *_args: steps.append("cleanup"))
    monkeypatch.setattr(probe.fixture, "_quarantine", lambda *_args: steps.append("quarantine"))
    result = probe.run(NAMESPACE)
    assert result["result"] == ("PASS" if answer_passed else "FAIL")
    assert result["executions"] == result["live_calls"] == result["broker_orders"] == 0
    assert steps == ["prepare", "turns", "cleanup" if answer_passed else "quarantine"]


def test_account_probe_fails_closed_on_measured_execution(monkeypatch):
    monkeypatch.setenv("FINN_QA_ALLOW_TRADER_ACCOUNT_FIXTURE", "1")
    monkeypatch.setenv("FINN_QA_USER_ID", "7")
    monkeypatch.setattr(probe.fixture, "_seed", lambda *_args: (11, 22, "today"))
    monkeypatch.setattr(probe, "_prepare", lambda *_args: None)
    snapshots = [{table: 0 for table in probe.BUSINESS_TABLES} for _ in range(2)]
    for snapshot in snapshots:
        snapshot["broker_orders"] = 0
    snapshots[1]["finn_v2_executions"] = 1
    monkeypatch.setattr(probe, "_business_state", lambda *_args: {
        "counts": snapshots.pop(0),
        "fingerprints": {table: b"unchanged" for table in probe.BUSINESS_TABLES},
    })
    @contextmanager
    def live_guard():
        yield []
    monkeypatch.setattr(exit_probe, "_guard_live_exchange", live_guard)
    async def turns(*_args):
        return {"result": "PASS", "failed_checks": []}
    monkeypatch.setattr(probe, "_probe_turns", turns)
    quarantined = []
    monkeypatch.setattr(probe.fixture, "_quarantine", lambda *_args: quarantined.append(True))
    result = probe.run(NAMESPACE)
    assert result["result"] == "FAIL"
    assert result["executions"] == 1
    assert "account_unexpected_business_write" in result["failed_checks"]
    assert quarantined == [True]


def test_account_probe_detects_same_count_row_mutation(monkeypatch):
    monkeypatch.setenv("FINN_QA_ALLOW_TRADER_ACCOUNT_FIXTURE", "1")
    monkeypatch.setenv("FINN_QA_USER_ID", "7")
    monkeypatch.setattr(probe.fixture, "_seed", lambda *_args: (11, 22, "today"))
    monkeypatch.setattr(probe, "_prepare", lambda *_args: None)
    counts = {table: 1 for table in probe.BUSINESS_TABLES}
    counts["broker_orders"] = 0
    states = [
        {"counts": counts.copy(), "fingerprints": {table: b"before" for table in probe.BUSINESS_TABLES}},
        {"counts": counts.copy(), "fingerprints": {table: b"before" for table in probe.BUSINESS_TABLES}},
    ]
    states[1]["fingerprints"]["setups"] = b"after"
    monkeypatch.setattr(probe, "_business_state", lambda *_args: states.pop(0))
    @contextmanager
    def live_guard():
        yield []
    monkeypatch.setattr(exit_probe, "_guard_live_exchange", live_guard)
    async def turns(*_args):
        return {"result": "PASS", "failed_checks": []}
    monkeypatch.setattr(probe, "_probe_turns", turns)
    quarantined = []
    monkeypatch.setattr(probe.fixture, "_quarantine", lambda *_args: quarantined.append(True))
    result = probe.run(NAMESPACE)
    assert result["result"] == "FAIL"
    assert "account_unexpected_business_write" in result["failed_checks"]
    assert result["proposals"] == result["executions"] == 0
    assert quarantined == [True]


def test_account_turns_use_two_fresh_conversations_and_sanitize_result(monkeypatch):
    facts = {
        "plan": {"setup_id": 1, "setup_name": "private-name", "strategy_id": 2,
                 "cadence": "weekly", "base_amount_eur": "10"},
        "bot": {"id": 3, "name": "private-bot", "active": True, "live": False},
        "position": {"quantity": "0.01"},
        "latest_decision": {"id": 4, "action": "hold", "at_utc": "2026-11-08T12:00:00+00:00"},
    }
    monkeypatch.setattr(probe, "_frozen_facts", lambda *_args: facts)
    calls = []
    async def chat(_user_id, message, *, conversation_id=None):
        calls.append(conversation_id)
        conv = conversation_id or f"conversation-{len(calls)}"
        evidence = []
        response = SimpleNamespace(content="private answer", proposal_id=None,
                                   confirmation_required=False, evidence=evidence)
        return SimpleNamespace(status="completed", response=response,
                               run_id=f"run-{len(calls)}", conversation_id=conv,
                               policy=SimpleNamespace(execute_allowed=False))
    async def examined(**_kwargs):
        return {"result": "PASS", "failed_checks": []}
    monkeypatch.setattr(review_probe, "_chat_turn", chat)
    monkeypatch.setattr(probe, "examine_answer", examined)
    async def read_tool_results(**_kwargs):
        return _tool_results()
    monkeypatch.setattr(probe, "_read_tool_results", read_tool_results)
    result = asyncio.run(probe._probe_turns(11, 3))
    assert calls == [None, "conversation-1", None]
    assert result["result"] == "PASS"
    assert result["fresh_conversations"] == 2
    assert result["public_account_references"] == "not_emitted"
    assert "private" not in str(result)


def test_account_source_check_rejects_missing_or_foreign_evidence():
    facts = {
        "plan": {"setup_id": 1, "strategy_id": 2, "cadence": "daily", "base_amount_eur": "10"},
        "bot": {"id": 3, "active": True, "live": False},
        "position": {"quantity": "0.01"},
        "latest_decision": {"id": 4, "action": "hold", "at_utc": "2026-11-08T12:00:00Z"},
    }
    results = _tool_results(cadence="daily")
    refs = _public_refs()
    assert probe._source_checks([], [], facts, 11) == ["account_evidence_sources_missing"]
    assert probe._source_checks(refs, results, facts, 11) == []
    assert probe._source_checks([], results, facts, 11) == []
    evidence = [EvidenceItem(entity_type="setup", entity_id="1", source="setups",
                             owned_by_user=False)]
    assert probe._source_checks(evidence, results, facts, 11) == ["account_evidence_owner_scope"]
    evidence = [EvidenceItem(entity_type="setup", entity_id="1", source="setups")]
    assert probe._source_checks(evidence, results, facts, 11) == ["account_evidence_owner_scope"]
    evidence = [EvidenceItem(entity_type="setup", entity_id="999", source="setups",
                             owned_by_user=True)]
    assert probe._source_checks(evidence, results, facts, 11) == ["account_evidence_wrong_source"]
    evidence = [EvidenceItem(entity_type="setup", entity_id="1", source="other",
                             owned_by_user=True)]
    assert probe._source_checks(evidence, results, facts, 11) == ["account_evidence_wrong_source"]
    evidence = [EvidenceItem(entity_type="portfolio", entity_id="account", source="bot_portfolios")]
    assert probe._source_checks(evidence, results, facts, 11) == ["account_evidence_owner_scope"]
    assert probe._source_checks(refs[:-1], results, facts, 11) == []
    assert probe._source_checks(refs, results[:-1], facts, 11) == ["account_evidence_sources_missing"]
    duplicate = [*refs, refs[0]]
    assert probe._source_checks(duplicate, results, facts, 11) == ["account_evidence_references_ambiguous"]
    wrong_portfolio = [*refs[:-1], EvidenceItem(entity_type="portfolio", entity_id="12",
                                                source="bot_portfolios", owned_by_user=True)]
    assert probe._source_checks(wrong_portfolio, results, facts, 11) == ["account_evidence_wrong_source"]
    foreign = [*results, {**results[0], "data": {"setup_id": 999, "dca_frequency": "daily"}}]
    assert probe._source_checks(refs, foreign, facts, 11) == ["account_evidence_wrong_source"]
    partial = [*results[:-1], {**results[-1], "status": "partial"}]
    assert probe._source_checks(refs, partial, facts, 11) == ["account_evidence_sources_unverified"]
    assert probe._source_checks(refs, [*results, "unexpected-row"], facts, 11) == [
        "account_evidence_sources_unverified"]
    unrelated = [*refs, EvidenceItem(entity_type="scores", entity_id="7", source="scores")]
    assert probe._source_checks(unrelated, results, facts, 11) == ["account_evidence_owner_scope"]


@pytest.mark.parametrize("owner,conversation,trace_present,expected", [
    (11, "conversation-1", True, None),
    (12, "conversation-1", True, "account_runtime_owner_scope"),
    (11, "conversation-2", True, "account_runtime_owner_scope"),
    (11, "conversation-1", False, "account_tool_evidence_unavailable"),
])
def test_account_runtime_tool_trace_requires_same_owner_and_run(
    monkeypatch, owner, conversation, trace_present, expected,
):
    class Session:
        async def __aenter__(self):
            return self
        async def __aexit__(self, *_args):
            return None
    exchange = {"run_id": "run-1", "conversation_id": "conversation-1",
                "response_id": "response-1", "tool_trace": [
                    {"result": {"results": _tool_results()}}
                ]} if trace_present else {}
    contract = SimpleNamespace(user_id=owner, conversation_id=conversation,
                               state_json={"responses_exchange": exchange})
    monkeypatch.setattr(database, "async_session_factory", Session)
    async def get_for_run(self, *, run_id):
        assert run_id == "run-1"
        return contract
    monkeypatch.setattr(contracts.FinnV2RuntimeContractRepository, "get_for_run", get_for_run)
    if expected:
        with pytest.raises(RuntimeError, match=f"^{expected}$"):
            asyncio.run(probe._read_tool_results(
                run_id="run-1", conversation_id="conversation-1", user_id=11))
    else:
        assert asyncio.run(probe._read_tool_results(
            run_id="run-1", conversation_id="conversation-1", user_id=11)) == _tool_results()


def test_account_runtime_read_error_is_sanitized(monkeypatch):
    class Session:
        async def __aenter__(self):
            raise ValueError("private database value")
        async def __aexit__(self, *_args):
            return None
    monkeypatch.setattr(database, "async_session_factory", Session)
    with pytest.raises(RuntimeError, match="^account_tool_evidence_unavailable$"):
        asyncio.run(probe._read_tool_results(
            run_id="run-1", conversation_id="conversation-1", user_id=11))


def test_account_runtime_private_runtime_error_is_not_exported(monkeypatch):
    class Session:
        async def __aenter__(self):
            raise RuntimeError("private fixture identity and SQL value")
        async def __aexit__(self, *_args):
            return None
    monkeypatch.setattr(database, "async_session_factory", Session)
    with pytest.raises(RuntimeError, match="^account_tool_evidence_unavailable$"):
        asyncio.run(probe._read_tool_results(
            run_id="run-1", conversation_id="conversation-1", user_id=11))


def test_account_prepare_reports_fixed_decision_stage_without_sql_values(monkeypatch):
    class Cursor:
        rowcount = 1
        step = 0
        def __enter__(self):
            return self
        def __exit__(self, *_args):
            return None
        def execute(self, *_args):
            self.step += 1
            if self.step == 3:
                raise ValueError("private SQL and fixture identity")
        def fetchone(self):
            return (1, 2)
    class Connection:
        rolled_back = False
        def cursor(self):
            return Cursor()
        def commit(self):
            pytest.fail("commit after failed insert")
        def rollback(self):
            self.rolled_back = True
        def close(self):
            pass
    connection = Connection()
    monkeypatch.setattr(probe.fixture, "_connection", lambda: connection)
    with pytest.raises(RuntimeError, match="^account_prepare_decisions_failed$"):
        probe._prepare(11, 22)
    assert connection.rolled_back
    assert profile_error_category(
        "trader_account_state_readback", RuntimeError("account_prepare_decisions_failed")
    ) == "account_prepare_decisions_failed"


def test_account_stage_sanitizes_private_runtime_error():
    with pytest.raises(RuntimeError, match="^account_turns_failed$"):
        with probe._stage("turns"):
            raise RuntimeError("private answer and fixture identity")


@pytest.mark.parametrize("sqlstate,expected", [
    ("23505", "unique"), ("23514", "check"), ("23502", "not_null"),
    ("23503", "foreign_key"), ("22P02", "datatype"),
    ("42804", "datatype"), ("42703", "column"),
    ("99999", "failed"),
])
def test_account_decision_insert_reports_only_allowlisted_sqlstate(
    monkeypatch, sqlstate, expected,
):
    class PrivateDbError(Exception):
        def __init__(self):
            super().__init__("private SQL values")
            self.sqlstate = sqlstate
    class Cursor:
        rowcount = 1
        step = 0
        def __enter__(self):
            return self
        def __exit__(self, *_args):
            return None
        def execute(self, *_args):
            self.step += 1
            if self.step == 3:
                raise PrivateDbError()
        def fetchone(self):
            return (1, 2)
    class Connection:
        def cursor(self):
            return Cursor()
        def rollback(self):
            pass
        def close(self):
            pass
    monkeypatch.setattr(probe.fixture, "_connection", Connection)
    code = f"account_prepare_decisions_{expected}"
    with pytest.raises(RuntimeError, match=f"^{code}$"):
        probe._prepare(11, 22)
    assert profile_error_category("trader_account_state_readback", RuntimeError(code)) == code
