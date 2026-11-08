"""Test the protected Paper-exit collector boundary and optional PostgreSQL casts."""

import os

import pytest

from backend.scripts import probe_protected_paper_exit_reconciliation as probe
from backend.scripts.run_finn_production_qa import profile_error_category


NAMESPACE = "qa-123-1-ad9fe0d3-deadbeef"


def test_probe_requires_authorization_before_source_read(monkeypatch):
    monkeypatch.delenv("FINN_QA_ALLOW_PAPER_EXIT_FIXTURE", raising=False)
    monkeypatch.setattr(probe, "_preflight", lambda: pytest.fail("unexpected source read"))
    with pytest.raises(RuntimeError, match="^paper_exit_fixture_not_authorized$"):
        probe.run(NAMESPACE)


@pytest.mark.parametrize("rendered_value", [True, False])
def test_probe_replays_once_and_cleans_only_after_contract_pass(monkeypatch, rendered_value):
    from backend.engine import trading_bot_execution

    monkeypatch.setenv("FINN_QA_ALLOW_PAPER_EXIT_FIXTURE", "1")
    monkeypatch.setenv("FINN_QA_USER_ID", "7")
    steps = []
    monkeypatch.setattr(probe, "_preflight", lambda: (2, {"market_price": 100,
                                                        "market_price_eur": 90}))
    monkeypatch.setattr(probe.fixture, "_seed", lambda *args: (11, 22, "today"))
    monkeypatch.setattr(probe, "_seed_trade", lambda *args: steps.append("seed_trade"))
    class Cursor:
        def __enter__(self):
            return self
        def __exit__(self, *args):
            return None
        def execute(self, *args):
            return None
        def fetchone(self):
            return (910, 0.001)
    class Connection:
        def cursor(self):
            return Cursor()
        def close(self):
            return None
    monkeypatch.setattr(probe.fixture, "_connection", Connection)
    monkeypatch.setattr(trading_bot_execution, "run_trading_bot_execution",
                        lambda *args, **kwargs: (steps.append("run") or {"ok": True}))
    monkeypatch.setattr(probe, "_evidence", lambda *args: {"fixture": "private", "ui_projection": {}})
    monkeypatch.setattr(probe, "check_paper_exit",
                        lambda evidence: {"result": "PASS", "failed_checks": []})
    async def rendered(*_args):
        steps.append("render")
        return {
            "rendered_exit_fields_present": rendered_value,
            "rendered_exit_eur_price": True,
            "rendered_exit_quantity": True,
            "rendered_exit_proceeds": True,
            "rendered_exit_source_quote": True,
            "rendered_exit_fx": True,
        }
    monkeypatch.setattr(probe, "_rendered_exit", rendered)
    monkeypatch.setattr(probe.fixture, "_cleanup", lambda *args: steps.append("cleanup"))
    monkeypatch.setattr(probe.fixture, "_quarantine", lambda *args: steps.append("quarantine"))
    result = probe.run(NAMESPACE)
    if rendered_value:
        assert result == {"result": "PASS", "failed_checks": [],
                          "exit_decisions": 1, "replay_duplicate_sells": 0,
                          "engine_calls": 2, "live_calls": 0,
                          "rendered_ui_checked": True, "gate_status": "PASS",
                          "onboarding_navigation_override": True}
        assert steps == ["seed_trade", "run", "run", "render", "cleanup"]
    else:
        assert result == {"result": "FAIL", "failed_checks": ["rendered_exit_fields_present"],
                          "engine_calls": 2, "live_calls": 0,
                          "rendered_ui_checked": True, "gate_status": "FAIL",
                          "onboarding_navigation_override": True}
        assert steps == ["seed_trade", "run", "run", "render", "quarantine"]


def test_probe_quarantines_when_persisted_effect_does_not_reconcile(monkeypatch):
    from backend.engine import trading_bot_execution

    monkeypatch.setenv("FINN_QA_ALLOW_PAPER_EXIT_FIXTURE", "1")
    monkeypatch.setenv("FINN_QA_USER_ID", "7")
    steps = []
    monkeypatch.setattr(probe, "_preflight", lambda: (2, {}))
    monkeypatch.setattr(probe.fixture, "_seed", lambda *args: (11, 22, "today"))
    monkeypatch.setattr(probe, "_seed_trade", lambda *args: None)
    class Cursor:
        def __enter__(self):
            return self
        def __exit__(self, *args):
            return None
        def execute(self, *args):
            return None
        def fetchone(self):
            return (910, 0.001)
    class Connection:
        def cursor(self):
            return Cursor()
        def close(self):
            return None
    monkeypatch.setattr(probe.fixture, "_connection", Connection)
    monkeypatch.setattr(trading_bot_execution, "run_trading_bot_execution",
                        lambda *args, **kwargs: {"ok": True})
    monkeypatch.setattr(probe, "_evidence", lambda *args: {})
    monkeypatch.setattr(probe, "check_paper_exit",
                        lambda evidence: {"result": "FAIL",
                                          "failed_checks": ["cashflow_reconciles"]})
    monkeypatch.setattr(probe.fixture, "_cleanup", lambda *args: steps.append("cleanup"))
    monkeypatch.setattr(probe.fixture, "_quarantine", lambda *args: steps.append("quarantine"))
    assert probe.run(NAMESPACE) == {"result": "FAIL",
                                    "failed_checks": ["cashflow_reconciles"],
                                    "rendered_ui_checked": False,
                                    "gate_status": "FAIL", "engine_calls": 2,
                                    "live_calls": 0}
    assert steps == ["quarantine"]


def test_probe_error_category_sanitizes_unexpected_errors():
    assert profile_error_category(
        "trader_paper_exit_reconciliation", RuntimeError("private account 123")
    ) == "paper_exit_probe_runtime_error"


def test_rendered_exit_opens_trades_before_reading_evidence(monkeypatch):
    from backend.scripts import qa_protected_browser
    from backend.utils import auth_utils

    events = []
    reads = []
    class Locator:
        @property
        def first(self):
            return self
        def nth(self, index):
            assert index == 1
            return self
        def locator(self, _selector):
            return self
        async def wait_for(self, **_kwargs):
            events.append("wait")
        async def click(self):
            events.append("click")
        async def count(self):
            return 1
        async def all_text_contents(self):
            assert events[:3] == ["wait", "wait", "click"]
            return ["line"] * 8
    class Page:
        def locator(self, selector):
            if 'button[aria-pressed="true"]' in selector:
                assert not events
            elif '> nav[aria-label] > button' in selector:
                assert events == ["wait"]
            else:
                assert events[:3] == ["wait", "wait", "click"]
            return Locator()
        async def evaluate(self, script, _args):
            if '/api/bot/configs' in script:
                reads.append('bots')
                return {"status": 200, "present": True}
            if '/api/bot/trades/all' in script:
                reads.append('trades')
                return {"status": 200, "present": True}
            return {key: True for key in (
                "rendered_exit_fields_present", "rendered_exit_eur_price",
                "rendered_exit_quantity", "rendered_exit_proceeds",
                "rendered_exit_source_quote", "rendered_exit_fx",
            )}
    async def observe_page(**kwargs):
        assert kwargs["path"] == "/bot?bot_id=22"
        assert kwargs["bypass_fixture_onboarding"] is True
        return await kwargs["inspect"](Page())
    monkeypatch.setattr(qa_protected_browser, "observe_page", observe_page)
    monkeypatch.setattr(auth_utils, "create_access_token", lambda *_args: "in-memory-token")
    import asyncio
    result = asyncio.run(probe._rendered_exit(11, 22, {}))
    assert all(result.values())
    assert events[:3] == ["wait", "wait", "click"]
    assert reads == ["bots", "trades"]


@pytest.mark.parametrize("status,present,expected", [
    (401, False, "paper_exit_rendered_owner_bot_api_auth_failed"),
    (503, False, "paper_exit_rendered_owner_bot_api_unavailable_failed"),
    (200, False, "paper_exit_rendered_owner_bot_api_missing_failed"),
])
def test_rendered_exit_sanitizes_owner_bot_read(monkeypatch, status, present, expected):
    from backend.scripts import qa_protected_browser
    from backend.utils import auth_utils

    class Page:
        async def evaluate(self, _script, _args):
            return {"status": status, "present": present}
    async def observe_page(**kwargs):
        return await kwargs["inspect"](Page())
    monkeypatch.setattr(qa_protected_browser, "observe_page", observe_page)
    monkeypatch.setattr(auth_utils, "create_access_token", lambda *_args: "in-memory-token")
    import asyncio
    with pytest.raises(RuntimeError, match=f"^{expected}$"):
        asyncio.run(probe._rendered_exit(11, 22, {}))
    assert profile_error_category(
        "trader_paper_exit_reconciliation", RuntimeError(expected)
    ) == expected


@pytest.mark.parametrize("fail_in_inspect,expected", [
    (False, "paper_exit_rendered_bootstrap_failed"),
    (True, "paper_exit_rendered_owner_bot_wait_failed"),
])
def test_rendered_exit_sanitizes_browser_failure_phase(monkeypatch, fail_in_inspect, expected):
    from backend.scripts import qa_protected_browser
    from backend.utils import auth_utils

    async def observe_page(**kwargs):
        if fail_in_inspect:
            class Page:
                async def evaluate(self, _script, _args):
                    return {"status": 200, "present": True}
                def locator(self, _selector):
                    raise ValueError("private DOM and fixture identity")
            return await kwargs["inspect"](Page())
        raise ValueError("private browser error and fixture identity")
    monkeypatch.setattr(qa_protected_browser, "observe_page", observe_page)
    monkeypatch.setattr(auth_utils, "create_access_token", lambda *_args: "in-memory-token")
    import asyncio
    with pytest.raises(RuntimeError, match=f"^{expected}$"):
        asyncio.run(probe._rendered_exit(11, 22, {}))
    assert profile_error_category(
        "trader_paper_exit_reconciliation", RuntimeError(expected)
    ) == expected


@pytest.mark.parametrize("path,expected", [
    ("/login", "paper_exit_rendered_login_redirect_failed"),
    ("/onboarding/profile", "paper_exit_rendered_onboarding_redirect_failed"),
    ("/bot", "paper_exit_rendered_tab_absent_failed"),
])
def test_rendered_exit_classifies_missing_tab_without_url_leak(
    monkeypatch, path, expected,
):
    from backend.scripts import qa_protected_browser
    from backend.utils import auth_utils

    class Locator:
        def nth(self, index):
            assert index == 1
            return self
        async def wait_for(self, **_kwargs):
            raise ValueError("private browser response")
    class OwnerLocator:
        @property
        def first(self):
            return self
        async def wait_for(self, **_kwargs):
            pass
    class Page:
        url = f"https://tradamind.com{path}?fixture=private"
        async def evaluate(self, _script, _args):
            return {"status": 200, "present": True}
        def locator(self, selector):
            return OwnerLocator() if 'button[aria-pressed="true"]' in selector else Locator()
    async def observe_page(**kwargs):
        return await kwargs["inspect"](Page())
    monkeypatch.setattr(qa_protected_browser, "observe_page", observe_page)
    monkeypatch.setattr(auth_utils, "create_access_token", lambda *_args: "in-memory-token")
    import asyncio
    with pytest.raises(RuntimeError, match=f"^{expected}$"):
        asyncio.run(probe._rendered_exit(11, 22, {}))
    assert profile_error_category(
        "trader_paper_exit_reconciliation", RuntimeError(expected)
    ) == expected


@pytest.mark.parametrize("failed_statement,phase", [
    (2, "setup_update"), (3, "target_type"), (4, "strategy_update"),
    (5, "bot_update"), (6, "portfolio_update"), (7, "decision_insert"),
    (8, "order_insert"), (9, "ledger_insert"),
])
def test_opening_fixture_reports_fixed_statement_phase(monkeypatch, failed_statement, phase):
    class Cursor:
        index = -1
        rowcount = 1
        def __enter__(self):
            return self
        def __exit__(self, *_args):
            return None
        def execute(self, *_args):
            self.index += 1
            if self.index == failed_statement:
                raise TypeError("private SQL value")
        def fetchone(self):
            if self.index == 3:
                return ("_text",)
            return (5,)
    class Connection:
        def __init__(self):
            self.cursor_value = Cursor()
            self.rolled_back = False
        def cursor(self):
            return self.cursor_value
        def rollback(self):
            self.rolled_back = True
        def close(self):
            return None
    conn = Connection()
    monkeypatch.setattr(probe.fixture, "_connection", lambda: conn)
    with pytest.raises(RuntimeError, match=f"^paper_exit_open_{phase}_failed$"):
        probe._seed_trade(11, 22, 33, {"market_price": 100, "market_price_eur": 90})
    assert conn.rolled_back
    assert profile_error_category(
        "trader_paper_exit_reconciliation", RuntimeError(f"paper_exit_open_{phase}_failed")
    ) == f"paper_exit_open_{phase}_failed"


@pytest.mark.parametrize("udt_name,expected_cast", [
    ("_text", "ARRAY[%s::text]"),
    ("_varchar", "ARRAY[%s::varchar]"),
    ("_numeric", "ARRAY[%s::numeric]"),
])
def test_opening_fixture_uses_allowlisted_target_array_cast(monkeypatch, udt_name, expected_cast):
    class Cursor:
        index = -1
        def __enter__(self):
            return self
        def __exit__(self, *_args):
            return None
        def execute(self, sql, *_args):
            self.index += 1
            if self.index == 4:
                assert expected_cast in sql
                raise TypeError("stop after verified strategy statement")
        def fetchone(self):
            return (udt_name,) if self.index == 3 else (5,)
    class Connection:
        def __init__(self):
            self.cursor_value = Cursor()
            self.rolled_back = False
        def cursor(self):
            return self.cursor_value
        def rollback(self):
            self.rolled_back = True
        def close(self):
            return None
    conn = Connection()
    monkeypatch.setattr(probe.fixture, "_connection", lambda: conn)
    with pytest.raises(RuntimeError, match="^paper_exit_open_strategy_update_failed$"):
        probe._seed_trade(11, 22, 33, {"market_price": 100, "market_price_eur": 90})
    assert conn.rolled_back


def test_opening_fixture_rejects_unexpected_target_type(monkeypatch):
    class Cursor:
        index = -1
        def __enter__(self):
            return self
        def __exit__(self, *_args):
            return None
        def execute(self, *_args):
            self.index += 1
            assert self.index <= 3
        def fetchone(self):
            return ("_jsonb",) if self.index == 3 else (5,)
    class Connection:
        def __init__(self):
            self.cursor_value = Cursor()
            self.rolled_back = False
        def cursor(self):
            return self.cursor_value
        def rollback(self):
            self.rolled_back = True
        def close(self):
            return None
    conn = Connection()
    monkeypatch.setattr(probe.fixture, "_connection", lambda: conn)
    with pytest.raises(RuntimeError, match="^paper_exit_target_type_unavailable$"):
        probe._seed_trade(11, 22, 33, {"market_price": 100, "market_price_eur": 90})
    assert conn.rolled_back


@pytest.mark.parametrize("column_type,udt_name", [
    ("text[]", "_text"),
    ("varchar[]", "_varchar"),
    ("numeric[]", "_numeric"),
])
def test_target_array_cast_updates_real_postgres(column_type, udt_name):
    dsn = os.getenv("TRADAMIND_TEST_POSTGRES_DSN")
    if not dsn:
        pytest.skip("Set TRADAMIND_TEST_POSTGRES_DSN for the PostgreSQL cast regression")
    import psycopg2

    connection = psycopg2.connect(dsn)
    try:
        with connection.cursor() as cursor:
            cursor.execute(f"CREATE TEMP TABLE qa_target_cast_test (id int, targets {column_type}) ON COMMIT DROP")
            cursor.execute("INSERT INTO qa_target_cast_test (id) VALUES (1)")
            expression = probe._target_array_expression(udt_name)
            cursor.execute(f"UPDATE qa_target_cast_test SET targets={expression} WHERE id=1", ("80000",))
            assert cursor.rowcount == 1
            cursor.execute("SELECT targets::text FROM qa_target_cast_test WHERE id=1")
            assert cursor.fetchone() == ("{80000}",)
    finally:
        connection.rollback()
        connection.close()


def test_live_exchange_guard_blocks_attempt_and_restores_entrypoint():
    from backend.engine import trading_bot_execution

    original = trading_bot_execution._execute_on_exchange_sync
    with probe._guard_live_exchange() as attempts:
        with pytest.raises(RuntimeError, match="^paper_exit_live_execution_attempt$"):
            trading_bot_execution._execute_on_exchange_sync(None, 1, "exchange", "BTC", "sell", 1, 1)
    assert len(attempts) == 1
    assert trading_bot_execution._execute_on_exchange_sync is original


def test_persisted_evidence_uses_execution_quote_not_earlier_decision_quote(monkeypatch):
    raw = {
        "source_price": 95, "fx_eur_per_unit": 0.88,
        "source_price_at": "2026-11-08T09:00:00+00:00",
        "execution_source_price": 100, "execution_fx_eur_per_unit": 0.9,
        "execution_source_price_currency": "USDT",
        "execution_source_price_at": "2026-11-08T09:12:00+00:00",
        "execution_fx_observed_at": "2026-11-08T09:10:00+00:00",
        "execution_eur_price": 90, "execution_qty": 0.5,
        "execution_proceeds_eur": 45,
    }
    rows = [(51, raw, "executed", "sell", "filled", "paper", 0.5, 90, 45, 91)]
    projection = {
        "execution_source_price_currency": "USDT",
        "execution_source_price_at": raw["execution_source_price_at"],
        "execution_fx_observed_at": raw["execution_fx_observed_at"],
        "execution_qty": 0.5, "execution_eur_price": 90,
        "execution_proceeds_eur": 45,
    }
    async def history(_user_id):
        return [{"decision_id": 51, "exit_evidence": projection}]
    monkeypatch.setattr(probe, "_history", history)
    fetched = {
        0: rows, 1: (55, 0), 2: [(45, -0.5, 90, 91)], 3: (1,),
        4: (False, {"qa_fixture": probe.fixture.FIXTURE_MARKER,
                    "qa_namespace": NAMESPACE}),
        5: (0,), 6: (False,), 7: (0,),
    }
    class Cursor:
        index = -1
        def __enter__(self):
            return self
        def __exit__(self, *args):
            return None
        def execute(self, *args):
            self.index += 1
        def fetchone(self):
            return fetched[self.index]
        def fetchall(self):
            return fetched[self.index]
    class Connection:
        cursor_instance = Cursor()
        def cursor(self):
            return self.cursor_instance
        def close(self):
            return None
    monkeypatch.setattr(probe.fixture, "_connection", Connection)
    evidence = probe._evidence(NAMESPACE, 11, 22, 2, 10, 0.5, 0)
    assert evidence["execution_source_price"] == 100
    assert "source_price" not in evidence
    assert probe.check_paper_exit(evidence)["result"] == "PASS"
