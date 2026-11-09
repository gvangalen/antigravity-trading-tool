"""Synthetic source refs only; the protected collector never contacts production here."""

import asyncio
from datetime import datetime, timezone

import pytest

from backend.scripts import probe_protected_source_time_parity as probe
from backend.scripts.run_finn_production_qa import profile_error_category


REF = {"market_id": 43, "measurement_id": 987,
       "source_observed_at_utc": "2026-11-08T09:30:00+00:00"}


def test_ref_validation_normalizes_offset_and_rejects_incomplete_identity():
    assert probe._normalized_ref({**REF,
        "source_observed_at_utc": "2026-11-08T10:30:00+01:00"}) == (
        43, 987, datetime(2026, 11, 8, 9, 30, tzinfo=timezone.utc),
    )
    assert probe._normalized_ref({**REF, "measurement_id": None}) is None
    assert probe._normalized_ref({**REF, "source_observed_at_utc": "2026-11-08T09:30:00"}) is None


def test_source_parity_runner_error_is_sanitized():
    assert profile_error_category("trader_source_time_parity", RuntimeError(
        "private market 987 secret-token")) == "paper_exit_probe_runtime_error"
    assert profile_error_category("trader_source_time_parity", RuntimeError(
        "paper_exit_source_parity_failed")) == "paper_exit_source_parity_failed"


def test_report_path_persists_the_product_snapshot_reference(monkeypatch):
    from backend.infrastructure import database
    from backend.infrastructure.repositories import daily_report_repository
    from backend.services import finn_unified_report_service

    saved = {}
    class Session:
        def commit(self):
            saved["committed"] = True
        def rollback(self):
            raise AssertionError("unexpected rollback")
        def close(self):
            pass
    class Writer:
        JSONB_FIELDS = ("score_source_snapshot",)
        def __init__(self, _session):
            pass
        def upsert_daily_report(self, **kwargs):
            saved.update(kwargs)
    monkeypatch.setattr(database, "SessionLocal", Session)
    monkeypatch.setattr(daily_report_repository, "DailyReportWriteRepository", Writer)
    monkeypatch.setattr(finn_unified_report_service,
        "generate_unified_daily_report_sections", lambda **_: {
            "score_source_snapshot": {"assets": [{"market_id": 43, "pair": "BTC/USDT",
                "market_snapshot": {"source_ref": REF}}]},
        })
    snapshot = probe._saved_report(7)
    assert saved["user_id"] == 7 and saved["committed"] is True
    assert saved["sections"]["score_source_snapshot"] == snapshot
    assert snapshot["assets"][0]["market_snapshot"]["source_ref"] == REF


def test_four_surface_collector_returns_only_fixed_checks(monkeypatch):
    def read_json(*, owner_id, path):
        assert owner_id == 7
        if path.startswith("/api/workspace/"):
            return {"market_id": 43, "quote": {"source_ref": REF,
                "as_of": REF["source_observed_at_utc"]}}
        assert path.startswith("/api/report/daily/latest")
        return {"score_source_snapshot": {"assets": [
            {"market_id": 43, "pair": "BTC/USDT", "market_snapshot": {"source_ref": REF,
                "as_of": REF["source_observed_at_utc"]}},
        ]}}

    async def finn(_owner):
        return {"source_ref": REF, "as_of": REF["source_observed_at_utc"]}

    async def browser(_owner, _source):
        return {f"{surface}_{zone}": True for surface in ("analysis", "report")
                for zone in ("amsterdam", "new_york", "tokyo")}

    monkeypatch.setattr(probe, "read_json", read_json)
    monkeypatch.setattr(probe, "_saved_report", lambda _owner: {})
    monkeypatch.setattr(probe, "_finn_market_read", finn)
    monkeypatch.setattr(probe, "_rendered_quote_times", browser)
    evidence = {"ui_projection": {"source_ref": REF,
               "source_price_at": REF["source_observed_at_utc"]}}
    result = probe.run(user_id=7, market_id=43,
                       paper_evidence=evidence, frozen_ref=REF)
    assert result["result"] == "PASS" and result["failed_checks"] == []
    assert result["gate_status"] == "PASS" and result["browser_zones_checked"] == 6
    assert all(result["browser_zone_checks"].values())
    assert all(result["surface_display_checks"].values())
    assert result["parity_subchecks"] == []
    assert "987" not in str(result) and "2026" not in str(result)

    def wrong_analysis(*, owner_id, path):
        value = read_json(owner_id=owner_id, path=path)
        if path.startswith("/api/workspace/"):
            value["quote"]["source_ref"] = {**REF, "measurement_id": 988}
        return value

    monkeypatch.setattr(probe, "read_json", wrong_analysis)
    failed = probe.run(user_id=7, market_id=43,
                       paper_evidence=evidence, frozen_ref=REF)
    assert failed["failed_checks"] == ["analysis_source", "four_instant_display"] or (
        failed["failed_checks"] == ["analysis_source"]
    )
    assert "988" not in str(failed)

    monkeypatch.setattr(probe, "read_json", read_json)
    async def refreshed_browser(_owner, _source):
        return {f"{surface}_{zone}": (
            "page_source_changed" if surface == "analysis" and zone == "amsterdam" else "ok"
        ) for surface in ("analysis", "report")
            for zone in ("amsterdam", "new_york", "tokyo")}
    monkeypatch.setattr(probe, "_rendered_quote_times", refreshed_browser)
    inconclusive = probe.run(user_id=7, market_id=43,
                             paper_evidence=evidence, frozen_ref=REF)
    assert inconclusive["result"] == "INCONCLUSIVE"
    assert inconclusive["failed_checks"] == ["page_source_changed"]
    assert inconclusive["browser_zone_phases"]["analysis_amsterdam"] == "page_source_changed"


def test_browser_checks_classify_page_source_refresh_without_leaking_payload(monkeypatch):
    from backend.scripts import qa_protected_browser
    from backend.utils import auth_utils

    monkeypatch.setattr(auth_utils, "create_access_token", lambda *_args: "private-token")
    seen_locales = []

    class Response:
        status = 200
        def __init__(self, path, payload):
            self.url = "https://tradamind.com" + path
            self.payload = payload
        async def json(self):
            return self.payload

    class Locator:
        async def wait_for(self, **_kwargs):
            return None

    class Page:
        async def evaluate(self, _script, args):
            seen_locales.append(args[1])
            return "visible UTC"
        def get_by_text(self, *_args, **_kwargs):
            return type("Match", (), {"first": Locator()})()

    calls = 0
    def selected_workspace(*, owner_id, path):
        assert owner_id == 7
        assert path == "/api/workspace/exact-market?symbol=BTC&quote_currency=USDT"
        source = ({**REF, "source_observed_at_utc": "2026-11-08T09:31:00+00:00"}
                  if calls == 1 else REF)
        return {"market_id": 43, "pair": "BTC/USDT", "quote": {
            "source_ref": source, "private": "private-fixture-value",
        }}

    async def observe_page(*, path, inspect, observe_response,
                           fixture_exact_selection=None, **_kwargs):
        nonlocal calls
        calls += 1
        if path.startswith("/asset"):
            assert fixture_exact_selection is not None
            payload = fixture_exact_selection()
            api_path = "/api/assets/BTC/trading-markets/USDT/select?include_workspace=true"
        else:
            assert fixture_exact_selection is None
            payload = {"score_source_snapshot": {"content_locale": "en", "assets": [
                {"pair": "BTC/USDT", "market_snapshot": {"source_ref": REF}},
            ]}}
            api_path = "/api/report/daily/latest"
        observe_response(Response(api_path, payload))
        return await inspect(Page())

    monkeypatch.setattr(qa_protected_browser, "observe_page", observe_page)
    monkeypatch.setattr(probe, "read_json", selected_workspace)
    async def visible(*_args, **_kwargs):
        return "ok"
    monkeypatch.setattr(probe, "_target_quote_visible", visible)
    phases = asyncio.run(probe._rendered_quote_times(7, REF))
    assert phases["analysis_amsterdam"] == "page_source_changed"
    assert all(value == "ok" for key, value in phases.items() if key != "analysis_amsterdam")
    assert seen_locales.count("en-US") == 3
    assert "private-token" not in str(phases)
    assert "private-fixture-value" not in str(phases)


def test_target_quote_selector_rejects_duplicate_time_outside_btc_usdt_card():
    class Locator:
        def __init__(self, scope, *, count=1):
            self.scope, self._count = scope, count
            self.first = self
        async def count(self):
            return self._count
        def locator(self, selector):
            return Locator(f"{self.scope}/{selector}")
        def filter(self, **_kwargs):
            return self
        def get_by_text(self, text, **_kwargs):
            if getattr(text, "pattern", "") == r"\bUSDT\b":
                return Locator(f"{self.scope}/currency")
            return Locator(f"{self.scope}/target_time", count=0)
        async def wait_for(self, **_kwargs):
            if "target_time" in self.scope:
                raise TimeoutError("duplicate exists elsewhere, target absent")

    class Page:
        def get_by_text(self, text, **_kwargs):
            # A page-wide time locator would succeed; the target card does not.
            return Locator("page/time" if "UTC" in text else "page/active_anchor")
        def get_by_role(self, *_args, **_kwargs):
            return Locator("page/heading")
        def locator(self, selector):
            return Locator(f"page/{selector}")

    page = Page()
    assert asyncio.run(probe._target_quote_visible(
        page, surface="analysis", locale="nl-NL", expected="8 nov 2026 09:30 UTC",
    )) == "selector_missing"
    assert asyncio.run(probe._target_quote_visible(
        page, surface="report", locale="nl-NL", expected="8 nov 2026 09:30 UTC",
    )) == "selector_missing"


def test_real_playwright_dom_scopes_both_quote_timestamps():
    playwright = pytest.importorskip("playwright.async_api")
    expected = "8 nov 2026 09:30 UTC"

    async def exercise():
        async with playwright.async_playwright() as runtime:
            try:
                browser = await runtime.chromium.launch(headless=True, args=["--no-sandbox"])
            except playwright.Error:
                pytest.skip("Chromium is unavailable in this test environment")
            try:
                page = await browser.new_page()
                await page.set_content(f"""
                    <p>{expected}</p>
                    <section><div>Actieve analyse</div><div>Koers van <span>{expected}</span></div>
                      <span>BTC</span><span>76.100 USDT</span></section>
                """)
                assert await probe._target_quote_visible(
                    page, surface="analysis", locale="nl-NL", expected=expected,
                    timeout_ms=150,
                ) == "ok"
                await page.set_content(f"""
                    <p>{expected}</p>
                    <section><div>Actieve analyse</div><div>Koers van <span>ander moment</span></div>
                      <span>BTC</span><span>76.100 USDT</span></section>
                """)
                assert await probe._target_quote_visible(
                    page, surface="analysis", locale="nl-NL", expected=expected,
                    timeout_ms=150,
                ) == "selector_missing"
                await page.set_content(f"""
                    <p>{expected}</p>
                    <div class="report-v2-at-glance-item"><h3>BTC/USDT · Benchmark</h3>
                      <dl><div><dt>Koersbron: </dt><dd>{expected} · 2 h</dd></div></dl>
                    </div>
                """)
                assert await probe._target_quote_visible(
                    page, surface="report", locale="nl-NL", expected=expected,
                    timeout_ms=150,
                ) == "ok"
                await page.set_content(f"""
                    <p>{expected}</p>
                    <div class="report-v2-at-glance-item"><h3>BTC/USDT · Benchmark</h3>
                      <dl><div><dt>Koersbron: </dt><dd>ander moment</dd></div></dl>
                    </div>
                """)
                assert await probe._target_quote_visible(
                    page, surface="report", locale="nl-NL", expected=expected,
                    timeout_ms=150,
                ) == "selector_missing"
            finally:
                await browser.close()

    asyncio.run(exercise())


def test_real_playwright_dom_binds_eur_quote_inside_active_card():
    playwright = pytest.importorskip("playwright.async_api")
    expected = "9 nov 2026 09:12 UTC"

    async def exercise():
        async with playwright.async_playwright() as runtime:
            try:
                browser = await runtime.chromium.launch(headless=True, args=["--no-sandbox"])
            except playwright.Error:
                pytest.skip("Chromium is unavailable in this test environment")
            try:
                page = await browser.new_page()
                await page.set_content(f"""
                    <p>{expected}</p>
                    <section><div>Actieve analyse</div><span>68.000 EUR</span>
                      <span>{expected}</span></section>
                """)
                assert await probe._target_quote_visible(
                    page, surface="analysis", locale="nl-NL", expected=expected,
                    quote_currency="EUR", timeout_ms=150,
                ) == "ok"
                assert await probe._target_quote_visible(
                    page, surface="analysis", locale="nl-NL", expected=expected,
                    quote_currency="USDT", timeout_ms=150,
                ) == "selector_missing"
            finally:
                await browser.close()

    asyncio.run(exercise())
