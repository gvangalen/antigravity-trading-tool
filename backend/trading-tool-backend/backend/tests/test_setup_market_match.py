import asyncio
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

from backend.domain.setup_market_match import match_setup, match_setup_from_daily_scores, rank_matches
from backend.services.setup_market_match_service import SetupMarketMatchService
from backend.services.finn_v2_responses_tool_catalog import FinnResponsesToolCatalog
from backend.services import finn_v2_tool_execution_service as execution_module
from backend.engine.policy_engine import evaluate_policy
from backend.engine.decision_engine import decide_amount
from backend.services import setup_market_match_sync
from backend.services.report_service import ReportService
from backend.services.finn_v2_tool_adapters.setup_tool_adapter import SetupToolAdapter
from backend.services.finn_v2_tool_adapters.setup_inventory_tool_adapter import SetupInventoryToolAdapter
from backend.services.finn_v2_tool_adapters.market_tool_adapter import MarketToolAdapter


def setup(setup_id, symbol="BTC", **conditions):
    return {"id": setup_id, "name": f"Setup {setup_id}", "symbol": symbol,
            "timeframe": "4H", "setup_type": "trade", **conditions}


def test_legacy_report_metadata_cannot_restore_retired_setup_score():
    service = ReportService(SimpleNamespace())
    old = {
        "setup_score": 88,
        "best_setup": {"name": "Old AI pick", "score": 88},
        "top_setups": [{"name": "Old AI pick", "score": 88}],
        "meta_json": {"setup_score": 88, "best_setup": {"name": "Old AI pick"},
                      "top_setups": [{"name": "Old AI pick"}]},
    }
    marked = service._mark_daily_setup_semantics(old)
    mobile = service.format_report_for_mobile(marked)
    assert marked["setup_score"] is None
    assert mobile["kpi_metrics"]["setup_score"] is None
    assert mobile["best_setup"] is None
    assert mobile["top_setups"] == []


def test_rank_only_marks_a_matching_setup_as_best():
    scores = {"macro": 50, "technical": 75, "market": 70}
    rows = rank_matches([
        setup(1, min_macro_score=80),
        setup(2, min_macro_score=40, max_macro_score=60,
              min_technical_score=70, max_technical_score=90),
    ], scores)
    assert [row["setup_id"] for row in rows] == [2, 1]
    assert rows[0]["status"] == "matches"
    assert rows[0]["is_best"] is True
    assert rows[1]["status"] == "outside_conditions"
    assert rows[1]["is_active"] is False


def test_weakest_setup_is_not_automatically_active():
    rows = rank_matches([setup(1, min_market_score=90), setup(2, min_macro_score=90)],
                        {"macro": 20, "technical": 50, "market": 20})
    assert all(row["is_best"] is False and row["is_active"] is False for row in rows)


def test_a_valid_boundary_is_not_displayed_as_zero_percent_match():
    matched = match_setup(setup(1, min_market_score=40, max_market_score=60),
                          {"macro": 50, "technical": 50, "market": 40})
    outside = match_setup(setup(2, min_market_score=40, max_market_score=60),
                          {"macro": 50, "technical": 50, "market": 39.9})
    assert matched["status"] == "matches" and matched["score"] == 60
    assert outside["status"] == "outside_conditions" and outside["score"] <= 59


def test_missing_data_and_unconfigured_conditions_have_no_match_score():
    configured = setup(1, min_market_score=40)
    assert match_setup(configured, None)["status"] == "insufficient_data"
    assert match_setup(configured, None)["conditions"]["market"] == {
        "minimum": 40.0, "maximum": None,
    }
    assert match_setup(configured, {"macro": 50, "technical": None, "market": 60})["score"] is None
    assert match_setup(setup(2), {"macro": 50, "technical": 50, "market": 50})["status"] == "unconfigured"


def test_finn_setup_reads_preserve_boundaries_without_selecting_a_strategy():
    async def run():
        saved = setup(9, min_market_score=20, max_market_score=60,
                      min_macro_score=30, max_macro_score=70,
                      min_technical_score=40, max_technical_score=80)
        active = (await SetupToolAdapter().execute(
            setup=saved, resolution_source="explicit_name",
        ))["data"]
        listed = (await SetupInventoryToolAdapter().execute(setups=[saved]))["data"].setups[0]
        assert (active.min_market_score, active.max_market_score) == (20, 60)
        assert (active.min_macro_score, active.max_macro_score) == (30, 70)
        assert (active.min_technical_score, active.max_technical_score) == (40, 80)
        assert listed["min_market_score"] == 20
        assert listed["max_technical_score"] == 80

    asyncio.run(run())


def test_finn_can_read_same_reported_market_score_as_analyse_without_a_complete_benchmark():
    async def run():
        today = date.today()
        row = {"report_date": today, "macro_score": None,
               "technical_score": None, "market_score": 100}
        session = SimpleNamespace(execute=AsyncMock(return_value=SimpleNamespace(
            mappings=lambda: SimpleNamespace(first=lambda: row))))
        service = SetupMarketMatchService(session)
        service._source_is_fresh = AsyncMock(return_value=True)
        result = await service.for_asset(7, "BTC", setups=[setup(9, min_market_score=20)])
        assert result["reported_scores"]["market_score"] == 100
        assert result["benchmark_score"] is None
        assert result["matches"][0]["conditions"]["market"]["minimum"] == 20

        adapter = MarketToolAdapter(SimpleNamespace())
        adapter.repository.get_latest_snapshot = AsyncMock(return_value=SimpleNamespace(
            symbol="BTC", price=100000, change_24h=1, volume=100,
            timestamp=datetime.now(timezone.utc),
        ))
        adapter.scores.fetch_daily_scores = AsyncMock(return_value=row)
        market = await adapter.execute(asset="BTC", user_id=7)
        assert market["data"].saved_market_score == 100
        assert market["data"].score_report_date == today
        adapter.scores.fetch_daily_scores.assert_awaited_once_with(7, "BTC")

        adapter.repository.get_latest_snapshot = AsyncMock(return_value=None)
        score_only = await adapter.execute(asset="BTC", user_id=7)
        assert score_only["data"].saved_market_score == 100
        assert score_only["data"].price is None
        assert score_only["source"] == "daily_scores"

    asyncio.run(run())


def test_setup_fit_uses_current_benchmark_weights_but_preserves_hard_conditions():
    conditions = setup(1, min_macro_score=40, max_macro_score=60,
                       min_market_score=40, max_market_score=80)
    scores = {"macro": 50, "technical": 50, "market": 80}
    weights = {"macro_score": 0.8, "market_score": 0.2, "technical_score": 0.0}
    weighted = match_setup(conditions, scores, weights)
    equal = match_setup(conditions, scores)
    assert weighted["score"] == 92
    assert equal["score"] == 80
    assert weighted["status"] == "matches"
    outside = match_setup(conditions, {**scores, "market": 81}, weights)
    assert outside["status"] == "outside_conditions"
    assert outside["is_active"] is False


def test_total_benchmark_is_distinct_from_setup_fit():
    async def run():
        pref = {"ai_preferences": {"intelligence_weights": {
            "market": 0.2, "macro": 0.8, "technical": 0.0}}}
        daily = {"report_date": date.today(), "macro_score": 50,
                 "technical_score": 50, "market_score": 80}
        session = SimpleNamespace(execute=AsyncMock(side_effect=[
            SimpleNamespace(mappings=lambda: SimpleNamespace(first=lambda: pref)),
            SimpleNamespace(mappings=lambda: SimpleNamespace(first=lambda: daily)),
        ]))
        service = SetupMarketMatchService(session)
        service._source_is_fresh = AsyncMock(return_value=True)
        assessment = await service.for_asset(7, "BTC", setups=[
            setup(1, min_macro_score=40, max_macro_score=60,
                  min_market_score=40, max_market_score=80)])
        assert assessment["benchmark_score"] == 56.0
        assert assessment["matches"][0]["score"] == 92
        assert assessment["matches"][0]["benchmark_weights"]["macro_score"] == 0.8

    asyncio.run(run())


def test_batch_reader_does_not_relabel_yesterdays_score_as_current():
    async def run():
        session = SimpleNamespace(execute=AsyncMock(return_value=SimpleNamespace(
            mappings=lambda: SimpleNamespace(first=lambda: {"ai_preferences": None}),
        )))
        service = SetupMarketMatchService(session, daily_rows={
            "BTC": {"report_date": date.today() - timedelta(days=1),
                    "macro_score": 70, "technical_score": 70, "market_score": 70},
        })
        service._source_is_fresh = AsyncMock(return_value=True)
        result = await service.for_asset(7, "BTC", setups=[setup(1, min_market_score=60)])
        assert result["source_status"] == "stale_scores"
        assert result["benchmark_score"] is None
        assert result["matches"][0]["status"] == "insufficient_data"
        service._source_is_fresh.assert_not_awaited()

    asyncio.run(run())


def test_bot_and_report_score_adapter_requires_fresh_complete_sources():
    conditions = setup(9, min_market_score=40, max_market_score=80)
    values = {"market": 70, "macro": 50, "technical": 60,
              "_source_available": {"market_score": True, "macro_score": True,
                                    "technical_score": True}}
    weights = {"market_score": 0.5, "macro_score": 0.25, "technical_score": 0.25}
    measured = match_setup_from_daily_scores(conditions, values, weights)
    assert measured["status"] == "matches"
    assert measured["score"] is not None
    stale = match_setup_from_daily_scores(conditions, {
        **values, "_source_available": {**values["_source_available"], "market_score": False},
    }, weights)
    assert stale["status"] == "insufficient_data"
    assert stale["score"] is None


def test_sync_report_adapter_uses_same_owner_scoped_match_and_weights(monkeypatch):
    class Connection:
        def cursor(self):
            return self

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

        def execute(self, sql, params):
            assert params[0] == 7
            if "FROM users" in sql:
                self.row = ({"intelligence_weights": {
                    "macro": 0.8, "market": 0.2, "technical": 0}},)
            elif "FROM daily_scores" in sql:
                assert params == (7, "BTC")
                self.row = (date.today(), 50, 50, 80)
            elif "FROM setups" in sql:
                assert params == (7, "BTC")
                self.rows = [tuple(setup(1, min_macro_score=40, max_macro_score=60,
                                         min_market_score=40, max_market_score=80).get(key)
                                   for key in setup_market_match_sync.SETUP_COLUMNS)]
            else:
                raise AssertionError(sql)

        def fetchone(self):
            return self.row

        def fetchall(self):
            return self.rows

    monkeypatch.setattr(setup_market_match_sync, "_fresh", lambda *_: True)
    result = setup_market_match_sync.current_setup_market_assessment(Connection(), 7, "BTC")
    assert result["benchmark_score"] == 56
    assert result["matches"][0]["score"] == 92
    assert result["matches"][0]["is_best"] is True


def test_historical_ai_setup_score_is_not_served_as_current_match():
    old = ReportService._mark_daily_setup_semantics({
        "setup_score": 91, "best_setup": {"name": "Old AI choice"},
        "top_setups": [{"name": "Old AI choice", "score": 91}],
    })
    assert old["setup_score"] is None
    assert old["best_setup"] is None
    current = ReportService._mark_daily_setup_semantics({
        "setup_score": 76, "top_setups": [{
            "name": "Saved setup", "score": 76,
            "score_semantics": "benchmark_setup_match_v1",
        }],
    })
    assert current["setup_score"] == 76
    assert current["setup_score_semantics"] == "benchmark_setup_match_v1"


def test_setup_match_is_not_a_hard_bot_policy_gate():
    policy = evaluate_policy(
        scores={"market_score": 70, "macro_score": 70,
                "technical_score": 70, "setup_score": 20},
        transition_risk=0.2, market_pressure=0.6,
    )
    assert "buy" in policy["allowed_actions"]


def test_missing_match_does_not_apply_weak_setup_size_penalty():
    result = decide_amount(
        {"base_amount": 100, "execution_mode": "fixed"},
        {"market_score": 60, "macro_score": 60, "technical_score": 60},
    )
    assert result["sized_amount"] == 100


def test_finn_can_select_the_owner_scoped_match_read():
    catalog = FinnResponsesToolCatalog()
    call = catalog.validate("get_setup_market_matches", {"asset": "BTC"})
    assert call.read_tools == ("read_setup_market_matches",)
    definition = next(row for row in catalog.definitions()
                      if row.get("name") == "get_setup_market_matches")
    assert "entry" in definition["description"].lower()


def test_asset_match_is_owner_scoped_and_requires_fresh_sources():
    async def run():
        row = {"report_date": date.today(), "macro_score": 50,
               "technical_score": 75, "market_score": 70}
        session = SimpleNamespace(execute=AsyncMock(return_value=SimpleNamespace(
            mappings=lambda: SimpleNamespace(first=lambda: row))))
        service = SetupMarketMatchService(session)
        service._source_is_fresh = AsyncMock(return_value=True)
        owned = [setup(1, "BTC", min_market_score=60),
                 setup(2, "AAPL", min_market_score=60)]

        result = await service.for_asset(7, "BTC", setups=owned)
        assert result["source_status"] == "available"
        assert [item["setup_id"] for item in result["matches"]] == [1]
        assert result["matches"][0]["is_best"] is True

        service._source_is_fresh = AsyncMock(return_value=False)
        stale = await service.for_asset(7, "BTC", setups=owned)
        assert stale["source_status"] == "stale_sources"
        assert stale["matches"][0]["status"] == "insufficient_data"
        assert stale["matches"][0]["is_best"] is False

    asyncio.run(run())


def test_all_asset_match_keeps_each_asset_and_source_status():
    async def run():
        service = SetupMarketMatchService(SimpleNamespace(), daily_rows={})
        service.setups.get_all_setups = AsyncMock(return_value=[setup(1, "BTC"), setup(2, "AAPL")])

        async def for_asset(_user_id, symbol, *, setups):
            return {"as_of": date.today(), "source_status": "available" if symbol == "BTC" else "missing_scores",
                    "matches": [match_setup(row, {"macro": 50, "technical": 50, "market": 70}
                                            if symbol == "BTC" else None)
                                for row in setups if row["symbol"] == symbol]}

        service.for_asset = for_asset
        result = await service.for_all_assets(7)
        assert result["symbol"] == "ALL"
        assert {row["symbol"] for row in result["matches"]} == {"BTC", "AAPL"}
        assert {row["symbol"]: row["source_status"] for row in result["matches"]} == {
            "BTC": "available", "AAPL": "missing_scores"}

    asyncio.run(run())


def test_twenty_assets_keep_distinct_owner_setup_ids():
    async def run():
        owned = [setup(index, f"ASSET{index}", min_market_score=50)
                 for index in range(1, 21)]
        service = SetupMarketMatchService(SimpleNamespace(), daily_rows={})
        service.setups.get_all_setups = AsyncMock(return_value=owned)

        async def for_asset(_user_id, symbol, *, setups):
            selected = [item for item in setups if item["symbol"] == symbol]
            return {"as_of": date.today(), "source_status": "available",
                    "matches": rank_matches(selected, {"macro": 60, "technical": 60, "market": 60})}

        service.for_asset = for_asset
        result = await service.for_all_assets(7)
        assert len(result["matches"]) == 20
        assert {item["setup_id"]: item["symbol"] for item in result["matches"]} == {
            index: f"ASSET{index}" for index in range(1, 21)
        }

    asyncio.run(run())


def test_source_freshness_rejects_missing_configured_indicator():
    async def run():
        now = datetime.now(timezone.utc)
        results = [
            SimpleNamespace(fetchall=lambda: [("rsi",), ("macd",)]),
            SimpleNamespace(fetchall=lambda: [("rsi", now - timedelta(hours=1))]),
        ]
        session = SimpleNamespace(execute=AsyncMock(side_effect=results))
        service = SetupMarketMatchService(session)
        assert await service._source_is_fresh(7, "BTC", "technical") is False

    asyncio.run(run())


def test_finn_match_tool_returns_scoped_typed_evidence(monkeypatch):
    async def run():
        service = object.__new__(execution_module.FinnV2ToolExecutionService)
        service.session = object()

        async def asset(**_kwargs):
            return {"asset": "BTC"}

        async def assessment(_user_id, _symbol):
            return {"symbol": "BTC", "as_of": date.today(), "source_status": "available",
                    "matches": [match_setup(setup(1, min_market_score=50),
                                            {"macro": 50, "technical": 50, "market": 70})]}

        service._ensure_asset = asset
        monkeypatch.setattr(execution_module, "SetupMarketMatchService",
                            lambda _session: SimpleNamespace(for_asset=assessment))
        payload = await service._dispatch_tool(
            tool_name="read_setup_market_matches", user_id=7,
            selector={"asset": "BTC"}, run=SimpleNamespace(), shared_state={},
        )
        assert payload["schema_name"] == "SetupMarketMatchesData"
        assert payload["data"].matches[0]["status"] == "matches"
        assert payload["asset"] == "BTC"

    asyncio.run(run())


def test_finn_match_tool_can_read_all_owned_setup_assets(monkeypatch):
    async def run():
        service = object.__new__(execution_module.FinnV2ToolExecutionService)
        service.session = object()
        all_assets = AsyncMock(return_value={"symbol": "ALL", "as_of": None,
            "source_status": "per_asset", "matches": []})
        monkeypatch.setattr(execution_module, "SetupMarketMatchService",
                            lambda _session: SimpleNamespace(for_all_assets=all_assets))
        payload = await service._dispatch_tool(
            tool_name="read_setup_market_matches", user_id=7,
            selector={"asset": None}, run=SimpleNamespace(), shared_state={},
        )
        all_assets.assert_awaited_once_with(7)
        assert payload["data"].symbol == "ALL"

    asyncio.run(run())
