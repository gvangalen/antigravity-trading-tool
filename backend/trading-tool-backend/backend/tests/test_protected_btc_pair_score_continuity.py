"""No database or network access: prove protected probe control flow."""

import asyncio
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from backend.scripts import probe_protected_btc_pair_score_continuity as probe
from backend.scripts.run_finn_production_qa import profile_error_category


NAMESPACE = "qa-123-1-5ffd5b21-deadbeef"
MARKETS = {
    "BTC/EUR": {"market_id": 1, "change_24h": 1.5,
                "source_at": datetime(2026, 11, 8, 9, 12, tzinfo=timezone.utc)},
    "BTC/USDT": {"market_id": 2, "change_24h": -1.5,
                 "source_at": datetime(2026, 11, 8, 9, 12, tzinfo=timezone.utc)},
}


def _snapshot(eur_score, usdt_score, *, stale=False):
    rows = {
        "BTC/EUR": {"owner_id": 11, "market_id": 1,
                    "indicator_config": (("market", "change_24h"),),
                    "source_at": "2026-11-08T09:12:00Z",
                    "score": eur_score, "source_status": "missing_score" if stale else "fresh",
                    "fixture_source_diagnosis": "stale_source" if stale else "fresh",
                    "stale_reading_proven": stale},
        "BTC/USDT": {"owner_id": 11, "market_id": 2,
                     "indicator_config": (("market", "change_24h"),),
                     "source_at": "2026-11-08T09:12:00Z", "score": usdt_score,
                     "source_status": "fresh", "source_reason": "fresh"},
    }
    return {"pairs": rows}


def _stable_business(_owner):
    return {"counts": {"bot_orders": 0}, "fingerprints": {"bot_orders": b"same"}}


def test_finn_pair_read_uses_one_event_loop_and_disposes_engine(monkeypatch):
    from backend.infrastructure import database
    from backend.scripts import probe_protected_account_answer, probe_protected_closed_paper_review

    steps = []
    async def chat(owner, message):
        steps.append(("turn", id(asyncio.get_running_loop())))
        assert owner == 11 and "BTC/EUR" in message
        return SimpleNamespace(
            status="completed", run_id="private-run", conversation_id="private-conversation",
            response=SimpleNamespace(proposal_id=None, confirmation_required=False), policy=None,
        )
    async def evidence(**kwargs):
        steps.append(("evidence", id(asyncio.get_running_loop())))
        assert kwargs["user_id"] == 11
        return [{"scope": "read_asset_scores"}]
    async def dispose():
        steps.append(("dispose", id(asyncio.get_running_loop())))
    monkeypatch.setattr(probe_protected_closed_paper_review, "_chat_turn", chat)
    monkeypatch.setattr(probe_protected_account_answer, "_read_tool_results", evidence)
    monkeypatch.setattr(database, "engine", SimpleNamespace(dispose=dispose))
    assert asyncio.run(probe._finn_pair_read(11, "BTC/EUR")) == ([{"scope": "read_asset_scores"}], "ok", None)
    assert [name for name, _loop in steps] == ["turn", "evidence", "dispose"]
    assert len({loop for _name, loop in steps}) == 1


def test_finn_pair_read_disposes_engine_after_failed_turn(monkeypatch):
    from backend.infrastructure import database
    from backend.scripts import probe_protected_closed_paper_review

    steps = []
    async def chat(*_args):
        steps.append("turn")
        raise RuntimeError("private fixture owner 92741")
    async def dispose():
        steps.append("dispose")
    monkeypatch.setattr(probe_protected_closed_paper_review, "_chat_turn", chat)
    monkeypatch.setattr(database, "engine", SimpleNamespace(dispose=dispose))
    with pytest.raises(RuntimeError):
        asyncio.run(probe._finn_pair_read(11, "BTC/EUR"))
    assert steps == ["turn", "dispose"]


@pytest.mark.parametrize("rows,expected", [
    ([], "scope_missing"),
    ([{"scope": "read_asset_scores", "status": "partial"}], "scope_unverified"),
    ([{"scope": "read_asset_scores", "status": "completed", "data": {
        "pair": "BTC/USDT", "market_id": 1, "benchmark_score": 45}}], "pair_mismatch"),
    ([{"scope": "read_asset_scores", "status": "completed", "data": {
        "pair": "BTC/EUR", "market_id": 99, "benchmark_score": 45}}], "market_mismatch"),
    ([{"scope": "read_asset_scores", "status": "completed", "data": {
        "pair": "BTC/EUR", "market_id": 1, "benchmark_score": 99}}], "score_mismatch"),
])
def test_finn_transport_diagnostic_uses_only_fixed_phase_codes(monkeypatch, rows, expected):
    from backend.scripts import qa_protected_readback
    monkeypatch.setattr(qa_protected_readback, "read_json", lambda **_kwargs: {
        "market_id": 1, "pair": "BTC/EUR", "combined": {"score": 45},
    })
    async def finn_read(*_args):
        return rows, "ok", None
    monkeypatch.setattr(probe, "_finn_pair_read", finn_read)
    result = probe._transport_checks(11, {"pairs": {"BTC/EUR": {
        "market_id": 1, "score": 45,
    }}})
    assert result == {"analysis": True, "finn": False,
                      "finn_codes": {"BTC/EUR": expected}, "finn_runtime_codes": {}}
    assert "99" not in str(result) and "11" not in str(result)


@pytest.mark.parametrize("quote_market_id,response_market_id,phase", [
    (1, 1, "indicator_missing"),
    (2, 1, "page_unavailable"),
    (1, 2, "api_source_unverified"),
])
def test_outage_browser_scopes_pending_score_and_quote_market(
    monkeypatch, quote_market_id, response_market_id, phase,
):
    from backend.scripts import qa_protected_browser, qa_protected_readback
    from backend.scripts import probe_protected_source_time_parity as source_probe

    source_at = "2026-10-10T00:30:00+00:00"
    workspace = {
        "market_id": 1, "pair": "BTC/EUR", "daily": {"market": {"score": None}},
        "combined": {"score": None},
        "score_source_observed_at": {"market": {"change_24h": source_at}},
        "categories": {"market": {"rows": [{"name": "change_24h", "score": None,
            "indicator_source_observed_at": source_at,
            "source_observed_at": "2026-11-09T09:12:00+00:00"}]}},
        "quote": {"price": 68267.0,
                  "source_ref": {"market_id": quote_market_id, "measurement_id": 9,
                                 "source_observed_at_utc": "2026-11-09T09:12:00+00:00"}},
    }
    monkeypatch.setattr(qa_protected_readback, "read_json", lambda **_kwargs: workspace)
    async def quote_visible(*_args, **_kwargs):
        return "ok"
    monkeypatch.setattr(source_probe, "_target_quote_visible", quote_visible)

    class Response:
        url = "https://tradamind.com/api/assets/BTC/trading-markets/EUR/select?include_workspace=true"
        status = 200
        async def json(self):
            projected = deepcopy(workspace)
            projected["quote"]["source_ref"]["market_id"] = response_market_id
            return {"workspace": projected}

    class Locator:
        async def count(self):
            return 1
        def locator(self, _selector):
            return self
        def get_by_role(self, *_args, **_kwargs):
            return self
        def filter(self, **_kwargs):
            return self
        async def wait_for(self, **_kwargs):
            return None
    class MissingIndicator(Locator):
        async def count(self):
            return 0
    class Market(Locator):
        def filter(self, **_kwargs):
            return MissingIndicator()
    class Heading(Locator):
        def locator(self, _selector):
            return Market()
    class Page:
        async def evaluate(self, *_args):
            return "current quote UTC"
        def get_by_role(self, *_args, **_kwargs):
            return Heading()

    async def observe_page(*, fixture_exact_selection, observe_response, inspect, **_kwargs):
        assert fixture_exact_selection()["pair"] == "BTC/EUR"
        observe_response(Response())
        return await inspect(Page())
    monkeypatch.setattr(qa_protected_browser, "observe_page", observe_page)
    phases = asyncio.run(probe._stale_date_display(11, source_at, 1))
    assert phases == {"amsterdam": phase, "new_york": phase, "tokyo": phase}


def test_finn_terminal_diagnostic_is_allowlisted_and_redacts_secret_values():
    secret = "private-owner-92871-token-value"
    turn = SimpleNamespace(
        status="failed", error_code=secret, error_message=secret,
        runtime_trace={"reasoning": {"status": "failed", "error_codes": [secret]},
                       "orchestrator": {"outcome": "failed", "snapshot_id": secret}},
    )
    result = probe._finn_terminal_diagnostic(turn)
    assert result == {"status": "failed", "error_code": "other",
                      "reasoning_status": "failed", "orchestrator_outcome": "failed"}
    assert secret not in str(result)
    turn.error_code = "market_pair_ambiguous"
    assert probe._finn_terminal_diagnostic(turn)["error_code"] == "market_pair_ambiguous"


def test_finn_noncompleted_turn_reports_fixed_status_and_reason(monkeypatch):
    from backend.infrastructure import database
    from backend.scripts import probe_protected_closed_paper_review

    async def chat(*_args):
        return SimpleNamespace(status="unavailable", response=None,
                               error_code="selector_phase_timeout",
                               runtime_trace={"reasoning": {"status": "unavailable"},
                                              "orchestrator": {"outcome": "failed"}})
    async def dispose():
        return None
    monkeypatch.setattr(probe_protected_closed_paper_review, "_chat_turn", chat)
    monkeypatch.setattr(database, "engine", SimpleNamespace(dispose=dispose))
    assert asyncio.run(probe._finn_pair_read(11, "BTC/EUR")) == (
        None, "turn_unavailable", {"status": "unavailable", "error_code": "selector_phase_timeout",
                                   "reasoning_status": "unavailable", "orchestrator_outcome": "failed"},
    )


def test_finn_provider_diagnostic_captures_only_fixed_error_and_prior_tool_presence(monkeypatch):
    from openai import AsyncOpenAI
    from openai.resources.responses import AsyncResponses
    from backend.infrastructure import database
    from backend.scripts import probe_protected_account_answer, probe_protected_closed_paper_review

    secret = "private-provider-payload-owner-92871"
    bad_request = type("BadRequestError", (Exception,), {})
    async def failed_provider(self, *_args, **_kwargs):
        error = bad_request(secret)
        error.status_code = 400
        raise error
    monkeypatch.setattr(AsyncResponses, "create", failed_provider)
    async def chat(*_args):
        client = AsyncOpenAI(api_key="synthetic-test-key")
        try:
            await client.with_options(max_retries=0).responses.create(model="synthetic")
        except bad_request:
            pass
        return SimpleNamespace(status="unavailable", response=None,
                               error_code="responses_provider_error", runtime_trace={},
                               run_id="private-run", conversation_id="private-conversation")
    async def score_seen(**_kwargs):
        return True
    async def dispose():
        return None
    monkeypatch.setattr(probe_protected_closed_paper_review, "_chat_turn", chat)
    monkeypatch.setattr(probe, "_score_tool_seen", score_seen)
    monkeypatch.setattr(database, "engine", SimpleNamespace(dispose=dispose))
    rows, phase, diagnostic = asyncio.run(probe._finn_pair_read(11, "BTC/EUR"))
    assert rows is None and phase == "turn_unavailable"
    assert diagnostic["provider_failure"] == {
        "provider_call": 1, "status_class": "4xx", "exception_kind": "BadRequestError",
    }
    assert diagnostic["score_tool_seen"] is True
    assert secret not in str(diagnostic)


def test_provider_call_over_cap_is_explicit_bucket_not_exact_round(monkeypatch):
    from openai.resources.responses import AsyncResponses

    secret = "private-provider-error-owner-92871"
    async def failed_provider(self, *_args, **_kwargs):
        raise RuntimeError(secret)
    monkeypatch.setattr(AsyncResponses, "create", failed_provider)
    async def exercise():
        with probe._provider_failure_probe() as observations:
            for _ in range(5):
                with pytest.raises(RuntimeError):
                    await AsyncResponses.create(None)
        return observations
    observations = asyncio.run(exercise())
    assert [item["provider_call"] for item in observations] == [1, 2, 3, "4_plus", "4_plus"]
    assert all(item["status_class"] == "none" and item["exception_kind"] == "other"
               for item in observations)
    assert secret not in str(observations)


@pytest.mark.parametrize("scope,expected", [
    ("read_asset_scores", True),
    ("read_market_snapshot", False),
])
def test_score_tool_presence_reads_owner_bound_progress_without_exporting_data(
    monkeypatch, scope, expected,
):
    from backend.infrastructure import database
    from backend.infrastructure.repositories import finn_v2_runtime_contract_repository as contracts

    secret = "private-progress-body-owner-92871"
    row = SimpleNamespace(
        user_id=11, conversation_id="private-conversation",
        state_json={"responses_progress": {
            "run_id": "private-run", "conversation_id": "private-conversation",
            "tool_trace": [{"result": {"results": [{"scope": scope, "data": secret}]}}],
        }},
    )
    class Session:
        async def __aenter__(self):
            return self
        async def __aexit__(self, *_args):
            return None
    class Repository:
        def __init__(self, _session):
            pass
        async def get_for_run(self, *, run_id):
            assert run_id == "private-run"
            return row
    monkeypatch.setattr(database, "async_session_factory", Session)
    monkeypatch.setattr(contracts, "FinnV2RuntimeContractRepository", Repository)
    result = asyncio.run(probe._score_tool_seen(
        user_id=11, run_id="private-run", conversation_id="private-conversation",
    ))
    assert result is expected and secret not in str(result)
    row.state_json["responses_exchange"] = {
        "run_id": "private-run", "conversation_id": "private-conversation",
        "tool_trace": [{"result": {"results": [{"scope": "read_market_snapshot",
                                               "data": secret}]}}],
    }
    assert asyncio.run(probe._score_tool_seen(
        user_id=11, run_id="private-run", conversation_id="private-conversation",
    )) is expected
    row.state_json["responses_exchange"]["conversation_id"] = "other-private-conversation"
    assert asyncio.run(probe._score_tool_seen(
        user_id=11, run_id="private-run", conversation_id="private-conversation",
    )) == "unknown"
    assert asyncio.run(probe._score_tool_seen(
        user_id=12, run_id="private-run", conversation_id="private-conversation",
    )) == "unknown"


@pytest.mark.parametrize("response,expected", [
    (None, "response_missing"),
    (SimpleNamespace(proposal_id="private-proposal", confirmation_required=False), "action_boundary"),
])
def test_finn_completed_turn_separates_missing_response_from_action_boundary(
    monkeypatch, response, expected,
):
    from backend.infrastructure import database
    from backend.scripts import probe_protected_closed_paper_review

    async def chat(*_args):
        return SimpleNamespace(status="completed", response=response, policy=None,
                               error_code=None, runtime_trace={})
    async def dispose():
        return None
    monkeypatch.setattr(probe_protected_closed_paper_review, "_chat_turn", chat)
    monkeypatch.setattr(database, "engine", SimpleNamespace(dispose=dispose))
    rows, phase, diagnostic = asyncio.run(probe._finn_pair_read(11, "BTC/EUR"))
    assert rows is None and phase == expected
    assert diagnostic == {"status": "completed", "error_code": "none",
                          "reasoning_status": "other", "orchestrator_outcome": "other"}


@pytest.mark.parametrize("callback_mode,expected", [
    ("absent", "request_absent"),
    ("owner_get_error", "owner_get_error"),
    ("owner_get_invariant", "owner_get_invariant_pair"),
    ("owner_get_ok_no_response", "selection_response_absent"),
    ("owner_get_bad_saved_source", "owner_get_invariant_saved_source"),
    ("owner_get_bad_indicator_source", "owner_get_invariant_indicator_source"),
    ("response_error", "selection_response_error"),
])
def test_outage_browser_classifies_selection_subphase(monkeypatch, callback_mode, expected):
    from backend.scripts import qa_protected_browser, qa_protected_readback

    source_at = "2026-10-10T00:30:00+00:00"
    if callback_mode == "owner_get_error":
        monkeypatch.setattr(qa_protected_readback, "read_json", lambda **_kwargs: (_ for _ in ()).throw(RuntimeError("private-92741")))
    elif callback_mode == "owner_get_invariant":
        monkeypatch.setattr(qa_protected_readback, "read_json", lambda **_kwargs: {"pair": "BTC/USDT"})
    elif callback_mode in {"owner_get_ok_no_response", "owner_get_bad_saved_source",
                           "owner_get_bad_indicator_source"}:
        workspace = {
            "pair": "BTC/EUR", "market_id": 1,
            "score_source_observed_at": {},
            "categories": {"market": {"rows": [{"name": "change_24h", "score": None,
                "indicator_source_observed_at": source_at,
                "source_observed_at": "2026-11-09T09:12:00+00:00"}]}},
            "quote": {"source_ref": {"market_id": 1, "measurement_id": 9,
                                     "source_observed_at_utc": "2026-11-09T09:12:00+00:00"}},
            "daily": {"market": {"score": None}}, "combined": {"score": None},
        }
        if callback_mode == "owner_get_bad_saved_source":
            workspace["score_source_observed_at"] = {
                "market": {"change_24h": "2026-10-09T00:30:00+00:00"}}
        if callback_mode == "owner_get_bad_indicator_source":
            workspace["categories"]["market"]["rows"][0]["indicator_source_observed_at"] = (
                "2026-10-09T00:30:00+00:00")
        monkeypatch.setattr(qa_protected_readback, "read_json", lambda **_kwargs: workspace)
    async def observe_page(*, fixture_exact_selection, observe_response, inspect, **_kwargs):
        if callback_mode.startswith("owner_get"):
            if callback_mode == "owner_get_ok_no_response":
                assert fixture_exact_selection()["pair"] == "BTC/EUR"
            else:
                with pytest.raises(Exception):
                    fixture_exact_selection()
        if callback_mode == "response_error":
            observe_response(SimpleNamespace(url="https://tradamind.com/api/assets/BTC/trading-markets/EUR/select", status=500))
        return await inspect(SimpleNamespace())
    monkeypatch.setattr(qa_protected_browser, "observe_page", observe_page)
    result = asyncio.run(probe._stale_date_display(11, source_at, 1))
    assert result == {"amsterdam": expected, "new_york": expected, "tokyo": expected}


def test_real_browser_requires_old_source_date_inside_btc_eur_indicator_row():
    playwright = pytest.importorskip("playwright.async_api")

    async def exercise():
        async with playwright.async_playwright() as runtime:
            try:
                browser = await runtime.chromium.launch(headless=True, args=["--no-sandbox"])
            except playwright.Error:
                pytest.skip("Chromium unavailable")
            try:
                page = await browser.new_page()
                old = "10 okt 2026 00:30 UTC"
                current = "9 nov 2026 09:12 UTC"
                await page.set_content(f"""
                    <p>{old}</p>
                    <section><h2>Markt</h2><button>Prijsverandering 24 uur
                      <span>Score wordt berekend</span>
                      <span>Laatste indicatormeting: {old}.</span>
                      <span>Getoonde 24-uursverandering uit koersbron: {current}.</span>
                    </button></section>
                """)
                assert await probe._outage_indicator_visible(
                    page, old_source_time=old, current_quote_time=current, timeout_ms=150,
                ) == "ok"
                await page.set_content(f"""
                    <p>{old}</p>
                    <section><h2>Markt</h2><button>Prijsverandering 24 uur
                      <span>Score wordt berekend</span>
                      <span>Getoonde 24-uursverandering uit koersbron: {current}.</span>
                    </button></section>
                """)
                assert await probe._outage_indicator_visible(
                    page, old_source_time=old, current_quote_time=current, timeout_ms=150,
                ) == "old_source_date_or_pending_missing"
            finally:
                await browser.close()

    asyncio.run(exercise())


def test_probe_runs_three_pair_snapshots_and_cleans_only_verified_fixture(monkeypatch):
    monkeypatch.setenv("FINN_QA_ALLOW_TRADER_PAIR_FIXTURE", "1")
    monkeypatch.setenv("FINN_QA_USER_ID", "7")
    steps = []
    monkeypatch.setattr(probe, "_markets", lambda: MARKETS)
    monkeypatch.setattr(probe.fixture, "_seed", lambda namespace, owner: (11, 22, "today"))
    monkeypatch.setattr(probe, "_seed_pair_readings", lambda *args: steps.append("seed_readings"))
    monkeypatch.setattr(probe, "_business_snapshot", _stable_business)
    snapshots = iter((_snapshot(45, 70), _snapshot(None, 70, stale=True), _snapshot(45, 70)))
    monkeypatch.setattr(probe, "_snapshot", lambda *args: deepcopy(next(snapshots)))
    monkeypatch.setattr(probe, "_transport_checks", lambda *args: {"analysis": True, "finn": True})
    async def stale_browser(*_args):
        return {"amsterdam": "ok", "new_york": "ok", "tokyo": "ok"}
    monkeypatch.setattr(probe, "_stale_date_display", stale_browser)
    monkeypatch.setattr(probe, "_set_eur_source_time", lambda *args, stale: steps.append(f"stale:{stale}"))
    monkeypatch.setattr(probe.fixture, "_cleanup", lambda *args: steps.append("cleanup"))
    monkeypatch.setattr(probe.fixture, "_quarantine", lambda *args: steps.append("quarantine"))
    assert probe.run(NAMESPACE) == {"result": "PASS", "failed_checks": [],
                                    "pairs": 2, "phases": 3,
                                    "source_outage": "owner_scoped", "live_calls": 0,
                                    "analysis_transport_checked": True,
                                    "finn_transport_checked": True,
                                    "outage_quote_pending_browser_checked": True,
                                    "gate_status": "PASS"}
    assert steps == ["seed_readings", "stale:True", "stale:False", "cleanup"]


def test_probe_quarantines_on_score_cross_contamination(monkeypatch):
    monkeypatch.setenv("FINN_QA_ALLOW_TRADER_PAIR_FIXTURE", "1")
    monkeypatch.setenv("FINN_QA_USER_ID", "7")
    steps = []
    monkeypatch.setattr(probe, "_markets", lambda: MARKETS)
    monkeypatch.setattr(probe.fixture, "_seed", lambda *args: (11, 22, "today"))
    monkeypatch.setattr(probe, "_seed_pair_readings", lambda *args: None)
    monkeypatch.setattr(probe, "_business_snapshot", _stable_business)
    snapshots = iter((_snapshot(45, 70), _snapshot(None, 45, stale=True), _snapshot(45, 70)))
    monkeypatch.setattr(probe, "_snapshot", lambda *args: next(snapshots))
    monkeypatch.setattr(probe, "_transport_checks", lambda *args: {"analysis": True, "finn": True})
    async def stale_browser(*_args):
        return {"amsterdam": "ok", "new_york": "ok", "tokyo": "ok"}
    monkeypatch.setattr(probe, "_stale_date_display", stale_browser)
    monkeypatch.setattr(probe, "_set_eur_source_time", lambda *args, **kwargs: None)
    monkeypatch.setattr(probe.fixture, "_cleanup", lambda *args: steps.append("cleanup"))
    monkeypatch.setattr(probe.fixture, "_quarantine", lambda *args: steps.append("quarantine"))
    assert probe.run(NAMESPACE) == {"result": "FAIL",
                                    "failed_checks": ["outage_isolated"],
                                    "analysis_transport_checked": True,
                                    "finn_transport_checked": True,
                                    "outage_quote_pending_browser_checked": True,
                                    "live_calls": 0,
                                    "gate_status": "FAIL"}
    assert steps == ["quarantine"]


def test_probe_quarantines_when_one_transport_misreports_pair(monkeypatch):
    monkeypatch.setenv("FINN_QA_ALLOW_TRADER_PAIR_FIXTURE", "1")
    monkeypatch.setenv("FINN_QA_USER_ID", "7")
    steps = []
    monkeypatch.setattr(probe, "_markets", lambda: MARKETS)
    monkeypatch.setattr(probe.fixture, "_seed", lambda *args: (11, 22, "today"))
    monkeypatch.setattr(probe, "_seed_pair_readings", lambda *args: None)
    monkeypatch.setattr(probe, "_business_snapshot", _stable_business)
    snapshots = iter((_snapshot(45, 70), _snapshot(None, 70, stale=True), _snapshot(45, 70)))
    monkeypatch.setattr(probe, "_snapshot", lambda *args: next(snapshots))
    transport = iter(({"analysis": True, "finn": True},
                      {"analysis": False, "finn": True},
                      {"analysis": True, "finn": True}))
    monkeypatch.setattr(probe, "_transport_checks", lambda *args: next(transport))
    async def stale_browser(*_args):
        return {"amsterdam": "ok", "new_york": "ok", "tokyo": "ok"}
    monkeypatch.setattr(probe, "_stale_date_display", stale_browser)
    monkeypatch.setattr(probe, "_set_eur_source_time", lambda *args, **kwargs: None)
    monkeypatch.setattr(probe.fixture, "_cleanup", lambda *args: steps.append("cleanup"))
    monkeypatch.setattr(probe.fixture, "_quarantine", lambda *args: steps.append("quarantine"))
    result = probe.run(NAMESPACE)
    assert result["failed_checks"] == ["outage_transport_analysis"]
    assert result["gate_status"] == "FAIL"
    assert steps == ["quarantine"]


def test_probe_measures_live_attempt_and_unexpected_business_write(monkeypatch):
    from backend.engine import trading_bot_execution

    monkeypatch.setenv("FINN_QA_ALLOW_TRADER_PAIR_FIXTURE", "1")
    monkeypatch.setenv("FINN_QA_USER_ID", "7")
    steps = []
    monkeypatch.setattr(probe, "_markets", lambda: MARKETS)
    monkeypatch.setattr(probe.fixture, "_seed", lambda *args: (11, 22, "today"))
    monkeypatch.setattr(probe, "_seed_pair_readings", lambda *args: None)
    snapshots = iter((_snapshot(45, 70), _snapshot(None, 70, stale=True), _snapshot(45, 70)))
    monkeypatch.setattr(probe, "_snapshot", lambda *args: next(snapshots))
    business = iter((_stable_business(11), {"counts": {"bot_orders": 1},
                                         "fingerprints": {"bot_orders": b"changed"}}))
    monkeypatch.setattr(probe, "_business_snapshot", lambda *_args: next(business))
    called = False
    def transport(*_args):
        nonlocal called
        if not called:
            called = True
            with pytest.raises(RuntimeError, match="paper_exit_live_execution_attempt"):
                trading_bot_execution._execute_on_exchange_sync()
        return {"analysis": True, "finn": True}
    monkeypatch.setattr(probe, "_transport_checks", transport)
    async def stale_browser(*_args):
        return {"amsterdam": "ok", "new_york": "ok", "tokyo": "ok"}
    monkeypatch.setattr(probe, "_stale_date_display", stale_browser)
    monkeypatch.setattr(probe, "_set_eur_source_time", lambda *args, **kwargs: None)
    monkeypatch.setattr(probe.fixture, "_cleanup", lambda *args: steps.append("cleanup"))
    monkeypatch.setattr(probe.fixture, "_quarantine", lambda *args: steps.append("quarantine"))
    result = probe.run(NAMESPACE)
    assert result["result"] == "FAIL"
    assert result["failed_checks"] == ["live_execution_attempt", "unexpected_business_write"]
    assert result["live_calls"] == 1
    assert steps == ["quarantine"]


def test_probe_rejects_missing_authorization_before_source_or_fixture(monkeypatch):
    monkeypatch.delenv("FINN_QA_ALLOW_TRADER_PAIR_FIXTURE", raising=False)
    monkeypatch.setattr(probe, "_markets", lambda: pytest.fail("unexpected source read"))
    with pytest.raises(RuntimeError, match="^trader_pair_fixture_not_authorized$"):
        probe.run(NAMESPACE)


def test_probe_error_category_does_not_export_database_details():
    assert profile_error_category(
        "trader_pair_score_continuity", RuntimeError("private fixture user 123")
    ) == "trader_pair_probe_runtime_error"
    assert profile_error_category(
        "trader_pair_score_continuity", RuntimeError("btc_pair_source_unavailable")
    ) == "btc_pair_source_unavailable"


def test_probe_reports_fixed_readings_stage_and_quarantines(monkeypatch):
    monkeypatch.setenv("FINN_QA_ALLOW_TRADER_PAIR_FIXTURE", "1")
    monkeypatch.setenv("FINN_QA_USER_ID", "7")
    monkeypatch.setattr(probe, "_markets", lambda: MARKETS)
    monkeypatch.setattr(probe.fixture, "_seed", lambda *_args: (11, 22, "today"))
    monkeypatch.setattr(probe, "_seed_pair_readings", lambda *_args: (_ for _ in ()).throw(
        RuntimeError("private owner 11 secret")))
    quarantined = []
    monkeypatch.setattr(probe.fixture, "_quarantine", lambda *_args: quarantined.append(True))
    with pytest.raises(RuntimeError, match="^trader_pair_readings_failed$"):
        probe.run(NAMESPACE)
    assert quarantined == [True]
    assert profile_error_category("trader_pair_score_continuity", RuntimeError(
        "trader_pair_readings_failed")) == "trader_pair_readings_failed"


def test_probe_reports_quarantine_failure_without_raw_exception(monkeypatch):
    monkeypatch.setenv("FINN_QA_ALLOW_TRADER_PAIR_FIXTURE", "1")
    monkeypatch.setenv("FINN_QA_USER_ID", "7")
    monkeypatch.setattr(probe, "_markets", lambda: MARKETS)
    monkeypatch.setattr(probe.fixture, "_seed", lambda *_args: (11, 22, "today"))
    monkeypatch.setattr(probe, "_seed_pair_readings", lambda *_args: (_ for _ in ()).throw(
        RuntimeError("private owner 11 secret")))
    monkeypatch.setattr(probe.fixture, "_quarantine", lambda *_args: (_ for _ in ()).throw(
        RuntimeError("private bot 22 secret")))
    with pytest.raises(RuntimeError, match="^trader_pair_quarantine_failed$"):
        probe.run(NAMESPACE)


def test_snapshot_substage_classifies_builder_failure_without_private_exception(monkeypatch):
    from backend.celery_task import store_daily_scores_task

    class Connection:
        def close(self):
            pass
    monkeypatch.setattr(probe.fixture, "_connection", Connection)
    monkeypatch.setattr(store_daily_scores_task, "build_daily_scores_for_market",
                        lambda *_args: (_ for _ in ()).throw(RuntimeError("private market value")))
    with pytest.raises(RuntimeError, match="^trader_pair_snapshot_score_builder_failed$"):
        probe._snapshot(11, MARKETS)


def test_probe_reports_outage_snapshot_substage_and_quarantines(monkeypatch):
    monkeypatch.setenv("FINN_QA_ALLOW_TRADER_PAIR_FIXTURE", "1")
    monkeypatch.setenv("FINN_QA_USER_ID", "7")
    monkeypatch.setattr(probe, "_markets", lambda: MARKETS)
    monkeypatch.setattr(probe.fixture, "_seed", lambda *_args: (11, 22, "today"))
    monkeypatch.setattr(probe, "_seed_pair_readings", lambda *_args: None)
    monkeypatch.setattr(probe, "_business_snapshot", _stable_business)
    snapshots = iter((_snapshot(45, 70), RuntimeError("trader_pair_snapshot_assessment_failed")))
    def snapshot(*_args):
        value = next(snapshots)
        if isinstance(value, Exception):
            raise value
        return value
    monkeypatch.setattr(probe, "_snapshot", snapshot)
    monkeypatch.setattr(probe, "_transport_checks", lambda *_args: {"analysis": True, "finn": True})
    monkeypatch.setattr(probe, "_set_eur_source_time", lambda *_args, **_kwargs: None)
    quarantined = []
    monkeypatch.setattr(probe.fixture, "_quarantine", lambda *_args: quarantined.append(True))
    with pytest.raises(RuntimeError, match="^trader_pair_outage_snapshot_assessment_failed$"):
        probe.run(NAMESPACE)
    assert quarantined == [True]
    assert profile_error_category(
        "trader_pair_score_continuity",
        RuntimeError("trader_pair_outage_snapshot_assessment_failed"),
    ) == "trader_pair_outage_snapshot_assessment_failed"


def test_assessment_diagnostic_exposes_only_allowlisted_class_and_static_origin():
    secret = "fixture-owner-92741-private-token"
    source = compile(
        "def _source_is_fresh():\n    raise TypeError(secret)\n",
        "/srv/backend/services/setup_market_match_service.py", "exec",
    )
    scope = {"secret": secret}
    exec(source, scope)
    try:
        scope["_source_is_fresh"]()
    except TypeError as error:
        code = probe._assessment_error_code(error)
    assert code == "typeerror_match_source"
    assert secret not in code and "92741" not in code
    safe = "trader_pair_outage_snapshot_assessment_typeerror_match_source_failed"
    assert profile_error_category("trader_pair_score_continuity", RuntimeError(safe)) == safe
    assert profile_error_category(
        "trader_pair_score_continuity", RuntimeError(safe + secret),
    ) == "trader_pair_probe_runtime_error"


def test_assessment_diagnostic_does_not_export_unlisted_python_error_text():
    secret = "private-sql-owner-8732"
    try:
        raise OSError(secret)
    except OSError as error:
        code = probe._assessment_error_code(error)
    assert code == "other_other"
    assert secret not in code


def test_probe_preserves_bounded_assessment_diagnostic_at_outage(monkeypatch):
    monkeypatch.setenv("FINN_QA_ALLOW_TRADER_PAIR_FIXTURE", "1")
    monkeypatch.setenv("FINN_QA_USER_ID", "7")
    monkeypatch.setattr(probe, "_markets", lambda: MARKETS)
    monkeypatch.setattr(probe.fixture, "_seed", lambda *_args: (11, 22, "today"))
    monkeypatch.setattr(probe, "_seed_pair_readings", lambda *_args: None)
    monkeypatch.setattr(probe, "_business_snapshot", _stable_business)
    snapshots = iter((_snapshot(45, 70), RuntimeError(
        "trader_pair_snapshot_assessment_typeerror_match_source_failed")))
    def snapshot(*_args):
        value = next(snapshots)
        if isinstance(value, Exception):
            raise value
        return value
    monkeypatch.setattr(probe, "_snapshot", snapshot)
    monkeypatch.setattr(probe, "_transport_checks", lambda *_args: {"analysis": True, "finn": True})
    monkeypatch.setattr(probe, "_set_eur_source_time", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(probe.fixture, "_quarantine", lambda *_args: None)
    with pytest.raises(RuntimeError, match="^trader_pair_outage_snapshot_assessment_typeerror_match_source_failed$"):
        probe.run(NAMESPACE)


def test_snapshot_keeps_missing_score_with_independent_stale_source_diagnosis(monkeypatch):
    from backend.celery_task import store_daily_scores_task

    now = datetime.now(timezone.utc)
    times = {1: now - timedelta(days=30), 2: now - timedelta(minutes=5)}
    class Cursor:
        def __enter__(self):
            return self
        def __exit__(self, *args):
            return None
        def execute(self, statement, params):
            self.market_id = params[1]
            self.is_source = "SELECT source_observed_at" in statement
        def fetchone(self):
            return (times[self.market_id],)
        def fetchall(self):
            return [("market", "change_24h")]
    class Connection:
        cursor_instance = Cursor()
        def cursor(self):
            return self.cursor_instance
        def close(self):
            return None
    monkeypatch.setattr(probe.fixture, "_connection", Connection)
    monkeypatch.setattr(store_daily_scores_task, "build_daily_scores_for_market",
                        lambda user_id, market_id: {
                            "scores": {"market": None if market_id == 1 else 60}
                        })
    async def assessment(user_id, market_id):
        return ({"source_status": "missing_scores", "benchmark_score": None,
                 "component_source_status": {"market_score": "missing_score"}}
                if market_id == 1 else
                {"source_status": "available", "benchmark_score": 70,
                 "component_source_status": {"market_score": "fresh"}})
    monkeypatch.setattr(probe, "_assessment", assessment)
    snapshot = probe._snapshot(11, MARKETS)["pairs"]
    assert snapshot["BTC/EUR"]["source_status"] == "missing_score"
    assert snapshot["BTC/EUR"]["fixture_source_diagnosis"] == "stale_source"
    assert snapshot["BTC/EUR"]["stale_reading_proven"] is True
    assert snapshot["BTC/USDT"]["fixture_source_diagnosis"] == "fresh"
