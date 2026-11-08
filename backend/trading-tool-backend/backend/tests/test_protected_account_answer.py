import asyncio
from contextlib import contextmanager
import pytest
from types import SimpleNamespace

from backend.scripts import probe_protected_account_answer as probe
from backend.scripts import probe_protected_closed_paper_review as review_probe
from backend.scripts import probe_protected_paper_exit_reconciliation as exit_probe


NAMESPACE = "qa-123-1-ad9fe0d3-deadbeef"


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
        evidence = [
            SimpleNamespace(entity_type="setup", entity_id="1", user_id=11,
                            user_scoped=True, payload={"dca_frequency": "weekly"}),
            SimpleNamespace(entity_type="strategy", entity_id="2", user_id=11,
                            user_scoped=True, payload={"base_amount": 10}),
            SimpleNamespace(entity_type="bot_status", entity_id="3", user_id=11,
                            user_scoped=True, payload={"is_active": True, "is_live": False,
                                "latest_decision": {"decision_id": 4, "action": "hold",
                                    "decision_at": "2026-11-08T12:00:00Z"}}),
            SimpleNamespace(entity_type="portfolio", entity_id=None, user_id=11,
                            user_scoped=True, payload={"bots": [{"bot_id": 3, "position_qty": "0.01"}]}),
        ]
        response = SimpleNamespace(content="private answer", proposal_id=None,
                                   confirmation_required=False, evidence=evidence)
        return SimpleNamespace(status="completed", response=response,
                               conversation_id=conv, policy=SimpleNamespace(execute_allowed=False))
    async def examined(**_kwargs):
        return {"result": "PASS", "failed_checks": []}
    monkeypatch.setattr(review_probe, "_chat_turn", chat)
    monkeypatch.setattr(probe, "examine_answer", examined)
    result = asyncio.run(probe._probe_turns(11, 3))
    assert calls == [None, "conversation-1", None]
    assert result["result"] == "PASS"
    assert result["fresh_conversations"] == 2
    assert "private" not in str(result)


def test_account_source_check_rejects_missing_or_foreign_evidence():
    facts = {
        "plan": {"setup_id": 1, "strategy_id": 2, "cadence": "daily", "base_amount_eur": "10"},
        "bot": {"id": 3, "active": True, "live": False},
        "position": {"quantity": "0.01"},
        "latest_decision": {"id": 4, "action": "hold", "at_utc": "2026-11-08T12:00:00Z"},
    }
    assert probe._source_checks([], facts, 11) == ["account_evidence_sources_missing"]
    evidence = [SimpleNamespace(entity_type=kind, entity_id=str(source_id),
                                user_id=12, user_scoped=True, payload={})
                for kind, source_id in (("setup", 1), ("strategy", 2),
                                        ("bot_status", 3), ("portfolio", None))]
    assert probe._source_checks(evidence, facts, 11) == ["account_evidence_owner_scope"]
    evidence = [SimpleNamespace(**{**item.__dict__, "user_id": 11}) for item in evidence]
    evidence.append(SimpleNamespace(entity_type="setup", entity_id="1", user_id=12,
                                    user_scoped=True, payload={}))
    assert probe._source_checks(evidence, facts, 11) == ["account_evidence_owner_scope"]
    evidence[-1].user_id = 11
    assert probe._source_checks(evidence, facts, 11) == ["account_evidence_sources_ambiguous"]
    evidence.pop()
    evidence.append(SimpleNamespace(entity_type="scores", entity_id=None, user_id=12,
                                    user_scoped=True, payload={}))
    assert probe._source_checks(evidence, facts, 11) == ["account_evidence_owner_scope"]
