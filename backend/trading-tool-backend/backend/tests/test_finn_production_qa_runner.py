from __future__ import annotations

import importlib.util
import json
import re
import socket
import ssl
import sys
import types
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[4]
SCRIPT_PATH = REPO_ROOT / "backend" / "trading-tool-backend" / "backend" / "scripts" / "run_finn_production_qa.py"
WORKFLOW_PATH = REPO_ROOT / ".github" / "workflows" / "finn-production-qa.yml"
DISPATCH_SCRIPT_PATH = REPO_ROOT / "ops" / "qa" / "run_finn_production_qa.sh"
CRYPTO_SCRIPT_PATH = REPO_ROOT / "ops" / "qa" / "finn_qa_manifest_bundle.py"


def _module():
    spec = importlib.util.spec_from_file_location("finn_production_qa_runner", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def test_workflow_is_manual_protected_and_serialized():
    workflow = WORKFLOW_PATH.read_text(encoding="utf-8")
    assert "workflow_dispatch:" in workflow
    trigger_block = workflow.split("permissions:", maxsplit=1)[0]
    assert re.search(r'^"on":\n  workflow_dispatch:', trigger_block, flags=re.MULTILINE)
    assert not re.search(r"^  (push|pull_request|schedule|workflow_run):", trigger_block, flags=re.MULTILINE)
    assert "environment: production" in workflow
    assert "finn-production-qa-${{ inputs.release_sha }}-${{ inputs.qa_profile }}" in workflow
    assert "persist-credentials: false" in workflow
    assert "actions/upload-artifact@" in workflow
    assert "QA_SSH_KNOWN_HOSTS" in workflow
    assert "StrictHostKeyChecking=yes" in workflow
    assert "manifest_key" in workflow
    assert "manifest_bundle" in workflow
    assert "allow_fixture_actions" in workflow
    assert "allow_safe_fixture_execution" in workflow
    assert "Safe fixture execution requires fixture-action authorization." in workflow
    assert "action_contract_acceptance" in workflow
    assert "timeout-minutes: 90" in workflow


def test_trade_review_preflight_reads_only_and_redacts_fixture_data(monkeypatch):
    module = _module()
    called = []
    def fake_request_json(*, url, token, timeout_seconds):
        called.append((url, token, timeout_seconds))
        if url.endswith("/trade-reviews?limit=1"):
            return 200, {"items": [{"id": 987, "note": "private journal"}],
                         "total": 1, "weekly": {}, "excluded": {}}, 12.5, None
        return 200, {"sources": [{"exchange_name": "private exchange"}]}, 8.0, None

    monkeypatch.setattr(module, "request_json", fake_request_json)
    report = module.trade_review_preflight(base_url="https://example.invalid", token="private-token")
    assert report["precondition_passed"] is True
    assert report["coverage"] == "authenticated_read_routes_only"
    assert len(called) == 3
    assert all(url.startswith("https://example.invalid/api/bot/") for url, _, _ in called)
    assert all(token == "private-token" for _, token, _ in called)
    assert "private journal" not in json.dumps(report)
    assert "private exchange" not in json.dumps(report)
    assert "987" not in json.dumps(report)
    assert "trade_review_preflight" in module.ALLOWED_PROFILES
    assert "trade_review_preflight" in WORKFLOW_PATH.read_text(encoding="utf-8")
    assert "trade_review_preflight" in DISPATCH_SCRIPT_PATH.read_text(encoding="utf-8")


def test_trade_review_preflight_rejects_disabled_rollout(monkeypatch):
    module = _module()
    def fake_request_json(*, url, token, timeout_seconds):
        if url.endswith("/trade-reviews?limit=1"):
            return 200, {"status": "disabled", "items": [], "total": 0,
                         "weekly": {}, "excluded": {}}, 1.0, None
        return 404, {}, 1.0, "server_http_response"

    monkeypatch.setattr(module, "request_json", fake_request_json)
    report = module.trade_review_preflight(base_url="https://example.invalid", token="fixture")
    assert report["precondition_passed"] is False
    assert report["checks"]["reviews"]["schema_valid"] is False
    assert report["checks"]["spot_sources"]["http_status"] == 404
    assert len(report["checks"]) == 3


def test_stale_score_paper_profile_is_explicitly_gated_and_owner_isolated(monkeypatch):
    module = _module()
    workflow = WORKFLOW_PATH.read_text(encoding="utf-8")
    probe_path = REPO_ROOT / "backend" / "trading-tool-backend" / "backend" / "scripts" / "probe_protected_score2_stale_paper.py"
    probe_source = probe_path.read_text(encoding="utf-8")
    spec = importlib.util.spec_from_file_location("protected_stale_probe", probe_path)
    probe = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(probe)

    assert "score2_stale_paper" in module.ALLOWED_PROFILES
    assert "score2_stale_paper" in workflow
    assert "FINN_QA_ALLOW_STALE_SCORE_FIXTURE=0" in workflow
    assert 'if [ "$qa_profile" = "score2_stale_paper" ]' in workflow
    assert '"$allow_fixture_actions" = "true"' in workflow
    assert '"$allow_safe_fixture_execution" = "true"' in workflow
    assert "INSERT INTO market_data\n" not in probe_source
    assert "VALUES (%s,%s,'user',FALSE,%s::jsonb)" in probe_source
    assert "min_benchmark_score,max_benchmark_score" in probe_source
    assert "min_macro_score,min_technical_score,min_market_score" not in probe_source
    dispatcher = (REPO_ROOT / "backend" / "trading-tool-backend" / "backend" / "celery_task" / "dispatcher.py").read_text(encoding="utf-8")
    assert "SELECT id FROM users WHERE is_active = true;" in dispatcher
    assert "run_trading_bot_agent(" in probe_source
    assert "bot_id=bot_id, paper_only=True" in probe_source
    monkeypatch.delenv("FINN_QA_ALLOW_STALE_SCORE_FIXTURE", raising=False)
    monkeypatch.setenv("FINN_QA_USER_ID", "42")
    with pytest.raises(RuntimeError, match="stale_fixture_not_authorized"):
        probe._require_protected_run("qa-123456-1-abcd1234-5678abcd")
    monkeypatch.setenv("FINN_QA_ALLOW_STALE_SCORE_FIXTURE", "1")
    assert probe._require_protected_run("qa-123456-1-abcd1234-5678abcd") == 42
    with pytest.raises(RuntimeError, match="stale_fixture_namespace_invalid"):
        probe._require_protected_run("../unsafe")


def test_auto_paper_history_profile_is_explicitly_gated_and_owner_isolated(monkeypatch):
    module = _module()
    workflow = WORKFLOW_PATH.read_text(encoding="utf-8")
    probe_path = REPO_ROOT / "backend" / "trading-tool-backend" / "backend" / "scripts" / "probe_protected_auto_paper_history.py"
    probe_source = probe_path.read_text(encoding="utf-8")
    spec = importlib.util.spec_from_file_location("protected_auto_paper_probe", probe_path)
    probe = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(probe)

    assert "auto_paper_trade_history" in module.ALLOWED_PROFILES
    assert "auto_paper_trade_history" in workflow
    dispatch = DISPATCH_SCRIPT_PATH.read_text(encoding="utf-8")
    assert "auto_paper_trade_history" in dispatch
    assert '"$manifest_id" != "none"' in dispatch
    assert '"$allow_safe_fixture_execution" != "true"' in dispatch
    assert "FINN_QA_ALLOW_AUTO_PAPER_HISTORY_FIXTURE=0" in workflow
    assert 'if [ "$qa_profile" = "auto_paper_trade_history" ]' in workflow
    assert "VALUES (%s,%s,'user',FALSE,%s::jsonb)" in probe_source
    assert "_auto_execute_decision(" in probe_source
    assert "get_account_bot_trades(user_id, 10, 0)" in probe_source
    assert "is_live=False, mode=\"auto\"" in probe_source
    monkeypatch.delenv("FINN_QA_ALLOW_AUTO_PAPER_HISTORY_FIXTURE", raising=False)
    monkeypatch.setenv("FINN_QA_USER_ID", "42")
    with pytest.raises(RuntimeError, match="auto_paper_fixture_not_authorized"):
        probe._require_protected_run("qa-123456-1-abcd1234-5678abcd")
    monkeypatch.setenv("FINN_QA_ALLOW_AUTO_PAPER_HISTORY_FIXTURE", "1")
    assert probe._require_protected_run("qa-123456-1-abcd1234-5678abcd") == 42
    with pytest.raises(RuntimeError, match="auto_paper_fixture_namespace_invalid"):
        probe._require_protected_run("../unsafe")


def test_protected_stale_paper_contract_identifies_the_failed_safety_boundary():
    path = REPO_ROOT / "backend" / "trading-tool-backend" / "backend" / "scripts" / "probe_protected_score2_stale_paper.py"
    spec = importlib.util.spec_from_file_location("protected_stale_probe_contract", path)
    probe = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(probe)
    valid = dict(
        action="hold", amount=0,
        payload={"setup_match": {"status": "insufficient_data"},
                 "dca_policy": {"source_available": False, "source_score": None}},
        orders=0, ledger=0, keys=0, owner_active=False,
        state=(100, True, False, "manual"),
    )
    probe._assert_stale_paper_contract(**valid)
    for change, error in (
        ({"action": "buy"}, "stale_paper_decision_not_hold_zero"),
        ({"payload": {"setup_match": {"status": "matches"}, "dca_policy": valid["payload"]["dca_policy"]}},
         "stale_paper_setup_match_not_insufficient"),
        ({"orders": 1}, "stale_paper_execution_side_effect"),
        ({"state": (99, True, False, "manual")}, "stale_paper_bot_state_changed"),
    ):
        with pytest.raises(RuntimeError, match=f"^{error}$"):
            probe._assert_stale_paper_contract(**(valid | change))


def test_protected_auto_paper_contract_reconciles_repriced_fill_and_history():
    path = REPO_ROOT / "backend" / "trading-tool-backend" / "backend" / "scripts" / "probe_protected_auto_paper_history.py"
    spec = importlib.util.spec_from_file_location("protected_auto_paper_probe_contract", path)
    probe = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(probe)
    # The EUR execution price can change after the €50 proposal is saved.
    quantity, price, spent = 0.00083333, 60000.0, 50.0
    valid = dict(
        rows=[("filled", "paper", "buy", spent, "filled", quantity, price, "executed", "auto")],
        portfolio=(50.0, quantity),
        ledger=[("paper_initial_funding", 100.0, 0), ("execute", -spent, quantity)],
        keys=0, owner_active=False, bot_id=12,
        items=[{"bot_id": 12, "environment": "paper", "execution_mode": "auto",
                "status": "filled", "side": "buy", "qty": quantity,
                "price": price, "amount_eur": spent}],
    )
    assert probe._assert_auto_paper_contract(**valid) == spent
    with pytest.raises(RuntimeError, match="^auto_paper_approved_spend_exceeded$"):
        probe._assert_auto_paper_contract(**(valid | {"rows": [
            ("filled", "paper", "buy", 51.0, "filled", 0.00085, price, "executed", "auto")]}))
    with pytest.raises(RuntimeError, match="^auto_paper_history_not_reconciled$"):
        probe._assert_auto_paper_contract(**(valid | {"items": [valid["items"][0] | {"amount_eur": 49.0}]}))


def test_local_positive_paper_probe_accepts_only_named_loopback_stacks(monkeypatch):
    path = REPO_ROOT / "backend" / "trading-tool-backend" / "backend" / "scripts" / "probe_local_score2_positive_paper.py"
    spec = importlib.util.spec_from_file_location("local_positive_paper_probe", path)
    probe = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(probe)
    source = path.read_text(encoding="utf-8")
    assert "min_benchmark_score,max_benchmark_score" in source
    for name, value in (
        ("APP_ENV", "local_finn"), ("DB_HOST", "127.0.0.1"),
        ("DB_NAME", "finn_local"), ("DB_PORT", "55440"),
        ("CELERY_BROKER_URL", "redis://127.0.0.1:56390/0"),
        ("CELERY_RESULT_BACKEND", "redis://127.0.0.1:56390/1"),
        ("FINN_LOCAL_PROBE_API_PORT", "18002"),
    ):
        monkeypatch.setenv(name, value)
    probe._assert_local_only()
    monkeypatch.setenv("FINN_LOCAL_PROBE_API_PORT", "18000")
    with pytest.raises(RuntimeError, match="local_only_environment_required:isolated_endpoints"):
        probe._assert_local_only()
    monkeypatch.setenv("FINN_LOCAL_PROBE_API_PORT", "18002")
    monkeypatch.setenv("DB_HOST", "tradamind.com")
    with pytest.raises(RuntimeError, match="local_only_environment_required:DB_HOST"):
        probe._assert_local_only()


def test_portfolio_paper_fx_profile_requires_explicit_authorization_and_real_sources(monkeypatch):
    from datetime import datetime, timedelta, timezone

    module = _module()
    workflow = WORKFLOW_PATH.read_text(encoding="utf-8")
    dispatch = DISPATCH_SCRIPT_PATH.read_text(encoding="utf-8")
    probe_path = (REPO_ROOT / "backend" / "trading-tool-backend" / "backend" /
                  "scripts" / "probe_protected_portfolio_paper_fx.py")
    spec = importlib.util.spec_from_file_location("protected_portfolio_paper_fx_probe", probe_path)
    probe = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(probe)

    assert "portfolio_paper_fx" in module.ALLOWED_PROFILES
    assert "portfolio_paper_fx" in workflow and "portfolio_paper_fx" in dispatch
    assert "FINN_QA_ALLOW_PORTFOLIO_PAPER_FX_FIXTURE=0" in workflow
    assert "export FINN_QA_ALLOW_PORTFOLIO_PAPER_FX_FIXTURE=$(printf '%q'" in workflow
    assert 'if [ "$qa_profile" = "portfolio_paper_fx" ]' in workflow
    monkeypatch.delenv("FINN_QA_ALLOW_PORTFOLIO_PAPER_FX_FIXTURE", raising=False)
    monkeypatch.setenv("FINN_QA_USER_ID", "42")
    with pytest.raises(RuntimeError, match="portfolio_paper_fx_fixture_not_authorized"):
        probe._require_protected_run("qa-123456-1-abcd1234-5678abcd")
    monkeypatch.setenv("FINN_QA_ALLOW_PORTFOLIO_PAPER_FX_FIXTURE", "1")
    assert probe._require_protected_run("qa-123456-1-abcd1234-5678abcd") == 42
    with pytest.raises(RuntimeError, match="portfolio_paper_fx_namespace_invalid"):
        probe._require_protected_run("../unsafe")

    class SourceCursor:
        def __init__(self, fx_time, *, diverging_projection=False):
            self.fx_time = fx_time
            self.diverging_projection = diverging_projection
            self.market_time = datetime.now(timezone.utc)
            self.rows = []

        def execute(self, query, _params):
            if "FROM market_data" in query:
                projected = "ORDER BY m.source_observed_at DESC" in query
                price = 2600 if projected and self.diverging_projection else 2500
                self.rows = (price, self.market_time, "USDT")
            else:
                self.rows = (0.8, self.fx_time)

        def fetchone(self):
            return self.rows

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

    class SourceConnection:
        def __init__(self, fx_time, **kwargs):
            self.cursor_value = SourceCursor(fx_time, **kwargs)

        def cursor(self):
            return self.cursor_value

        def close(self):
            pass

    now = datetime.now(timezone.utc)
    monkeypatch.setattr(probe, "_connection", lambda: SourceConnection(now))
    source = probe._verified_source_price_eur()
    assert source["eur_price"] == 2000.0
    assert source["raw_price"] == 2500.0
    assert source["fx_factor"] == 0.8
    assert source["quote"] == "USDT"
    monkeypatch.setattr(probe, "_connection", lambda: SourceConnection(now, diverging_projection=True))
    with pytest.raises(RuntimeError, match="portfolio_paper_fx_price_source_mismatch"):
        probe._verified_source_price_eur()
    monkeypatch.setattr(probe, "_connection", lambda: SourceConnection(now - timedelta(days=2)))
    with pytest.raises(RuntimeError, match="portfolio_paper_fx_source_unavailable"):
        probe._verified_source_price_eur()

    called = False

    def seed(*_args):
        nonlocal called
        called = True

    monkeypatch.setattr(probe, "_seed", seed)
    with pytest.raises(RuntimeError, match="portfolio_paper_fx_source_unavailable"):
        probe.run("qa-123456-1-abcd1234-5678abcd")
    assert called is False


def test_portfolio_paper_fx_attempt_is_reported_even_if_probe_fails():
    module = _module()
    report = {"safety": {"read_only_profile": True, "execution_calls": 0},
              "qa_status": "NOT_STARTED", "outcome": "failed"}

    def failed_probe(_namespace):
        raise RuntimeError("portfolio_paper_fx_execution_not_filled")

    with pytest.raises(RuntimeError, match="execution_not_filled"):
        module.run_protected_portfolio_probe(report, failed_probe, "qa-test")
    assert report["protected_profile_attempted"] is True
    assert report["qa_status"] == "INCOMPLETE"
    assert report["safety"]["read_only_profile"] is False
    assert report["safety"]["execution_calls"] == 1

    module.run_protected_portfolio_probe(report, lambda _: {"result": "PASS"}, "qa-test")
    assert report["qa_status"] == "COMPLETED"
    assert report["outcome"] == "passed"


def test_portfolio_paper_fx_fill_replay_projection_and_quarantine(monkeypatch):
    """Exercise the protected probe's run sequence without touching a real DB."""
    probe_path = (REPO_ROOT / "backend" / "trading-tool-backend" / "backend" /
                  "scripts" / "probe_protected_portfolio_paper_fx.py")
    spec = importlib.util.spec_from_file_location("protected_portfolio_fx_sequence", probe_path)
    probe = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(probe)
    source = {"eur_price": 2000.0, "raw_price": 2500.0, "fx_factor": 0.8,
              "quote": "USDT", "source_at": "source-time", "fx_at": "fx-time"}
    events = []
    monkeypatch.setattr(probe, "_require_protected_run", lambda _: 42)
    monkeypatch.setattr(probe, "_verified_source_price_eur", lambda: source)
    monkeypatch.setattr(probe, "_seed", lambda *_: (101, 202, 303))
    monkeypatch.setattr(probe, "_finish", lambda *args, **kwargs: events.append((args, kwargs)))

    class Connection:
        def commit(self):
            events.append("commit")

        def rollback(self):
            events.append("rollback")

        def close(self):
            events.append("close")

    monkeypatch.setattr(probe, "_connection", Connection)
    calls = []

    def execute(**kwargs):
        calls.append(kwargs)
        if len(calls) == 1:
            return "filled"
        raise RuntimeError("Decision already processing or executed")

    fake_agent = types.ModuleType("backend.ai_agents.trading_bot_agent")
    fake_agent._persist_bot_order = lambda **kwargs: events.append(("persist", kwargs["is_live"]))
    fake_agent._auto_execute_decision = execute
    monkeypatch.setitem(sys.modules, "backend.ai_agents.trading_bot_agent", fake_agent)
    monkeypatch.setattr(probe, "_verify", lambda *_: {"result": "PASS"})
    result = probe.run("qa-123456-1-abcd1234-5678abcd")
    assert result == {"result": "PASS"}
    assert len(calls) == 2
    assert all(call["is_live"] is False and call["mode"] == "auto" for call in calls)
    assert calls[0]["order"]["estimated_price"] == 1.0
    assert "rollback" in events
    assert events[-1][1]["passed"] is True

    events.clear()
    calls.clear()
    monkeypatch.setattr(probe, "_verify", lambda *_: (_ for _ in ()).throw(RuntimeError("verification_failed")))
    with pytest.raises(RuntimeError, match="verification_failed"):
        probe.run("qa-123456-1-abcd1234-5678abcd")
    assert events[-1][1]["passed"] is False


def test_portfolio_paper_fx_verifies_database_fill_and_shared_projection(monkeypatch):
    probe_path = (REPO_ROOT / "backend" / "trading-tool-backend" / "backend" /
                  "scripts" / "probe_protected_portfolio_paper_fx.py")
    spec = importlib.util.spec_from_file_location("protected_portfolio_fx_verification", probe_path)
    probe = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(probe)
    source = {"eur_price": 2000.0, "raw_price": 2500.0, "fx_factor": 0.8,
              "quote": "USDT", "source_at": "source-time", "fx_at": "fx-time"}
    monkeypatch.setattr(probe, "_verified_source_price_eur", lambda: source)

    class Cursor:
        def execute(self, sql, _params):
            self.sql = sql

        def fetchall(self):
            if "FROM bot_orders" in self.sql:
                return [("filled", "paper", 2000.0, 0.025, "filled", "executed", "auto")]
            if "FROM bot_ledger" in self.sql:
                return [("paper_initial_funding", 100.0, 0.0, None),
                        ("execute", -50.0, 0.025, 2)]
            raise AssertionError(self.sql)

        def fetchone(self):
            if "FROM bot_portfolios" in self.sql:
                return (50.0, 0.025)
            if "FROM exchange_keys" in self.sql:
                return (0,)
            if "FROM users" in self.sql:
                return (False,)
            raise AssertionError(self.sql)

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

    class Connection:
        def cursor(self):
            return Cursor()

        def close(self):
            pass

    monkeypatch.setattr(probe, "_connection", Connection)
    bot = types.SimpleNamespace(
        valuation_status="available", price_quote_currency="USDT",
        fx_as_of="fx-time", source_price_as_of="source-time",
        fx_eur_per_unit=0.8, cash_eur=50.0, position_value_eur=50.0,
        equity=100.0,
    )
    projected = {"data": types.SimpleNamespace(bots=[bot], valuation_status="available")}

    async def projection(_user_id):
        return projected

    monkeypatch.setattr(probe, "_projection", projection)
    result = probe._verify(101, 202, 303, source)
    assert result["result"] == "PASS"
    assert result["order_count"] == 1
    assert result["execution_ledger_entries"] == 1
    assert result["execution_environment"] == "paper"
    assert "live_trading_calls" not in result

    bot.fx_eur_per_unit = 0.9
    with pytest.raises(RuntimeError, match="portfolio_paper_fx_contract_failed"):
        probe._verify(101, 202, 303, source)


def test_workflow_has_only_the_manual_dispatch_trigger():
    """Official QA must never be started by a repository event."""
    workflow = WORKFLOW_PATH.read_text(encoding="utf-8")
    trigger_block = workflow.split("permissions:", maxsplit=1)[0]

    assert re.findall(r"^  ([A-Za-z_]+):", trigger_block, flags=re.MULTILINE) == ["workflow_dispatch"]


def test_workflow_never_exports_fixture_or_bearer_token():
    workflow = WORKFLOW_PATH.read_text(encoding="utf-8")
    assert "FINN_QA_USER_ID" not in workflow
    assert "FINN_QA_BEARER_TOKEN" not in workflow
    assert "authorization_header" not in workflow
    assert "set +x" in workflow


def test_transport_errors_have_typed_599_categories():
    module = _module()
    assert module.classify_transport_error(TimeoutError()) == "clienttimeout"
    assert module.classify_transport_error(socket.gaierror()) == "dns"
    assert module.classify_transport_error(ssl.SSLError()) == "tls"


def test_internal_runtime_diagnostic_never_exports_raw_exception_text():
    module = _module()
    assert module.classify_internal_issue('duplicate key value violates unique constraint "secret_name"') == "database_unique_constraint"
    assert module.classify_internal_issue("ValidationError: private details") == "validation"
    assert module.classify_internal_issue("unrecognized internal message") == "internal_unclassified"


def test_runtime_diagnostic_reuses_one_private_event_loop(monkeypatch):
    module = _module()
    module._DIAGNOSTIC_LOOP = None
    calls = []

    async def diagnostic(run_id):
        calls.append(run_id)
        return {"run_error_code": None, "orchestrator_issue_categories": []}

    monkeypatch.setattr(module, "_load_runtime_diagnostic", diagnostic)
    assert module.runtime_diagnostic("run-one")["orchestrator_issue_categories"] == []
    first_loop = module._DIAGNOSTIC_LOOP
    assert module.runtime_diagnostic("run-two")["orchestrator_issue_categories"] == []
    assert module._DIAGNOSTIC_LOOP is first_loop
    assert calls == ["run-one", "run-two"]


def test_bot_lineage_diagnostic_reuses_private_loop_and_hides_failure(monkeypatch):
    module = _module()
    module._DIAGNOSTIC_LOOP = None
    calls = []

    async def diagnostic(run_id, conversation_id):
        calls.append((run_id, conversation_id))
        if run_id == "missing":
            raise RuntimeError("private owner data")
        return {"parent_strategy_identity_present": True}

    monkeypatch.setattr(module, "_load_bot_lineage_diagnostic", diagnostic)
    assert module.bot_lineage_diagnostic("safe", "conversation") == {"parent_strategy_identity_present": True}
    first_loop = module._DIAGNOSTIC_LOOP
    assert module.bot_lineage_diagnostic("missing", "conversation") == {"diagnostic_status": "unavailable"}
    assert module._DIAGNOSTIC_LOOP is first_loop
    assert calls == [("safe", "conversation"), ("missing", "conversation")]


def test_bot_lineage_diagnostic_uses_snapshot_database_loop(monkeypatch):
    """asyncpg pooled connections cannot migrate between QA runner loops."""
    import asyncio

    module = _module()
    observed = []

    async def snapshot(*, operation_id, fixture_namespace):
        observed.append(asyncio.get_running_loop())
        return {"status": "available"}

    async def diagnostic(run_id, conversation_id):
        observed.append(asyncio.get_running_loop())
        return {"diagnostic_status": "available"}

    monkeypatch.setattr(module, "_load_owner_scoped_database_snapshot", snapshot)
    monkeypatch.setattr(module, "_load_bot_lineage_diagnostic", diagnostic)
    assert module.owner_scoped_database_snapshot(
        operation_id="create_setup", fixture_namespace="qa-shared-loop-test",
    )["status"] == "available"
    assert module.bot_lineage_diagnostic("run", "conversation")["diagnostic_status"] == "available"
    assert observed[0] is observed[1] is module._DATABASE_LOOP is module._DIAGNOSTIC_LOOP


def test_redaction_removes_credentials_and_fixture_identity():
    module = _module()
    report = module.redact({"access_token": "secret", "user_id": 7, "run_id": "safe", "nested": {"email": "x@example.test"}})
    assert report == {"access_token": "[REDACTED]", "user_id": "[REDACTED]", "run_id": "safe", "nested": {"email": "[REDACTED]"}}
    assert "secret" not in json.dumps(report)


def test_manifest_rejects_unsafe_fixture_actions_and_path_escape(monkeypatch, tmp_path):
    module = _module()
    manifest_dir = tmp_path / "manifests"
    manifest_dir.mkdir(parents=True)
    (manifest_dir / "unsafe.json").write_text(json.dumps({"cases": [{"case_id": "one", "message": "buy", "expected_operation_id": "manual_order", "fixture_action": "safe_execution"}]}), encoding="utf-8")
    monkeypatch.setenv("FINN_QA_ALLOW_FIXTURE_ACTIONS", "1")
    monkeypatch.setenv("FINN_QA_ALLOW_FIXTURE_EXECUTION", "1")
    with pytest.raises(ValueError, match="fixture_action_operation_blocked"):
        list(module.load_manifest(
            manifest_root=manifest_dir,
            manifest_id="unsafe",
            fixture_namespace="qa-34510823510-f8cbd9c1-a1b2c3d4",
        ))
    with pytest.raises(ValueError, match="manifest_id_invalid"):
        module.manifest_path(manifest_root=manifest_dir, manifest_id="../escape")


def test_manifest_allows_explicitly_authorized_safe_fixture_execution(monkeypatch, tmp_path):
    module = _module()
    manifest_dir = tmp_path / "manifests"
    manifest_dir.mkdir(parents=True)
    (manifest_dir / "safe.json").write_text(json.dumps({"cases": [{"case_id": "one", "message": "add BTC", "expected_operation_id": "watchlist_add", "fixture_action": "safe_execution", "idempotency_replay": True}]}), encoding="utf-8")
    monkeypatch.setenv("FINN_QA_ALLOW_FIXTURE_ACTIONS", "1")
    monkeypatch.setenv("FINN_QA_ALLOW_FIXTURE_EXECUTION", "1")
    assert list(module.load_manifest(
        manifest_root=manifest_dir,
        manifest_id="safe",
        fixture_namespace="qa-34510823510-f8cbd9c1-a1b2c3d4",
    ))[0]["fixture_action"] == "safe_execution"


def test_workflow_scopes_fixture_authorization_to_the_runner_subprocess():
    workflow = WORKFLOW_PATH.read_text(encoding="utf-8")
    assert "export FINN_QA_ALLOW_FIXTURE_ACTIONS=0" in workflow
    assert "export FINN_QA_ALLOW_FIXTURE_EXECUTION=0" in workflow
    assert "allow_fixture_actions=\"$9\"" in workflow
    assert "allow_safe_fixture_execution=\"${10}\"" in workflow
    assert "Create isolated fixture namespace" in workflow
    assert "FINN_QA_FIXTURE_NAMESPACE" in workflow
    assert "--fixture-namespace \"$fixture_namespace\"" in workflow


def test_workflow_serializes_protected_fixture_runs_across_reconnects_and_profiles():
    workflow = WORKFLOW_PATH.read_text(encoding="utf-8")
    runner = workflow.split('cat > "$state_dir/run.sh" <<RUNNER', 1)[1].split('\n          RUNNER', 1)[0]
    assert 'exec 9>>"\\$HOME/.finn-production-qa-fixture.lock"' in runner
    assert "flock -n -E 75 9" in runner
    assert runner.index("flock -n -E 75 9") < runner.index("PYTHONPATH=backend/trading-tool-backend python3")
    assert "runner_fixture_lock_unavailable" in runner
    assert 'if [ "$lock_status" = "runner_fixture_lock_unavailable" ]; then' in workflow
    assert 'workflow_attempt_id="${GITHUB_RUN_ID}-${GITHUB_RUN_ATTEMPT}"' in workflow
    assert 'remote_state_dir="/tmp/finn-production-qa-${workflow_attempt_id}"' in workflow
    assert 'name: finn-production-qa-${{ github.run_id }}-${{ github.run_attempt }}' in workflow
    assert 'runner.child.pid' in runner
    assert 'wait "\\$runner_child"' in runner


def test_workflow_runs_hashed_control_plane_runner_against_product_checkout():
    workflow = WORKFLOW_PATH.read_text(encoding="utf-8")
    assert "Checkout QA control plane" in workflow
    assert "path: .qa-control-plane" in workflow
    assert "control_plane_runner=\".qa-control-plane/backend/trading-tool-backend/backend/scripts/run_finn_production_qa.py\"" in workflow
    assert "runner_sha256=\"$(sha256sum \"$control_plane_runner\"" in workflow
    assert "test \"$(sha256sum \"$runner_path\"" in workflow
    assert "python3 $(printf '%q' \"$runner_path\")" in workflow
    assert "--runner-revision \"$runner_revision\"" in workflow
    assert "python3 backend/trading-tool-backend/backend/scripts/run_finn_production_qa.py" not in workflow


def test_workflow_runs_the_server_job_detached_and_resumes_from_checkpoint():
    workflow = WORKFLOW_PATH.read_text(encoding="utf-8")
    assert "remote_state_dir=\"/tmp/finn-production-qa-${workflow_attempt_id}\"" in workflow
    assert "nohup \"$state_dir/run.sh\"" in workflow
    assert "--resume >\"$state_dir/runner.log\"" in workflow
    assert "elif test -s '$remote_state_dir/runner.pid'" in workflow
    assert "elif test -s '$remote_state_dir/runner.child.pid'" in workflow
    assert "restarted=0" in workflow
    assert "honest partial checkpoint" in workflow
    assert "json.load(open(sys.argv[1]" in workflow
    assert "rm -f '$remote_state_dir/runner.exit'" in workflow
    assert 'runner_exit="$(ssh' in workflow
    assert 'test "$runner_exit" -eq 0' in workflow


def test_public_and_protected_matrix_paths_share_the_delivery_engine():
    protected = SCRIPT_PATH.read_text(encoding="utf-8")
    persisted = (
        REPO_ROOT / "backend" / "trading-tool-backend" / "backend" / "scripts"
        / "run_finn_v2_persisted_runtime_gate.py"
    ).read_text(encoding="utf-8")

    assert "from backend.scripts.finn_v2_matrix_transport import TERMINAL_STATUSES, observe_terminal" in protected
    assert "from backend.scripts.finn_v2_matrix_transport import TERMINAL_STATUSES, observe_terminal" in persisted
    assert "observe_terminal(" in protected
    assert "observe_terminal(" in persisted


def test_encrypted_manifest_is_only_staged_after_server_side_decryption(tmp_path):
    module = _module()
    private_key = tmp_path / "secrets" / "manifest.key"
    manifest = tmp_path / "sealed.json"
    manifest.write_text(json.dumps({"cases": [{"case_id": "one", "message": "Wat betekent RSI?"}]}), encoding="utf-8")
    public_key = module.manifest_public_key(crypto_script=CRYPTO_SCRIPT_PATH, private_key_path=private_key)
    bundle = tmp_path / "manifest.bundle"
    import subprocess
    subprocess.run(
        ["python3", str(CRYPTO_SCRIPT_PATH), "encrypt", f"--public-key={public_key}", "--manifest", str(manifest)],
        check=True,
        stdout=bundle.open("w", encoding="utf-8"),
    )
    root = tmp_path / "qa-manifests"
    staged = module.stage_manifest_bundle(
        crypto_script=CRYPTO_SCRIPT_PATH,
        private_key_path=private_key,
        bundle_path=bundle,
        manifest_root=root,
        manifest_id="qa-scope",
    )
    assert staged == root / "qa-scope.json"
    assert json.loads(staged.read_text(encoding="utf-8"))["cases"][0]["case_id"] == "one"
    assert oct(staged.stat().st_mode & 0o777) == "0o600"


def test_auth_preflight_does_not_persist_auth_payload(monkeypatch):
    module = _module()
    monkeypatch.setattr(module, "request_json", lambda **_kwargs: (200, {"email": "fixture@example.test", "id": 99}, 12.0, None))
    result = module.authenticated_preflight(base_url="https://example.test", token="never-persist")
    assert result == {"http_status": 200, "latency_ms": 12.0, "error_category": None, "fixture_authenticated": True, "attempt_count": 1}


def test_auth_preflight_retries_only_a_transient_read_failure(monkeypatch):
    module = _module()
    responses = iter([
        (599, {}, 10_000.0, "clienttimeout"),
        (200, {"id": 99}, 15.0, None),
    ])
    monkeypatch.setattr(module, "request_json", lambda **_kwargs: next(responses))
    monkeypatch.setattr(module.time, "sleep", lambda _seconds: None)

    result = module.authenticated_preflight(base_url="https://example.test", token="never-persist")

    assert result == {"http_status": 200, "latency_ms": 10015.0, "error_category": None, "fixture_authenticated": True, "attempt_count": 2}


def test_missing_fixture_binding_fails_without_invoking_the_issuer(monkeypatch, tmp_path):
    module = _module()
    monkeypatch.delenv("FINN_QA_USER_ID", raising=False)
    with pytest.raises(RuntimeError, match="fixture_binding_invalid"):
        module.issue_fixture_token(issuer=tmp_path / "issuer.py")


def test_release_identity_marks_any_sha_mismatch(monkeypatch, tmp_path):
    module = _module()

    class Completed:
        stdout = "a" * 40

    monkeypatch.setattr(module.subprocess, "run", lambda *_args, **_kwargs: Completed())
    monkeypatch.setattr(module, "request_json", lambda **_kwargs: (200, {"commit_sha": "b" * 40}, 1.0, None))
    marker = tmp_path / "LAST_GOOD_COMMIT"
    marker.write_text("a" * 40, encoding="utf-8")
    result = module.release_identity(release_sha="a" * 40, checkout=tmp_path, release_marker=marker, base_url="https://example.test")
    assert result["matches"] is False


def test_release_identity_accepts_nested_backend_build_sha(monkeypatch, tmp_path):
    module = _module()

    class Completed:
        stdout = "a" * 40

    responses = iter([
        (200, {"status": "ok", "build": {"commit_sha": "a" * 40}}, 1.0, None),
        (200, {"service": "frontend", "commit_sha": "a" * 40}, 1.0, None),
    ])
    monkeypatch.setattr(module.subprocess, "run", lambda *_args, **_kwargs: Completed())
    monkeypatch.setattr(module, "request_json", lambda **_kwargs: next(responses))
    marker = tmp_path / "LAST_GOOD_COMMIT"
    marker.write_text("a" * 40, encoding="utf-8")

    result = module.release_identity(release_sha="a" * 40, checkout=tmp_path, release_marker=marker, base_url="https://example.test")

    assert result["public_backend"]["sha"] == "a" * 40
    assert result["matches"] is True


def test_safe_projection_excludes_response_content_and_preserves_contract_metadata():
    module = _module()
    projection = module.safe_projection({
        "run_id": "run-1", "status": "completed", "mode": "READ",
        "response": {"mode": "READ", "content": "private response"},
        "runtime_trace": {
            "contract_id": "contract-1", "contract_revision": 4,
            "initial_operation_id": "capability", "final_operation_id": "capability",
            "dispatch_id": "dispatch-1", "dispatch_count": 1, "attempt_count": 1,
            "supplied_inputs": {"asset": "BTC"}, "missing_inputs": [],
            "required_inputs": ["asset"], "action_polarity": "add",
            "immediate_bot_pair_guard_reason": "unsupported_utterance",
            "private": "omit",
        },
    })
    assert projection["runtime_trace"]["initial_operation_id"] == "capability"
    assert projection["runtime_trace"]["contract_id"] == "contract-1"
    assert projection["runtime_trace"]["contract_revision"] == 4
    assert projection["runtime_trace"]["supplied_inputs"] == {"asset": "BTC"}
    assert projection["runtime_trace"]["required_inputs"] == ["asset"]
    assert projection["runtime_trace"]["action_polarity"] == "add"
    assert projection["runtime_trace"]["immediate_bot_pair_guard_reason"] == "unsupported_utterance"
    assert projection["runtime_trace"]["dispatch_count"] == 1
    assert "private response" not in json.dumps(projection)
    assert "private" not in projection["runtime_trace"]


def test_failed_terminal_is_a_product_failure_even_when_delivery_is_consistent():
    module = _module()
    assert module.classify_case_failure({
        "create_http_status": 200,
        "polling_sse_equal": True,
        "terminal": {"status": "failed"},
        "fixture_action": {"mode": "read_only"},
    }) == "product"


def test_runner_uses_gateway_created_conversation_for_follow_up(monkeypatch):
    module = _module()
    calls = []
    responses = iter([
        (200, {"run_id": "run-parent", "conversation_id": "conversation-live", "status": "pending"}, 1.0, None),
        (200, {"run_id": "run-parent", "conversation_id": "conversation-live", "status": "completed", "mode": "READ", "response": {}, "runtime_trace": {"initial_operation_id": "capability"}}, 1.0, None),
        (200, {"run_id": "run-child", "conversation_id": "conversation-live", "status": "pending"}, 1.0, None),
        (200, {"run_id": "run-child", "conversation_id": "conversation-live", "status": "completed", "mode": "READ", "response": {}, "runtime_trace": {"initial_operation_id": "explain_previous_evidence"}}, 1.0, None),
    ])

    def request(**kwargs):
        calls.append(kwargs)
        return next(responses)

    monkeypatch.setattr(module, "request_json", request)
    monkeypatch.setattr(module, "request_sse_terminal", lambda **kwargs: (
        {"run_id": "run-parent" if "run-parent" in kwargs["url"] else "run-child", "conversation_id": "conversation-live", "status": "completed", "mode": "READ", "response": {}, "runtime_trace": {"initial_operation_id": "capability" if "run-parent" in kwargs["url"] else "explain_previous_evidence"}},
        None,
    ))
    monkeypatch.setattr(module.time, "sleep", lambda _seconds: None)

    result = module.run_cases(base_url="https://example.test", token="token", cases=[
        {"case_id": "parent", "message": "Wat kan je?", "conversation_id": "logical-flow", "expected_operation_id": "capability"},
        {"case_id": "child", "message": "Waarom?", "conversation_id": "logical-flow", "expected_operation_id": "explain_previous_evidence"},
    ])

    create_calls = [call for call in calls if call.get("method") == "POST"]
    assert "conversation_id" not in create_calls[0]["payload"]
    assert create_calls[1]["payload"]["conversation_id"] == "conversation-live"
    assert result[1]["conversation_id"] == "conversation-live"


def test_runner_materializes_a_unique_natural_fixture_namespace_without_ids():
    module = _module()
    case = {
        "case_id": "setup",
        "message": "Maak een setup met de naam {{qa_run_namespace}}-setup.",
        "workspace_hints": {"label": "{{qa_run_namespace}}"},
    }

    materialized = module.materialize_fixture_namespace(case, namespace="qa-34454930988")

    assert materialized["message"] == "Maak een setup met de naam qa-34454930988-setup."
    assert materialized["workspace_hints"]["label"] == "qa-34454930988"
    assert case["message"].endswith("{{qa_run_namespace}}-setup.")
    assert "setup_id" not in json.dumps(materialized)


def test_runner_binds_new_bot_name_without_rewriting_linked_setup_reference():
    module = _module()
    message = (
        "Maak een nieuwe bot met de naam QA Paper Dagbot voor de strategie "
        "die gekoppeld is aan de bestaande DCA-setup met exacte naam "
        "QA DCA Setup qa-existing-123, met totaalbudget 20 EUR."
    )

    bound = module.bind_fixture_natural_name(message, namespace="qa-new-45678")

    assert "met de naam QA Paper Dagbot qa-new-45678 voor de strategie" in bound
    assert "met exacte naam QA DCA Setup qa-existing-123," in bound


@pytest.mark.parametrize("message", [
    "Maak een swingsetup met de naam Atlas, symbool XLM en timeframe 4H.",
    "Create a manual strategy from that setup and call it Atlas Plan.",
    "Erstelle einen Paper-Bot namens Atlas Bot.",
])
def test_runner_binds_declared_fixture_names_without_qa_instructions(message):
    module = _module()
    namespace = "qa-34746230528-f1e2d3c4"

    bound = module.bind_fixture_natural_name(message, namespace=namespace)

    assert namespace in bound
    assert "fixture namespace" not in bound.casefold()
    assert "setup_id" not in bound


def test_manifest_rejects_an_object_create_case_without_a_workflow_namespace(tmp_path, monkeypatch):
    module = _module()
    monkeypatch.setenv("FINN_QA_ALLOW_FIXTURE_ACTIONS", "1")
    monkeypatch.setenv("FINN_QA_ALLOW_FIXTURE_EXECUTION", "1")
    (tmp_path / "matrix.json").write_text(json.dumps({"cases": [{
        "case_id": "setup-create",
        "message": "Maak een setup met de naam vaste naam.",
        "fixture_action": "safe_execution",
        "expected_operation_id": "create_setup",
    }]}), encoding="utf-8")

    with pytest.raises(ValueError, match="fixture_namespace_required"):
        list(module.load_manifest(manifest_root=tmp_path, manifest_id="matrix"))


def test_sealed_manifest_without_token_accepts_a_runtime_namespace_and_stays_immutable(tmp_path, monkeypatch):
    module = _module()
    monkeypatch.setenv("FINN_QA_ALLOW_FIXTURE_ACTIONS", "1")
    monkeypatch.setenv("FINN_QA_ALLOW_FIXTURE_EXECUTION", "1")
    manifest = tmp_path / "matrix.json"
    manifest.write_text(json.dumps({"cases": [{
        "case_id": "setup-create",
        "message": "Maak een setup met de naam momentum.",
        "fixture_action": "safe_execution",
        "expected_operation_id": "create_setup",
    }]}), encoding="utf-8")
    before = module.sha256_file(manifest)

    cases = list(module.load_manifest(
        manifest_root=tmp_path,
        manifest_id="matrix",
        fixture_namespace="qa-34510823510-f8cbd9c1-a1b2c3d4",
    ))

    assert cases[0]["message"] == "Maak een setup met de naam momentum."
    assert module.sha256_file(manifest) == before


def test_fixture_preflight_recognizes_full_matrix_without_product_calls(tmp_path, monkeypatch):
    module = _module()
    monkeypatch.setenv("FINN_QA_ALLOW_FIXTURE_ACTIONS", "1")
    monkeypatch.setenv("FINN_QA_ALLOW_FIXTURE_EXECUTION", "1")
    operations = [
        "select_asset", "watchlist_add", "watchlist_remove",
        "create_indicator_configuration", "update_indicator_configuration", "delete_indicator_configuration",
        "create_setup", "update_setup", "create_strategy", "update_strategy",
        "create_bot", "update_bot", "deactivate_bot", "delete_bot", "delete_strategy", "delete_setup",
    ]
    cases = [
        {"case_id": f"write-{index}", "message": f"fixture {index}", "fixture_action": "safe_execution", "expected_operation_id": operation}
        for index, operation in enumerate(operations)
    ]
    cases.extend({"case_id": f"read-{index}", "message": "Lees status"} for index in range(21))
    manifest = tmp_path / "matrix.json"
    manifest.write_text(json.dumps({"cases": cases}), encoding="utf-8")
    base_hash = module.sha256_file(manifest)

    loaded = list(module.load_manifest(
        manifest_root=tmp_path,
        manifest_id="matrix",
        fixture_namespace="qa-34510823510-f8cbd9c1-a1b2c3d4",
    ))
    preflight = module.fixture_preflight(loaded, fixture_namespace="qa-34510823510-f8cbd9c1-a1b2c3d4")

    assert preflight == {
        "planned_cases": 37,
        "write_contracts_recognized": 16,
        "lineage_dependencies_recognized": 9,
        "fixture_namespace_present": True,
        "product_calls_executed": 0,
    }
    assert module.sha256_file(manifest) == base_hash


def _acceptance_cases(module):
    from backend.domain.finn_v2_operation_registry import FinnV2OperationRegistry

    write_operations = module.ACTION_CONTRACT_ACCEPTANCE_WRITE_OPERATIONS
    lineage_operations = module.LINEAGE_DEPENDENT_FIXTURE_OPERATIONS
    cases = []
    for index, contract in enumerate(FinnV2OperationRegistry().list()):
        cases.append({
            "case_id": f"acceptance-{index:02d}",
            "language": ("nl", "en", "de")[index % 3],
            "message": f"Independent acceptance question {index}",
            "expected_operation_id": contract.operation_id,
            "expected_action_polarity": contract.action_polarity.value,
            "expected_required_inputs": list(contract.required_inputs),
            "expected_supplied_inputs": [],
            "expected_missing_inputs": list(contract.required_inputs),
            "expected_canonical_target": None,
            "expected_target_type": None,
            "expected_target_source": None,
            "expected_terminal_statuses": ["completed"],
            "fixture_action": "safe_execution" if contract.operation_id in write_operations else "read_only",
            "idempotency_replay": contract.operation_id in write_operations,
            "lineage_dependency": contract.operation_id in lineage_operations,
        })
    non_lineage = [case for case in cases if not case["lineage_dependency"]]
    by_operation = {case["expected_operation_id"]: case for case in cases}
    return non_lineage + [by_operation[operation] for operation in module.NATURAL_LINEAGE_SEQUENCE]


def test_action_contract_acceptance_dry_preflight_requires_48_16_and_9():
    module = _module()
    result = module.action_contract_acceptance_preflight(
        _acceptance_cases(module), fixture_namespace="qa-acceptance-a1b2c3d4",
    )

    assert result["active_contracts_recognized"] == 48
    assert result["contract_cases_recognized"] == 48
    assert result["write_contracts_recognized"] == 16
    assert result["lineage_dependencies_recognized"] == 9
    assert result["product_calls_executed"] == 0
    assert result["workflow_dispatch_available"] is True
    assert set(result["acceptance_evidence_fields_supported"]) == module.ACCEPTANCE_EXPECTATION_FIELDS
    assert set(result["acceptance_report_fields_supported"]) == set(module.ACCEPTANCE_REPORT_EVIDENCE_FIELDS)


def test_action_contract_acceptance_rejects_incomplete_registry_coverage():
    module = _module()
    with pytest.raises(ValueError, match="acceptance_contract_count_invalid"):
        module.action_contract_acceptance_preflight(
            _acceptance_cases(module)[:-1], fixture_namespace="qa-acceptance-a1b2c3d4",
        )


def test_contract_expectations_are_scored_from_persisted_projection():
    module = _module()
    case = {
        "expected_operation_id": "select_asset",
        "expected_action_polarity": "update",
        "expected_required_inputs": ["asset"],
        "expected_supplied_inputs": ["asset"],
        "expected_missing_inputs": [],
        "expected_canonical_target": "SOL",
        "expected_target_type": None,
        "expected_target_source": "explicit_message",
        "expected_terminal_statuses": ["completed"],
    }
    evidence = module.contract_expectation_result(case, {
        "status": "completed",
        "runtime_trace": {
            "contract_id": "contract-1", "contract_revision": 3,
            "final_operation_id": "select_asset", "action_polarity": "update",
            "required_inputs": ["asset"], "supplied_inputs": {"asset": "SOL"},
            "missing_inputs": [], "canonical_target": "SOL", "target_type": None,
            "target_source": "explicit_message", "dispatch_count": 1, "attempt_count": 1,
        },
    })
    assert all(evidence.values())


def test_safe_write_captures_owner_database_effect_and_idempotent_replay(monkeypatch):
    module = _module()
    calls = []
    responses = iter([
        (200, {"proposal_id": "proposal-1", "status": "draft", "payload_hash": "hash", "confirmation_required": True}, 1.0, None),
        (200, {"confirmation_token": "secret", "payload_hash": "hash"}, 1.0, None),
        (200, {"status": "confirmed"}, 1.0, None),
        (200, {"execution_id": "execution-1", "proposal_id": "proposal-1", "operation_type": "create_setup", "status": "succeeded"}, 1.0, None),
        (200, {"execution_id": "execution-1", "proposal_id": "proposal-1", "operation_type": "create_setup", "status": "already_executed"}, 1.0, None),
    ])
    monkeypatch.setattr(module, "request_json", lambda **kwargs: (calls.append(kwargs) or next(responses)))
    snapshots = iter([
        {"owner_scoped": True, "row_count": 0, "state_sha256": "before", "owner_domain_state_sha256": "before-all", "broker_order_count": 0, "live_bot_count": 0},
        {"owner_scoped": True, "row_count": 0, "state_sha256": "before", "owner_domain_state_sha256": "before-all", "broker_order_count": 0, "live_bot_count": 0},
        {"owner_scoped": True, "row_count": 1, "state_sha256": "after", "owner_domain_state_sha256": "after-all", "broker_order_count": 0, "live_bot_count": 0, "entity_ids": [41]},
        {"owner_scoped": True, "row_count": 1, "state_sha256": "after", "owner_domain_state_sha256": "after-all", "broker_order_count": 0, "live_bot_count": 0, "entity_ids": [41]},
    ])
    monkeypatch.setattr(module, "owner_scoped_database_snapshot", lambda **_kwargs: next(snapshots))

    result = module._run_fixture_action(
        base_url="https://example.test", token="token",
        case={
            "fixture_action": "safe_execution", "expected_operation_id": "create_setup",
            "idempotency_replay": True,
            "client_context": {"fixture_namespace": "qa-acceptance-a1b2c3d4"},
        },
        terminal={"response": {"proposal_id": "proposal-1"}, "runtime_trace": {"contract_revision": 3}},
    )

    assert result["outcome"] == "executed"
    assert result["no_write_before_confirmation"] is True
    assert result["database_effect_observed"] is True
    assert result["idempotency_replay_execution_status"] == "already_executed"
    assert result["no_duplicate_effect"] is True
    assert result["safety_database_unchanged"] == {"broker_orders": True, "live_bots": True}
    assert result.get("error_category") is None


def test_fixture_write_during_proposal_stops_before_publish_or_confirmation(monkeypatch):
    module = _module()
    calls = []
    monkeypatch.setattr(module, "request_json", lambda **kwargs: (
        calls.append(kwargs) or (200, {
            "proposal_id": "proposal-1", "status": "draft", "payload_hash": "hash",
            "confirmation_required": True,
        }, 1.0, None)
    ))
    monkeypatch.setattr(module, "owner_scoped_database_snapshot", lambda **_kwargs: {
        "owner_scoped": True, "row_count": 1, "state_sha256": "after",
        "owner_domain_state_sha256": "after-all",
        "broker_order_count": 0, "live_bot_count": 0, "entity_ids": [41],
    })
    baseline = {
        "owner_scoped": True, "row_count": 0, "state_sha256": "before",
        "owner_domain_state_sha256": "before-all",
        "broker_order_count": 0, "live_bot_count": 0, "entity_ids": [],
    }

    result = module._run_fixture_action(
        base_url="https://example.test", token="token",
        case={
            "fixture_action": "safe_execution", "expected_operation_id": "create_setup",
            "client_context": {"fixture_namespace": "qa-acceptance-a1b2c3d4"},
        },
        terminal={"response": {"proposal_id": "proposal-1"}},
        database_before_run=baseline,
    )

    assert calls == []
    assert result["no_write_during_proposal"] is False
    assert result["error_category"] == "write_during_proposal"
    assert result["outcome"] == "proposal_write_detected"
    assert result["confirm_status"] is None
    assert result["execute_status"] is None


def test_matrix_stops_all_later_cases_after_protected_write_failure(monkeypatch):
    module = _module()
    requests = []
    terminal = {
        "run_id": "run-write", "conversation_id": "conversation-one",
        "status": "completed", "mode": "CREATE_PROPOSAL", "response": {},
        "runtime_trace": {"initial_operation_id": "create_setup", "final_operation_id": "create_setup"},
    }

    def request(**kwargs):
        requests.append(kwargs)
        return 200, terminal, 1.0, None

    monkeypatch.setattr(module, "request_json", request)
    monkeypatch.setattr(module, "request_sse_terminal", lambda **_kwargs: (terminal, None))
    monkeypatch.setattr(module, "owner_scoped_database_snapshot", lambda **_kwargs: {
        "status": "ok", "row_count": 0, "state_sha256": "before",
        "owner_domain_state_sha256": "before-all", "broker_order_count": 0,
        "live_bot_count": 0,
    })
    monkeypatch.setattr(module, "_run_fixture_action", lambda **_kwargs: {
        "mode": "safe_execution", "outcome": "proposal_write_detected",
        "error_category": "write_during_proposal",
    })
    cases = [
        {"case_id": "unsafe", "message": "Maak een setup met de naam QA Test.",
         "expected_operation_id": "create_setup", "fixture_action": "safe_execution"},
        {"case_id": "later-write", "message": "Maak een bot.",
         "expected_operation_id": "create_bot", "fixture_action": "safe_execution"},
        {"case_id": "later-read", "message": "Lees het plan."},
    ]
    checkpointed = []
    results = module.run_cases(
        base_url="https://example.test", token="token", cases=cases,
        fixture_namespace="qa-acceptance-a1b2c3d4",
        checkpoint=lambda rows, **_kwargs: checkpointed.append(list(rows)),
    )

    assert [item["case_status"] for item in results] == ["completed", "not_run", "not_run"]
    assert [item.get("error_category") for item in results[1:]] == [
        "prior_write_case_failed", "prior_write_case_failed",
    ]
    assert len([call for call in requests if call.get("method") == "POST"]) == 1
    assert checkpointed[-1] == results

    resumed = module.run_cases(
        base_url="https://example.test", token="token", cases=cases,
        fixture_namespace="qa-acceptance-a1b2c3d4", existing_results=results,
    )
    assert [item["case_status"] for item in resumed] == ["completed", "not_run", "not_run"]
    assert len([call for call in requests if call.get("method") == "POST"]) == 1


def test_owner_database_fingerprint_detects_write_outside_target_namespace():
    module = _module()
    baseline = {
        "row_count": 0, "state_sha256": "same-target", "owner_domain_state_sha256": "before-all",
        "broker_order_count": 0, "live_bot_count": 0,
    }
    after = {**baseline, "owner_domain_state_sha256": "after-all"}
    assert module.same_owner_database_state(baseline, after) is False


def test_missing_proposal_still_checks_for_preconfirmation_write(monkeypatch):
    module = _module()
    baseline = {
        "row_count": 0, "state_sha256": "before", "owner_domain_state_sha256": "before-all",
        "broker_order_count": 0, "live_bot_count": 0,
    }
    monkeypatch.setattr(module, "owner_scoped_database_snapshot", lambda **_kwargs: {
        **baseline, "owner_domain_state_sha256": "after-all",
    })
    monkeypatch.setattr(module, "request_json", lambda **_kwargs: pytest.fail("unexpected product request"))
    result = module._run_fixture_action(
        base_url="https://example.test", token="token",
        case={
            "fixture_action": "safe_execution", "expected_operation_id": "create_setup",
            "client_context": {"fixture_namespace": "qa-acceptance-a1b2c3d4"},
        },
        terminal={"runtime_trace": {}}, database_before_run=baseline,
    )
    assert result["error_category"] == "write_during_proposal"
    assert result["confirm_status"] is None


def test_publish_write_stops_before_confirmation(monkeypatch):
    module = _module()
    calls = []
    responses = iter([
        (200, {"proposal_id": "proposal-1", "status": "draft", "payload_hash": "hash"}, 1.0, None),
        (200, {"confirmation_token": "secret", "payload_hash": "hash"}, 1.0, None),
    ])
    monkeypatch.setattr(module, "request_json", lambda **kwargs: calls.append(kwargs) or next(responses))
    baseline = {
        "row_count": 0, "state_sha256": "before", "owner_domain_state_sha256": "before-all",
        "broker_order_count": 0, "live_bot_count": 0,
    }
    snapshots = iter([baseline, {**baseline, "owner_domain_state_sha256": "after-all"}])
    monkeypatch.setattr(module, "owner_scoped_database_snapshot", lambda **_kwargs: next(snapshots))
    result = module._run_fixture_action(
        base_url="https://example.test", token="token",
        case={
            "fixture_action": "safe_execution", "expected_operation_id": "create_setup",
            "client_context": {"fixture_namespace": "qa-acceptance-a1b2c3d4"},
        },
        terminal={"response": {"proposal_id": "proposal-1"}}, database_before_run=baseline,
    )
    assert len(calls) == 2
    assert result["error_category"] == "write_during_publish_or_database_evidence_unavailable"
    assert result["no_write_after_publish"] is False
    assert result["confirm_status"] is None


def test_interrupted_case_is_checkpointed_before_request_and_not_replayed(monkeypatch):
    module = _module()
    checkpoints = []

    def interrupted_request(**_kwargs):
        raise RuntimeError("simulated_runner_interruption")

    monkeypatch.setattr(module, "request_json", interrupted_request)
    cases = [{"case_id": "write-1", "message": "Maak een setup.", "fixture_action": "proposal"}]
    with pytest.raises(RuntimeError, match="simulated_runner_interruption"):
        module.run_cases(
            base_url="https://example.test", token="token", cases=cases,
            checkpoint=lambda rows, **_kwargs: checkpoints.append([dict(row) for row in rows]),
        )

    assert checkpoints[0][0]["case_status"] == "in_progress"
    assert module.case_progress(cases=checkpoints[0], planned_count=1)["incomplete"] is True
    resumed = module.run_cases(
        base_url="https://example.test", token="token", cases=cases,
        existing_results=checkpoints[0],
    )
    assert resumed == checkpoints[0]


def test_failed_run_create_still_checks_owner_database_effect(monkeypatch):
    module = _module()
    baseline = {
        "row_count": 0, "state_sha256": "before", "owner_domain_state_sha256": "before-all",
        "broker_order_count": 0, "live_bot_count": 0,
    }
    snapshots = iter([baseline, {**baseline, "owner_domain_state_sha256": "after-all"}])
    monkeypatch.setattr(module, "owner_scoped_database_snapshot", lambda **_kwargs: next(snapshots))
    monkeypatch.setattr(module, "request_json", lambda **_kwargs: (503, {}, 1.0, "server_http_response"))
    results = module.run_cases(
        base_url="https://example.test", token="token",
        cases=[{
            "case_id": "write-1", "message": "Maak een setup.",
            "fixture_action": "safe_execution", "expected_operation_id": "create_setup",
        }],
        fixture_namespace="qa-34510823510-f8cbd9c1-a1b2c3d4",
    )
    action = results[0]["fixture_action"]
    assert action["no_write_after_attempt"] is False
    assert action["error_category"] == "write_during_run"
    assert action["outcome"] == "run_write_detected"
    assert action.get("confirm_status") is None


def test_expired_fixture_action_still_checks_owner_database_effect(monkeypatch):
    from types import SimpleNamespace

    module = _module()
    baseline = {
        "row_count": 0, "state_sha256": "before", "owner_domain_state_sha256": "before-all",
        "broker_order_count": 0, "live_bot_count": 0,
    }
    snapshots = iter([baseline, {**baseline, "owner_domain_state_sha256": "after-all"}])
    monkeypatch.setattr(module, "owner_scoped_database_snapshot", lambda **_kwargs: next(snapshots))
    monkeypatch.setattr(module, "request_json", lambda **_kwargs: (
        200, {"run_id": "run-1", "conversation_id": "conversation-1"}, 1.0, None,
    ))
    terminal = {"status": "completed", "runtime_trace": {"initial_operation_id": "create_setup"}}
    monkeypatch.setattr(module, "observe_terminal", lambda **_kwargs: SimpleNamespace(
        terminal=terminal, sse_terminal=terminal, sse_error=None,
        fallback_poll_error=None, snapshot_error=None,
    ))
    monkeypatch.setattr(module, "_run_fixture_action", lambda **_kwargs: {
        "mode": "safe_execution", "outcome": "case_timeout", "error_category": "case_timeout",
    })
    results = module.run_cases(
        base_url="https://example.test", token="token",
        cases=[{
            "case_id": "write-1", "message": "Maak een setup.",
            "fixture_action": "safe_execution", "expected_operation_id": "create_setup",
        }],
        fixture_namespace="qa-34510823510-f8cbd9c1-a1b2c3d4",
    )
    assert results[0]["fixture_action"]["outcome"] == "run_write_detected"
    assert results[0]["fixture_action"]["error_category"] == "write_during_run"


def test_missing_namespace_is_blocked_before_any_product_call(tmp_path, monkeypatch):
    module = _module()
    monkeypatch.setenv("FINN_QA_ALLOW_FIXTURE_ACTIONS", "1")
    monkeypatch.setenv("FINN_QA_ALLOW_FIXTURE_EXECUTION", "1")
    (tmp_path / "matrix.json").write_text(json.dumps({"cases": [{
        "case_id": "setup-create", "message": "Maak setup.",
        "fixture_action": "safe_execution", "expected_operation_id": "create_setup",
    }]}), encoding="utf-8")
    report = tmp_path / "report.json"
    monkeypatch.setattr(module, "parse_args", lambda: type("Args", (), {
        "release_sha": "a" * 40, "profile": "full_release_acceptance", "manifest_id": "matrix",
        "run_label": "blocked-preflight", "base_url": "https://example.test", "checkout": str(tmp_path),
        "release_marker": str(tmp_path / "marker"), "manifest_root": str(tmp_path),
        "manifest_bundle_path": None, "manifest_private_key_path": str(tmp_path / "key"),
        "manifest_crypto_script": None, "report_path": str(report), "workflow_run_id": "34510823510",
        "fixture_namespace": None, "dry_preflight": True,
    })())
    monkeypatch.setattr(module, "request_json", lambda **_kwargs: pytest.fail("product call"))

    assert module.main() == 1
    payload = json.loads(report.read_text(encoding="utf-8"))
    assert payload["outcome"] == "blocked"
    assert payload["qa_status"] == "QA BLOCKED / NOT STARTED"
    assert payload["planned_count"] == 1
    assert payload["cases"] == []


def test_all_downstream_fixture_cases_receive_the_same_execution_namespace():
    module = _module()
    namespace = "qa-34510823510-f8cbd9c1-a1b2c3d4"
    create = module.materialize_fixture_namespace({
        "case_id": "create", "message": "Maak een setup.", "fixture_action": "safe_execution",
        "expected_operation_id": "create_setup",
    }, namespace=namespace)
    downstream = module.materialize_fixture_namespace({
        "case_id": "update", "message": "Wijzig die setup.", "fixture_action": "safe_execution",
        "expected_operation_id": "update_setup",
    }, namespace=namespace)

    assert create["client_context"]["fixture_namespace"] == namespace
    assert "fixture_name_suffix" not in create["client_context"]
    assert namespace not in create["message"]
    assert downstream["client_context"]["fixture_namespace"] == namespace
    assert downstream["client_context"]["fixture_lineage_namespace"] == namespace
    assert namespace not in downstream["message"]
    assert "setup_id" not in json.dumps(create)


def test_distinct_workflow_namespaces_are_not_interchangeable():
    module = _module()
    first = module.materialize_fixture_namespace(
        {"case_id": "one", "message": "Maak setup.", "fixture_action": "safe_execution", "expected_operation_id": "create_setup"},
        namespace="qa-34510823510-f8cbd9c1-a1b2c3d4",
    )
    second = module.materialize_fixture_namespace(
        {"case_id": "two", "message": "Maak setup.", "fixture_action": "safe_execution", "expected_operation_id": "create_setup"},
        namespace="qa-34510823511-f8cbd9c1-e5f6a7b8",
    )

    assert first["client_context"]["fixture_namespace"] != second["client_context"]["fixture_namespace"]


def test_fixture_confirmation_includes_required_idempotency_key(monkeypatch):
    module = _module()
    calls = []
    responses = iter([
        (200, {"proposal_id": "proposal-1", "status": "pending", "proposal_version": "v1", "payload_hash": "hash", "confirmation_required": True}, 1.0, None),
        (200, {"confirmation_token": "secret", "payload_hash": "hash"}, 1.0, None),
        (200, {"status": "succeeded"}, 1.0, None),
    ])
    monkeypatch.setattr(module, "request_json", lambda **kwargs: (calls.append(kwargs) or next(responses)))
    result = module._run_fixture_action(
        base_url="https://example.test", token="token",
        case={"fixture_action": "confirmation"},
        terminal={"response": {"proposal_id": "proposal-1"}, "runtime_trace": {"contract_revision": 3}},
    )
    confirm_call = calls[2]
    assert result["confirm_status"] == 200
    assert result["proposal"]["contract_revision"] == 3
    assert confirm_call["payload"]["idempotency_key"].startswith("qa-confirm-")
    assert "secret" not in json.dumps(result)


def test_fixture_execution_requires_a_successful_terminal_execution_status(monkeypatch):
    module = _module()
    responses = iter([
        (200, {"proposal_id": "proposal-1", "status": "pending", "payload_hash": "hash", "confirmation_required": True}, 1.0, None),
        (200, {"confirmation_token": "secret", "payload_hash": "hash"}, 1.0, None),
        (200, {}, 1.0, None),
        (200, {"status": "blocked"}, 1.0, None),
    ])
    monkeypatch.setattr(module, "request_json", lambda **_kwargs: next(responses))

    result = module._run_fixture_action(
        base_url="https://example.test", token="token", case={"fixture_action": "safe_execution"},
        terminal={"response": {"proposal_id": "proposal-1"}, "runtime_trace": {}},
    )

    assert result["execute_status"] == 200
    assert result["execution_status"] == "blocked"
    assert result["error_category"] == "proposal_execute_failed"


def test_incomplete_action_is_a_typed_contract_outcome_not_proposal_missing():
    module = _module()
    result = module._run_fixture_action(
        base_url="https://example.test", token="token",
        case={"fixture_action": "proposal", "expected_missing_inputs": ["name", "timeframe"]},
        terminal={"runtime_trace": {"missing_inputs": ["timeframe", "name"]}},
    )

    assert result == {
        "mode": "proposal", "proposal": {}, "publish_status": None, "confirm_status": None,
        "execute_status": None, "idempotency_replay_status": None, "outcome": "missing_inputs",
        "missing_inputs": ["timeframe", "name"],
    }


def test_case_content_failure_is_reported_without_runner_failure(monkeypatch, tmp_path):
    module = _module()
    monkeypatch.setattr(module, "release_identity", lambda **_kwargs: {"matches": True})
    monkeypatch.setattr(module, "issue_fixture_token", lambda **_kwargs: "token")
    monkeypatch.setattr(module, "authenticated_preflight", lambda **_kwargs: {"fixture_authenticated": True})
    monkeypatch.setattr(module, "sha256_file", lambda _path: "a" * 64)
    monkeypatch.setattr(module, "manifest_path", lambda **_kwargs: tmp_path / "manifest.json")
    monkeypatch.setattr(module, "manifest_cases", lambda _path: [{"case_id": "case", "message": "x"}])
    monkeypatch.setattr(module, "load_manifest", lambda **_kwargs: [{"case_id": "case", "message": "x"}])
    monkeypatch.setattr(module, "run_cases", lambda **_kwargs: [{"case_id": "case", "create_http_status": 200, "terminal": {"status": "completed"}, "polling_sse_equal": True, "operation_matches": False, "fixture_action": {"mode": "read_only"}}])
    report = tmp_path / "report.json"
    monkeypatch.setattr(module, "parse_args", lambda: type("Args", (), {
        "release_sha": "a" * 40, "profile": "targeted_regression", "manifest_id": "scope", "run_label": "run", "base_url": "https://example.test", "checkout": str(tmp_path), "release_marker": str(tmp_path / "marker"), "manifest_root": str(tmp_path), "manifest_bundle_path": None, "manifest_private_key_path": str(tmp_path / "key"), "manifest_crypto_script": None, "report_path": str(report), "workflow_run_id": "local",
    })())

    assert module.main() == 0
    payload = json.loads(report.read_text(encoding="utf-8"))
    assert payload["outcome"] == "failed"
    assert payload["error_category"] is None


def test_case_failure_categories_do_not_count_transport_as_selector_failures():
    module = _module()
    cases = [
        {"error_category": "clienttimeout", "fixture_action": {}},
        {"create_http_status": 200, "terminal": {"status": "completed"}, "polling_sse_equal": True, "operation_matches": False, "fixture_action": {}},
        {"create_http_status": 200, "terminal": {"status": "completed"}, "polling_sse_equal": True, "operation_matches": True, "fixture_action": {"error_category": "proposal_missing"}},
    ]

    assert [module.classify_case_failure(case) for case in cases] == ["infrastructure", "product", "product"]
    assert module.failure_summary(cases) == {"product": 2, "runner": 0, "infrastructure": 1}


def test_case_timeout_is_checkpointed_and_does_not_block_the_next_case(monkeypatch):
    module = _module()
    original_sleep = module.time.sleep
    calls = []
    responses = iter([
        (200, {"run_id": "slow", "conversation_id": "c1", "status": "pending"}, 1.0, None),
        (200, {"run_id": "slow", "conversation_id": "c1", "status": "pending"}, 1.0, None),
        (200, {"run_id": "slow", "conversation_id": "c1", "status": "canceled"}, 1.0, None),
        (200, {"run_id": "slow", "conversation_id": "c1", "status": "canceled"}, 1.0, None),
        (200, {"run_id": "fast", "conversation_id": "c2", "status": "pending"}, 1.0, None),
        (200, {"run_id": "fast", "conversation_id": "c2", "status": "completed", "runtime_trace": {"initial_operation_id": "capability"}}, 1.0, None),
    ])
    monkeypatch.setattr(module, "request_json", lambda **kwargs: (calls.append(kwargs) or next(responses)))
    monkeypatch.setattr(module.time, "sleep", lambda _seconds: original_sleep(0.01))
    def slow_sse(**_kwargs):
        original_sleep(0.01)
        return {"status": "completed", "runtime_trace": {"initial_operation_id": "capability"}}, None

    monkeypatch.setattr(module, "request_sse_terminal", slow_sse)
    checkpoints = []
    results = module.run_cases(base_url="https://example.test", token="token", case_timeout_seconds=0.005, checkpoint=lambda rows, **_kwargs: checkpoints.append(list(rows)), cases=[
        {"case_id": "slow", "message": "slow"},
        {"case_id": "fast", "message": "fast", "expected_operation_id": "capability"},
    ])
    assert results[0]["error_category"] == "case_timeout"
    assert results[0]["timeout_cleanup"]["cancel_http_status"] == 200
    assert results[0]["timeout_cleanup"]["server_active_after_cleanup"] is False
    assert results[1]["run_id"] == "fast"
    assert len(checkpoints) == 4
    assert checkpoints[0][0]["case_status"] == "in_progress"
    assert checkpoints[-1][1]["case_status"] == "completed"


def test_resume_replaces_not_run_placeholders_without_duplicate_cases(monkeypatch):
    module = _module()
    created = []

    def request(**kwargs):
        if kwargs.get("method") == "POST":
            case_id = str(kwargs["payload"]["message"])
            created.append(case_id)
            return 200, {"run_id": f"run-{case_id}", "conversation_id": "conversation", "status": "pending"}, 1.0, None
        run_id = str(kwargs["url"]).rsplit("/", 1)[-1]
        return 200, {"run_id": run_id, "conversation_id": "conversation", "status": "completed", "runtime_trace": {"initial_operation_id": "capability"}}, 1.0, None

    monkeypatch.setattr(module, "request_json", request)
    monkeypatch.setattr(module, "request_sse_terminal", lambda **kwargs: ({
        "run_id": str(kwargs["url"]).rsplit("/", 2)[-2], "conversation_id": "conversation",
        "status": "completed", "runtime_trace": {"initial_operation_id": "capability"},
    }, None))
    cases = [
        {"case_id": "done", "message": "done", "expected_operation_id": "capability"},
        {"case_id": "resume", "message": "resume", "expected_operation_id": "capability"},
    ]
    resumed = module.run_cases(
        base_url="https://example.test",
        token="token",
        cases=cases,
        existing_results=[
            {"case_id": "done", "case_status": "completed", "create_http_status": 200},
            {"case_id": "resume", "case_status": "not_run", "error_category": "runner_interrupted"},
        ],
    )

    assert [item["case_id"] for item in resumed] == ["done", "resume"]
    assert created == ["resume"]
    assert module.case_progress(cases=resumed, planned_count=2)["incomplete"] is False


def test_terminal_sse_uses_one_persisted_snapshot_without_a_polling_loop(monkeypatch):
    module = _module()
    calls = []

    def request(**kwargs):
        calls.append(kwargs)
        if kwargs.get("method") == "POST":
            return 200, {"run_id": "run-1", "conversation_id": "conversation-1", "status": "created"}, 1.0, None
        return 200, {
            "run_id": "run-1", "conversation_id": "conversation-1", "status": "completed",
            "runtime_trace": {"initial_operation_id": "capability"},
        }, 1.0, None

    monkeypatch.setattr(module, "request_json", request)
    monkeypatch.setattr(module, "request_sse_terminal", lambda **_kwargs: ({
        "run_id": "run-1", "conversation_id": "conversation-1", "status": "completed",
        "runtime_trace": {"initial_operation_id": "capability"},
    }, None))

    result = module.run_cases(
        base_url="https://example.test",
        token="token",
        cases=[{"case_id": "case", "message": "What can you do?", "expected_operation_id": "capability"}],
    )

    assert result[0]["polling_sse_equal"] is True
    assert len(calls) == 2  # create + one persisted projection snapshot
    assert calls[1].get("method", "GET") == "GET"


def test_checkpoint_with_executed_cases_never_reports_not_started(monkeypatch, tmp_path):
    module = _module()
    report = tmp_path / "report.json"
    args = type("Args", (), {
        "release_sha": "a" * 40, "profile": "targeted_regression", "manifest_id": "scope",
        "run_label": "run", "base_url": "https://example.test", "checkout": str(tmp_path),
        "release_marker": str(tmp_path / "marker"), "manifest_root": str(tmp_path),
        "manifest_bundle_path": None, "manifest_private_key_path": str(tmp_path / "key"),
        "manifest_crypto_script": None, "report_path": str(report), "workflow_run_id": "workflow",
        "fixture_namespace": "qa-12345678", "runner_revision": None,
        "matrix_deadline_seconds": 60.0, "case_timeout_seconds": 60.0, "resume": False,
        "dry_preflight": False,
    })()
    monkeypatch.setattr(module, "parse_args", lambda: args)
    monkeypatch.setattr(module, "release_identity", lambda **_kwargs: {"matches": True})
    monkeypatch.setattr(module, "issue_fixture_token", lambda **_kwargs: "token")
    monkeypatch.setattr(module, "authenticated_preflight", lambda **_kwargs: {"fixture_authenticated": True})
    manifest = tmp_path / "scope.json"
    manifest.write_text(json.dumps({"cases": [{"case_id": "one", "message": "x"}]}), encoding="utf-8")
    monkeypatch.setattr(module, "run_cases", lambda **kwargs: (
        kwargs["checkpoint"]([{
            "case_id": "one", "case_status": "completed", "create_http_status": 200,
            "terminal": {"status": "completed"}, "polling_sse_equal": True,
            "operation_matches": True, "fixture_action": {"mode": "read_only"},
        }], planned_count=1) or (_ for _ in ()).throw(RuntimeError("simulated_crash"))
    ))

    assert module.main() == 0
    payload = json.loads(report.read_text(encoding="utf-8"))
    assert payload["qa_status"] == "COMPLETED_WITH_FAILURES"
    assert payload["attempted_count"] == 1


def test_timeout_checkpoint_is_a_valid_partial_artifact(tmp_path):
    report = tmp_path / "report.json"
    payload = {"schema_version": 1, "cases": [{"case_id": "slow", "error_category": "case_timeout"}], "incomplete": True}
    temporary = report.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(payload), encoding="utf-8")
    temporary.replace(report)
    assert json.loads(report.read_text(encoding="utf-8")) == payload


def test_final_runner_report_uses_the_same_atomic_publish_path(tmp_path):
    module = _module()
    report = tmp_path / "report.json"
    module.write_report_atomic(report, {"cases": [{"case_id": "one"}], "incomplete": False})

    assert json.loads(report.read_text(encoding="utf-8"))["cases"] == [{"case_id": "one"}]
    assert not report.with_suffix(".json.tmp").exists()


def test_matrix_deadline_marks_each_unattempted_case_and_preserves_prior_failure(monkeypatch):
    module = _module()
    clock_calls = 0

    def monotonic():
        nonlocal clock_calls
        clock_calls += 1
        return 0.0 if clock_calls <= 3 else 2.0

    monkeypatch.setattr(module.time, "monotonic", monotonic)
    monkeypatch.setattr(module, "request_json", lambda **_kwargs: (500, {}, 1.0, "server_http_response"))
    checkpoints = []

    results = module.run_cases(
        base_url="https://example.test",
        token="token",
        matrix_deadline_seconds=1.0,
        cases=[
            {"case_id": "executed", "message": "first"},
            {"case_id": "not-run-1", "message": "second"},
            {"case_id": "not-run-2", "message": "third"},
            {"case_id": "not-run-3", "message": "fourth"},
            {"case_id": "not-run-4", "message": "fifth"},
            {"case_id": "not-run-5", "message": "sixth"},
        ],
        checkpoint=lambda rows, **kwargs: checkpoints.append((list(rows), kwargs)),
    )

    assert [item["case_id"] for item in results] == ["executed", "not-run-1", "not-run-2", "not-run-3", "not-run-4", "not-run-5"]
    assert all(item["case_status"] == "not_run" for item in results[1:])
    progress = module.case_progress(cases=results, planned_count=6)
    assert progress == {
        "planned_count": 6,
        "attempted_count": 1,
        "completed_count": 1,
        "failed_count": 1,
        "not_run_count": 5,
        "incomplete": True,
    }
    assert checkpoints[-1][1]["planned_count"] == 6


def test_broken_transport_after_a_checkpoint_resumes_a_37_case_matrix_without_duplicate_runs(monkeypatch, tmp_path):
    """A detached server runner can resume the same matrix after SSH drops."""
    module = _module()
    created_case_ids = []
    active_case_ids = []

    def request(**kwargs):
        if kwargs.get("method") == "POST":
            case_id = str(kwargs["payload"]["message"])
            active_case_ids.append(case_id)
            created_case_ids.append(case_id)
            return 200, {
                "run_id": f"run-{case_id}",
                "conversation_id": f"conversation-{case_id}",
                "status": "pending",
            }, 1.0, None
        run_id = str(kwargs["url"]).rsplit("/", 1)[-1]
        return 200, {
            "run_id": run_id,
            "conversation_id": f"conversation-{run_id}",
            "status": "completed",
            "runtime_trace": {"initial_operation_id": "capability"},
        }, 1.0, None

    monkeypatch.setattr(module, "request_json", request)
    def sse(**kwargs):
        run_id = str(kwargs["url"]).rsplit("/", 2)[-2]
        return {
            "run_id": run_id,
            "conversation_id": f"conversation-{run_id.removeprefix('run-')}",
            "status": "completed",
            "runtime_trace": {"initial_operation_id": "capability"},
        }, None

    monkeypatch.setattr(module, "request_sse_terminal", sse)
    monkeypatch.setattr(module.time, "sleep", lambda _seconds: None)
    cases = [
        {"case_id": f"case-{index:02d}", "message": f"case-{index:02d}", "expected_operation_id": "capability"}
        for index in range(37)
    ]
    checkpoint_path = tmp_path / "checkpoint.json"
    snapshots = []

    def interrupted_checkpoint(rows, **_kwargs):
        snapshot = [dict(row) for row in rows]
        snapshots.append(snapshot)
        checkpoint_path.write_text(json.dumps({"cases": snapshot}), encoding="utf-8")
        if len(snapshot) == 18:
            raise BrokenPipeError("simulated_ssh_broken_pipe")

    with pytest.raises(BrokenPipeError, match="simulated_ssh_broken_pipe"):
        module.run_cases(
            base_url="https://example.test",
            token="token",
            cases=cases,
            checkpoint=interrupted_checkpoint,
        )

    persisted = json.loads(checkpoint_path.read_text(encoding="utf-8"))["cases"]
    assert len(persisted) == 18
    assert len(created_case_ids) == 17
    assert persisted[-1]["case_status"] == "in_progress"

    def final_checkpoint(rows, **_kwargs):
        checkpoint_path.write_text(json.dumps({"cases": rows}), encoding="utf-8")

    resumed = module.run_cases(
        base_url="https://example.test",
        token="token",
        cases=cases,
        checkpoint=final_checkpoint,
        existing_results=persisted,
    )

    assert len(resumed) == 37
    assert {item["case_id"] for item in resumed} == {case["case_id"] for case in cases}
    assert len(created_case_ids) == 36
    assert len(set(created_case_ids)) == 36
    assert resumed[17]["case_status"] == "in_progress"
    assert all(item["case_status"] == "completed" for item in resumed if item["case_id"] != "case-17")
    assert module.case_progress(cases=resumed, planned_count=37)["incomplete"] is True


def test_runner_crash_after_case_thirty_two_resumes_without_duplicate_cases(monkeypatch, tmp_path):
    """The checkpoint preceding a runner crash is enough for one safe resume."""
    module = _module()
    created = []

    def request(**kwargs):
        if kwargs.get("method") == "POST":
            case_id = str(kwargs["payload"]["message"])
            created.append(case_id)
            return 200, {"run_id": f"run-{case_id}", "conversation_id": f"conversation-{case_id}", "status": "pending"}, 1.0, None
        run_id = str(kwargs["url"]).rsplit("/", 1)[-1]
        return 200, {"run_id": run_id, "status": "completed", "runtime_trace": {"initial_operation_id": "capability"}}, 1.0, None

    monkeypatch.setattr(module, "request_json", request)
    monkeypatch.setattr(module, "request_sse_terminal", lambda **kwargs: ({
        "run_id": str(kwargs["url"]).rsplit("/", 2)[-2], "status": "completed",
        "runtime_trace": {"initial_operation_id": "capability"},
    }, None))
    cases = [{"case_id": f"case-{index:02d}", "message": f"case-{index:02d}", "expected_operation_id": "capability"} for index in range(37)]
    checkpoint_path = tmp_path / "checkpoint.json"

    def crash_after_thirty_two(rows, **_kwargs):
        checkpoint_path.write_text(json.dumps({"cases": rows}), encoding="utf-8")
        if len(rows) == 32:
            raise RuntimeError("simulated_runner_crash_after_q32")

    with pytest.raises(RuntimeError, match="simulated_runner_crash_after_q32"):
        module.run_cases(base_url="https://example.test", token="token", cases=cases, checkpoint=crash_after_thirty_two)

    checkpointed = json.loads(checkpoint_path.read_text(encoding="utf-8"))["cases"]
    assert len(checkpointed) == 32
    assert module.case_progress(cases=checkpointed, planned_count=37)["incomplete"] is True

    resumed = module.run_cases(base_url="https://example.test", token="token", cases=cases, existing_results=checkpointed)
    assert len(resumed) == 37
    assert len(created) == 36
    assert len(set(created)) == 36
    assert resumed[31]["case_status"] == "in_progress"
    assert module.case_progress(cases=resumed, planned_count=37)["incomplete"] is True


def test_case_progress_marks_thirty_two_of_thirty_seven_as_incomplete():
    module = _module()
    cases = [
        {"case_id": f"done-{index}", "case_status": "completed", "create_http_status": 200,
         "terminal": {"status": "completed"}, "polling_sse_equal": True,
         "operation_matches": True, "fixture_action": {}}
        for index in range(32)
    ]
    cases.extend({"case_id": f"not-run-{index}", "case_status": "not_run", "error_category": "matrix_deadline"} for index in range(5))

    progress = module.case_progress(cases=cases, planned_count=37)

    assert progress["attempted_count"] == 32
    assert progress["completed_count"] == 32
    assert progress["not_run_count"] == 5
    assert progress["incomplete"] is True


def test_resume_skips_checkpointed_cases_and_restores_their_conversation(monkeypatch):
    module = _module()
    calls = []
    responses = iter([
        (200, {"run_id": "run-child", "conversation_id": "conversation-live", "status": "pending"}, 1.0, None),
        (200, {"run_id": "run-child", "conversation_id": "conversation-live", "status": "completed", "runtime_trace": {"initial_operation_id": "explain_previous_evidence"}}, 1.0, None),
    ])
    monkeypatch.setattr(module, "request_json", lambda **kwargs: (calls.append(kwargs) or next(responses)))
    monkeypatch.setattr(module, "request_sse_terminal", lambda **_kwargs: ({
        "run_id": "run-child", "conversation_id": "conversation-live", "status": "completed",
        "runtime_trace": {"initial_operation_id": "explain_previous_evidence"},
    }, None))
    monkeypatch.setattr(module.time, "sleep", lambda _seconds: None)

    results = module.run_cases(
        base_url="https://example.test",
        token="token",
        cases=[
            {"case_id": "parent", "message": "Wat kan je?", "conversation_id": "flow", "expected_operation_id": "capability"},
            {"case_id": "child", "message": "Waarom?", "conversation_id": "flow", "expected_operation_id": "explain_previous_evidence"},
        ],
        existing_results=[{
            "case_id": "parent", "case_status": "completed", "conversation_key": "flow",
            "conversation_id": "conversation-live", "create_http_status": 200,
        }],
    )

    assert [item["case_id"] for item in results] == ["parent", "child"]
    create_calls = [call for call in calls if call.get("method") == "POST"]
    assert len(create_calls) == 1
    assert create_calls[0]["payload"]["conversation_id"] == "conversation-live"
