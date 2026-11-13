"""Test the protected Paper-exit collector boundary and optional PostgreSQL casts."""

import os
import asyncio
from contextlib import contextmanager
from types import SimpleNamespace

import pytest

from backend.scripts import probe_protected_paper_exit_reconciliation as probe
from backend.scripts.run_finn_production_qa import profile_error_category


NAMESPACE = "qa-123-1-ad9fe0d3-deadbeef"


def test_aapl_review_chain_projects_and_reads_exact_usd_evidence(monkeypatch):
    from backend.infrastructure import database
    from backend.services import finn_trade_review_service
    from backend.scripts import probe_protected_closed_paper_review as review_probe

    expected = {
        "source_price_currency": "USD", "source_price": 400,
        "source_price_at": "2026-11-13T15:00:00+00:00",
        "fx_eur_per_unit": 0.92, "fx_observed_at": "2026-11-13T14:59:45+00:00",
        "execution_source_price": 400,
        "execution_source_price_at": "2026-11-13T15:00:00+00:00",
        "execution_fx_eur_per_unit": 0.92,
        "execution_fx_observed_at": "2026-11-13T14:59:45+00:00",
        "saved_stop_loss": 240, "saved_first_target": 320,
    }
    steps = []

    class Session:
        async def __aenter__(self):
            return self
        async def __aexit__(self, *_args):
            return None

    class Reviews:
        def __init__(self, session):
            assert isinstance(session, Session)
        async def list_reviews(self, owner, limit):
            assert owner == 11 and limit == 10
            return {"items": [{"id": 77}]}
        async def get_review(self, owner, review_id):
            assert owner == 11 and review_id == 77
            return {
                "id": 77, "bot_id": 22, "execution_environment": "paper",
                "analysis_status": "ready", "analysis_json": {
                    "format_version": 4,
                    "observations": [{"evidence_ids": ["paper_exit:decision"]}],
                },
                "paper_exit_evidence": {"trigger": "first_target", **expected},
                "plan_snapshot": {"source_price_currency": "USD", "source_levels": {
                    "stop_loss": 240, "targets": [320],
                }},
                "plan_status": "entry_order_plan_recorded",
            }

    async def dispose():
        steps.append("dispose")

    @contextmanager
    def rollout(owner):
        assert owner == 11
        yield

    async def chat(owner, message):
        assert owner == 11 and "#77" in message
        steps.append("chat")
        return SimpleNamespace(
            status="completed", run_id="qa-run", conversation_id="qa-conversation",
            policy=None,
            response=SimpleNamespace(
                proposal_id=None, confirmation_required=False,
                evidence=[SimpleNamespace(entity_type="review_history")],
                content="Het vastgelegde first_target was 320 USD; EUR-factor 0,92.",
            ),
        )

    async def exchange(owner, run_id, conversation_id):
        return (owner, run_id, conversation_id) == (11, "qa-run", "qa-conversation")

    monkeypatch.setattr(database, "async_session_factory", Session)
    monkeypatch.setattr(database, "engine", SimpleNamespace(dispose=dispose))
    monkeypatch.setattr(finn_trade_review_service, "FinnTradeReviewService", Reviews)
    monkeypatch.setattr(review_probe, "_process_review_for_fixture", lambda owner: steps.append("project"))
    monkeypatch.setattr(review_probe, "_fixture_review_rollout", rollout)
    monkeypatch.setattr(review_probe, "_chat_turn", chat)
    monkeypatch.setattr(review_probe, "_has_responses_exchange", exchange)

    result = asyncio.run(probe._review_chain(11, 22, expected))
    assert result["result"] == "PASS"
    assert result["analysis_format_version"] == 4
    assert steps == ["project", "dispose", "chat"]


def test_review_chain_reports_bounded_analysis_failure_before_finn(monkeypatch):
    from backend.infrastructure import database
    from backend.services import finn_trade_review_service
    from backend.scripts import probe_protected_closed_paper_review as review_probe

    class Session:
        async def __aenter__(self):
            return self
        async def __aexit__(self, *_args):
            return None

    class Reviews:
        def __init__(self, _session):
            pass
        async def list_reviews(self, owner, limit):
            assert owner == 11 and limit == 10
            return {"items": [{"id": 77}]}
        async def get_review(self, owner, review_id):
            assert owner == 11 and review_id == 77
            return {"analysis_status": "failed"}

    @contextmanager
    def capture():
        yield ["evidence_grounding"]

    async def dispose():
        pass

    monkeypatch.setattr(database, "async_session_factory", Session)
    monkeypatch.setattr(database, "engine", SimpleNamespace(dispose=dispose))
    monkeypatch.setattr(finn_trade_review_service, "FinnTradeReviewService", Reviews)
    monkeypatch.setattr(review_probe, "_process_review_for_fixture", lambda _owner: None)
    monkeypatch.setattr(review_probe, "_capture_fixture_analysis_failures", capture)
    monkeypatch.setattr(review_probe, "_chat_turn", lambda *_args: pytest.fail("FINN chat started"))
    with pytest.raises(RuntimeError, match="^paper_exit_review_analysis_not_ready$") as caught:
        asyncio.run(probe._review_chain(11, 22, {}))
    assert caught.value.review_step == "dossier_read"
    assert caught.value.analysis_failure == "evidence_grounding"
    assert profile_error_category("trader_paper_exit_review_chain", caught.value) == "paper_exit_review_analysis_not_ready"


@pytest.mark.parametrize("error,expected", [
    (ValueError("Ungrounded analysis observation"), "evidence_grounding"),
    (ValueError("Invalid analysis observations"), "observation_shape"),
    (ValueError("Invalid analysis summary"), "invalid_summary"),
    (ValueError("private model content"), "validation_other"),
    (TimeoutError("private timeout detail"), "runtime_timeout"),
])
def test_review_analysis_failure_categories_are_fixed(error, expected):
    from backend.scripts.probe_protected_closed_paper_review import _safe_analysis_failure

    assert _safe_analysis_failure(error) == expected


def test_fixture_analysis_failure_capture_is_process_local_and_restored(monkeypatch):
    from backend.services import finn_trade_analysis_service as analysis_service
    from backend.scripts.probe_protected_closed_paper_review import _capture_fixture_analysis_failures

    async def failing(*_args, **_kwargs):
        raise ValueError("Ungrounded analysis observation")

    monkeypatch.setattr(analysis_service, "_validated_model_analysis", failing)
    with _capture_fixture_analysis_failures() as failures:
        with pytest.raises(ValueError, match="Ungrounded analysis observation"):
            asyncio.run(analysis_service._validated_model_analysis({}, set(), image=None))
        assert failures == ["evidence_grounding"]
    assert analysis_service._validated_model_analysis is failing


def test_aapl_fixture_seeds_only_usd_paper_rows(monkeypatch):
    statements = []

    class Cursor:
        rowcount = 1
        def __enter__(self):
            return self
        def __exit__(self, *_args):
            return None
        def execute(self, sql, values=None):
            statements.append((sql, values))
        def fetchone(self):
            if "udt_name" in statements[-1][0]:
                return ("_text",)
            return (5,)

    class Connection:
        def cursor(self):
            return Cursor()
        def commit(self):
            statements.append(("COMMIT", None))
        def close(self):
            return None

    monkeypatch.setattr(probe.fixture, "_connection", Connection)
    probe._seed_trade(11, 22, None, {"market_price": 400, "market_price_eur": 368}, symbol="AAPL")
    assert statements[-1][0] == "COMMIT"
    assert all("'BTC'" not in sql for sql, _ in statements)
    assert any("UPDATE bot_configs" in sql and values[:2] == ("AAPL", None)
               for sql, values in statements if values)
    assert any("INSERT INTO bot_orders" in sql and values[3:5] == ("AAPL", None)
               for sql, values in statements if values)
    assert any("UPDATE finn_trade_order_context" in sql
               and '"source_price_currency": "USD"' in values[0]
               for sql, values in statements if values)


def test_synthetic_aapl_quote_is_process_scoped(monkeypatch):
    from backend.engine import trading_bot_execution as execution

    original = execution._get_trade_quote_fx_context
    context = {"market_price": 400, "quote_currency": "USD"}
    with probe._fixture_quote_context("AAPL", context):
        assert execution._get_trade_quote_fx_context(None, "AAPL", require_usd=True) is context
        with pytest.raises(RuntimeError, match="paper_exit_fixture_quote_scope_changed"):
            execution._get_trade_quote_fx_context(None, "BTC", require_usd=True)
    assert execution._get_trade_quote_fx_context is original


def _emit_page_bot_response(kwargs, *, status=200, bots=None):
    class Response:
        url = "https://tradamind.com/api/bot/configs?_=cache-bust"
        request = type("Request", (), {"method": "GET"})()
        async def json(self):
            return [{"id": 22}] if bots is None else bots
    response = Response()
    response.status = status
    kwargs["observe_response"](response)


def test_probe_requires_authorization_before_source_read(monkeypatch):
    monkeypatch.delenv("FINN_QA_ALLOW_PAPER_EXIT_FIXTURE", raising=False)
    monkeypatch.setattr(probe, "_preflight", lambda: pytest.fail("unexpected source read"))
    with pytest.raises(RuntimeError, match="^paper_exit_fixture_not_authorized$"):
        probe.run(NAMESPACE)


@pytest.mark.parametrize(("rendered_value", "stop_present"),
                         [(True, True), (False, True), (True, False)])
def test_probe_replays_once_and_cleans_only_after_contract_pass(monkeypatch, rendered_value, stop_present):
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
            "rendered_saved_stop": stop_present,
            "rendered_saved_target": True,
            "rendered_decision_source_quote": True,
            "rendered_decision_fx": True,
            "rendered_exit_eur_price": True,
            "rendered_exit_quantity": True,
            "rendered_exit_proceeds": True,
            "rendered_exit_source_quote": True,
            "rendered_exit_fx": True,
            "rendered_conversion": True,
        }
    monkeypatch.setattr(probe, "_rendered_exit", rendered)
    monkeypatch.setattr(probe.fixture, "_cleanup", lambda *args: steps.append("cleanup"))
    monkeypatch.setattr(probe.fixture, "_quarantine", lambda *args: steps.append("quarantine"))
    result = probe.run(NAMESPACE)
    if rendered_value and stop_present:
        assert result == {"result": "PASS", "failed_checks": [],
                          "exit_decisions": 1, "replay_duplicate_sells": 0,
                          "engine_calls": 2, "live_calls": 0,
                          "rendered_ui_checked": True, "gate_status": "PASS",
                          "onboarding_navigation_override": True}
        assert steps == ["seed_trade", "run", "run", "render", "cleanup"]
    else:
        failed = "rendered_exit_fields_present" if not rendered_value else "rendered_saved_stop"
        assert result == {"result": "FAIL", "failed_checks": [failed],
                          "engine_calls": 2, "live_calls": 0,
                          "rendered_ui_checked": True, "gate_status": "FAIL",
                          "onboarding_navigation_override": True}
        assert steps == ["seed_trade", "run", "run", "render", "quarantine"]


def test_source_parity_profile_requires_its_own_four_surface_result(monkeypatch):
    from backend.engine import trading_bot_execution
    from backend.scripts import probe_protected_source_time_parity
    from backend.scripts import probe_protected_account_answer

    monkeypatch.setenv("FINN_QA_ALLOW_PAPER_EXIT_FIXTURE", "1")
    monkeypatch.setenv("FINN_QA_USER_ID", "7")
    steps = []
    monkeypatch.setattr(probe, "_preflight", lambda: (2, {"market_price": 100,
        "market_price_eur": 90, "source_ref": {"secret": "private"}}))
    monkeypatch.setattr(probe.fixture, "_seed", lambda *args: (11, 22, "today"))
    monkeypatch.setattr(probe, "_seed_trade", lambda *args: None)
    class Cursor:
        def __enter__(self):
            return self
        def __exit__(self, *_args):
            return False
        def execute(self, *_args):
            pass
        def fetchone(self):
            return (910, 0.001)
    class Connection:
        def cursor(self):
            return Cursor()
        def close(self):
            pass
    monkeypatch.setattr(probe.fixture, "_connection", Connection)
    monkeypatch.setattr(trading_bot_execution, "run_trading_bot_execution",
                        lambda *args, **kwargs: {"ok": True})
    monkeypatch.setattr(probe, "_evidence", lambda *args: {"ui_projection": {}})
    monkeypatch.setattr(probe, "check_paper_exit",
                        lambda *_args: {"result": "PASS", "failed_checks": []})
    async def rendered(*_args):
        return {key: True for key in (
            "rendered_exit_fields_present", "rendered_saved_stop", "rendered_saved_target",
            "rendered_decision_source_quote", "rendered_decision_fx",
            "rendered_exit_eur_price",
            "rendered_exit_quantity", "rendered_exit_proceeds",
            "rendered_exit_source_quote", "rendered_exit_fx", "rendered_conversion",
        )}
    monkeypatch.setattr(probe, "_rendered_exit", rendered)
    monkeypatch.setattr(probe_protected_account_answer, "_business_state", lambda *_args: {
        "counts": {"bot_orders": 1}, "fingerprints": {"bot_orders": b"same"},
    })
    monkeypatch.setattr(probe_protected_source_time_parity, "run", lambda **_kwargs: {
        "result": "FAIL", "failed_checks": ["report_source"],
        "gate_status": "FAIL", "browser_zones_checked": 6,
    })
    monkeypatch.setattr(probe.fixture, "_cleanup", lambda *args: steps.append("cleanup"))
    monkeypatch.setattr(probe.fixture, "_quarantine", lambda *args: steps.append("quarantine"))
    result = probe.run(NAMESPACE, source_parity=True)
    assert result["result"] == "FAIL"
    assert result["failed_checks"] == ["report_source"]
    assert result["source_time_parity"]["browser_zones_checked"] == 6
    assert "private" not in str(result)
    assert steps == ["quarantine"]

    def attempted_live(**_kwargs):
        with pytest.raises(RuntimeError, match="paper_exit_live_execution_attempt"):
            trading_bot_execution._execute_on_exchange_sync()
        return {"result": "PASS", "failed_checks": [], "gate_status": "PASS",
                "browser_zones_checked": 6}
    monkeypatch.setattr(probe_protected_source_time_parity, "run", attempted_live)
    result = probe.run(NAMESPACE, source_parity=True)
    assert result["failed_checks"] == ["live_execution_attempt"]
    assert result["live_calls"] == 1
    assert steps == ["quarantine", "quarantine"]


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
            if '/api/bot/trades/all' in script:
                reads.append('trades')
                return {"status": 200, "present": True}
            return {key: True for key in (
                "rendered_exit_fields_present", "rendered_saved_stop", "rendered_saved_target",
                "rendered_decision_source_quote", "rendered_decision_fx",
                "rendered_exit_eur_price",
                "rendered_exit_quantity", "rendered_exit_proceeds",
                "rendered_exit_source_quote", "rendered_exit_fx", "rendered_conversion",
            )}
    async def observe_page(**kwargs):
        assert kwargs["path"] == "/bot?bot_id=22"
        assert kwargs["bypass_fixture_onboarding"] is True
        _emit_page_bot_response(kwargs)
        reads.append('bots')
        return await kwargs["inspect"](Page())
    monkeypatch.setattr(qa_protected_browser, "observe_page", observe_page)
    monkeypatch.setattr(auth_utils, "create_access_token", lambda *_args: "in-memory-token")
    import asyncio
    result = asyncio.run(probe._rendered_exit(11, 22, {}))
    assert all(result.values())
    assert events[:3] == ["wait", "wait", "click"]
    assert reads == ["bots", "trades"]


@pytest.mark.parametrize("status,present,expected", [
    (401, False, "paper_exit_rendered_owner_bot_page_get_auth_failed"),
    (503, False, "paper_exit_rendered_owner_bot_page_get_unavailable_failed"),
])
def test_rendered_exit_sanitizes_owner_bot_read(monkeypatch, status, present, expected):
    from backend.scripts import qa_protected_browser
    from backend.utils import auth_utils

    class Page:
        def locator(self, _selector):
            class Locator:
                @property
                def first(self):
                    return self
                async def wait_for(self, **_kwargs):
                    pass
            return Locator()
    async def observe_page(**kwargs):
        _emit_page_bot_response(kwargs, status=status, bots=[{"id": 22}] if present else [])
        return await kwargs["inspect"](Page())
    monkeypatch.setattr(qa_protected_browser, "observe_page", observe_page)
    monkeypatch.setattr(auth_utils, "create_access_token", lambda *_args: "in-memory-token")
    import asyncio
    with pytest.raises(RuntimeError, match=f"^{expected}$"):
        asyncio.run(probe._rendered_exit(11, 22, {}))
    assert profile_error_category(
        "trader_paper_exit_reconciliation", RuntimeError(expected)
    ) == expected


@pytest.mark.parametrize("bots,selected_missing,reason,shape,count", [
    ([{"id": 22}], True, "owner_bot_not_selected", "array", 1),
    ([], False, "owner_bot_page_get_missing", "array", 0),
    ({"items": [{"id": 22}]}, False, "owner_bot_page_get_missing", "wrapper", None),
])
def test_rendered_exit_reports_only_sanitized_page_get_and_ui_state(
    monkeypatch, bots, selected_missing, reason, shape, count,
):
    from backend.scripts import qa_protected_browser
    from backend.utils import auth_utils

    class Locator:
        @property
        def first(self):
            return self
        async def wait_for(self, **_kwargs):
            if selected_missing:
                raise ValueError("private DOM content")
    class Page:
        url = "https://tradamind.com/bot?bot_id=private"
        def locator(self, _selector):
            return Locator()
        async def evaluate(self, _script):
            return {"focus_nav_present": False, "bot_button_count": 0,
                    "onboarding_guide_present": True}
    async def observe_page(**kwargs):
        _emit_page_bot_response(kwargs, bots=bots)
        return await kwargs["inspect"](Page())
    monkeypatch.setattr(qa_protected_browser, "observe_page", observe_page)
    monkeypatch.setattr(auth_utils, "create_access_token", lambda *_args: "in-memory-token")
    import asyncio
    result = asyncio.run(probe._rendered_exit(11, 22, {}))
    assert result["rendered_failure_reason"] == reason
    assert result["ui_diagnostic"]["bot_get_status"] == 200
    assert result["ui_diagnostic"]["bot_get_shape"] == shape
    assert result["ui_diagnostic"]["bot_get_count"] == count
    assert result["ui_diagnostic"]["owner_bot_present"] is (shape == "array" and count == 1)
    assert "private" not in str(result)


def test_rendered_exit_error_observation_exports_only_bounded_codes(monkeypatch, tmp_path):
    import asyncio
    import json

    from backend.scripts import qa_protected_browser
    from backend.scripts import qa_browser_error_signature
    from backend.utils import auth_utils

    bundle = tmp_path / "app" / "(protected)" / "bot" / "page-a1b2c3.js"
    bundle.parent.mkdir(parents=True)
    bundle.write_text("var r=123456789;\n", encoding="utf-8")
    monkeypatch.setattr(qa_browser_error_signature, "_DEFAULT_BUNDLE_ROOT", tmp_path)

    class Locator:
        @property
        def first(self):
            return self

        async def wait_for(self, **_kwargs):
            raise TimeoutError("private bot name and owner ID")

    class Page:
        url = "https://tradamind.com/bot?bot_id=private"

        def locator(self, _selector):
            return Locator()

        async def evaluate(self, _script):
            return {"focus_nav_present": False, "bot_button_count": 0,
                    "onboarding_guide_present": False}

    class PageError(Exception):
        stack = ("at https://tradamind.com/_next/static/chunks/"
                 "app/(protected)/bot/page-a1b2c3.js:1:5\nprivate-token")

    class ConsoleMessage:
        type = "error"
        text = "ChunkLoadError: Loading chunk private-token failed"
        location = {"url": "https://tradamind.com/_next/static/chunks/main-private.js?token=private"}

    async def observe_page(**kwargs):
        _emit_page_bot_response(kwargs)
        kwargs["observe_page_error"](PageError("TypeError: (0,r.A) is not a function"))
        for _ in range(5):
            kwargs["observe_console"](ConsoleMessage())
        return await kwargs["inspect"](Page())

    monkeypatch.setattr(qa_protected_browser, "observe_page", observe_page)
    monkeypatch.setattr(auth_utils, "create_access_token", lambda *_args: "in-memory-token")
    result = asyncio.run(probe._rendered_exit(11, 22, {}))
    diagnostic = result["ui_diagnostic"]
    assert diagnostic["page_error_count"] == 1
    assert diagnostic["console_error_count"] == 5
    assert diagnostic["page_error_signatures"] == [
        {"kind": "js_non_callable", "stack_area": "next_chunk",
         "bundle_basename": "page-a1b2c3.js", "line": 1, "column": 5,
         "minified_call": "(0,r.A)"},
    ]
    assert diagnostic["console_error_signatures"] == [
        {"kind": "next_chunk_load", "stack_area": "next_runtime"},
    ]
    serialized = json.dumps(result)
    assert "private" not in serialized
    assert "token" not in serialized
    assert "owner ID" not in serialized


@pytest.mark.parametrize("fail_in_inspect,expected", [
    (False, "paper_exit_rendered_bootstrap_failed"),
    (True, "paper_exit_rendered_login_redirect_failed"),
])
def test_rendered_exit_sanitizes_browser_failure_phase(monkeypatch, fail_in_inspect, expected):
    from backend.scripts import qa_protected_browser
    from backend.utils import auth_utils

    async def observe_page(**kwargs):
        if fail_in_inspect:
            class Page:
                url = "https://tradamind.com/login"
                def locator(self, _selector):
                    raise ValueError("private DOM and fixture identity")
            _emit_page_bot_response(kwargs)
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
        def locator(self, selector):
            return OwnerLocator() if 'button[aria-pressed="true"]' in selector else Locator()
    async def observe_page(**kwargs):
        _emit_page_bot_response(kwargs)
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
    (8, "order_insert"), (9, "plan_capture"), (10, "ledger_insert"),
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
