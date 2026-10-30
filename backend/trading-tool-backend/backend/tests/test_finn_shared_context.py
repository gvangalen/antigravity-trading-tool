import asyncio
import json
from datetime import datetime, timedelta, timezone
from contextlib import nullcontext
from types import SimpleNamespace
from unittest.mock import AsyncMock

from backend.services.finn_shared_context_service import FinnSharedContextService
from backend.services import finn_unified_report_service as reports
from backend.schemas.finn_v2_evidence_schema import IndicatorConfigurationData, IndicatorConfigurationItem
from backend.celery_task import daily_report_task
from backend.services.finn_v2_tool_adapters.score_tool_adapter import ScoreToolAdapter
from backend.services.report_service import ReportService
from backend.utils import pdf_playwright


def test_pdf_render_uses_deployed_frontend_origin(monkeypatch):
    monkeypatch.delenv("FRONTEND_BASE_URL", raising=False)
    monkeypatch.setenv("FRONTEND_URL", "https://tradamind.com/")
    assert pdf_playwright._frontend_base_url() == "https://tradamind.com"
    monkeypatch.setenv("FRONTEND_BASE_URL", "http://127.0.0.1:5002/")
    assert pdf_playwright._frontend_base_url() == "http://127.0.0.1:5002"


def test_report_source_times_keep_seconds_and_missing_values():
    assert reports._report_source_times({
        "macro": {"DXY": "2026-10-29T23:59:59.999999+00:00"},
        "technical": {"RSI": None},
    }) == {
        "macro": {"DXY": "2026-10-29T23:59:59+00:00"},
        "technical": {"RSI": None},
    }


class _Rows:
    def __init__(self, rows):
        self.rows = rows

    def fetchall(self):
        return self.rows


def test_shared_context_reads_twenty_owner_assets_without_turning_missing_scores_into_zero():
    symbols = [f"ASSET{i:02}" for i in range(20)]

    class _Session:
        async def execute(self, _query, params):
            assert params == {"user_id": 7}
            return _Rows([(symbol,) for symbol in symbols])

    service = FinnSharedContextService(_Session())
    service.users.get_by_id = AsyncMock(return_value=SimpleNamespace(ai_preferences={"locale": "nl"}))
    service.setups.get_all_setups = AsyncMock(return_value=[])
    service.strategies.query_strategies = AsyncMock(return_value=[])
    service.bots.get_bot_configs = AsyncMock(return_value=[])
    service.market_data.get_latest_snapshot = AsyncMock(return_value=None)
    service.benchmark_for_asset = AsyncMock(side_effect=lambda user_id, asset, **_: {
        "symbol": asset, "source_status": "missing_scores", "benchmark_score": None,
        "reported_scores": {"market_score": None, "macro_score": None, "technical_score": None},
        "matches": [],
    })
    service.indicators.execute = AsyncMock(return_value={
        "data": SimpleNamespace(model_dump=lambda **_: {"market": [], "macro": [], "technical": []}),
    })

    snapshot = asyncio.run(service.for_user(7))

    assert len(snapshot["assets"]) == 20
    assert {item["symbol"] for item in snapshot["assets"]} == set(symbols)
    assert all(item["benchmark"]["benchmark_score"] is None for item in snapshot["assets"])
    assert all(item["indicator_lookup_status"] == "available" for item in snapshot["assets"])
    assert service.benchmark_for_asset.await_count == 20


def test_shared_context_keeps_failed_indicator_lookup_unknown():
    class _Session:
        async def execute(self, _query, _params):
            raise AssertionError("explicit asset must not query watchlist")

    service = FinnSharedContextService(_Session())
    service.users.get_by_id = AsyncMock(return_value=SimpleNamespace(ai_preferences={"locale": "de"}))
    service.setups.get_all_setups = AsyncMock(return_value=[])
    service.strategies.query_strategies = AsyncMock(return_value=[])
    service.bots.get_bot_configs = AsyncMock(return_value=[])
    service.market_data.get_latest_snapshot = AsyncMock(return_value=None)
    service.benchmark_for_asset = AsyncMock(return_value={
        "source_status": "missing_scores", "benchmark_score": None, "matches": [],
    })
    service.indicators.execute = AsyncMock(side_effect=RuntimeError("provider unavailable"))

    snapshot = asyncio.run(service.for_user(7, symbol="ETH"))

    assert snapshot["assets"][0]["indicator_configuration"] is None
    assert snapshot["assets"][0]["indicator_lookup_status"] == "unknown"
    assert snapshot["assets"][0]["benchmark"]["benchmark_score"] is None


def test_shared_context_keeps_two_exact_quotes_separate(monkeypatch):
    class _Session:
        async def execute(self, _query, _params):
            return _Rows([("BTC", 41), ("BTC", 42), ("BTC", None)])

    service = FinnSharedContextService(_Session())
    service.users.get_by_id = AsyncMock(return_value=SimpleNamespace(ai_preferences={}))
    service.setups.get_all_setups = AsyncMock(return_value=[
        {"id": 1, "symbol": "BTC", "market_id": 41},
        {"id": 2, "symbol": "BTC", "market_id": 42},
    ])
    service.strategies.query_strategies = AsyncMock(return_value=[])
    service.bots.get_bot_configs = AsyncMock(return_value=[])
    service.market_data.get_latest_exact_market_snapshot = AsyncMock(return_value=None)
    service.benchmark_for_asset = AsyncMock(side_effect=lambda _owner, _symbol, **kwargs: {
        "benchmark_score": kwargs["market_id"], "reported_scores": {}, "matches": [],
    })

    class _Pairs:
        def __init__(self, _session):
            pass

        async def market(self, market_id):
            return SimpleNamespace(id=market_id, asset_symbol="BTC")

        async def rows(self, _user_id, _market):
            return []

    monkeypatch.setattr("backend.services.finn_shared_context_service.PairIndicatorConfigService", _Pairs)
    snapshot = asyncio.run(service.for_user(7))
    assert [(asset["market_id"], asset["benchmark"]["benchmark_score"])
            for asset in snapshot["assets"]] == [(41, 41), (42, 42)]
    assert [[setup["id"] for setup in asset["setups"]] for asset in snapshot["assets"]] == [[1], [2]]


def test_report_context_uses_a_scoped_connection_without_disposing_the_api_pool(monkeypatch):
    disposed = []

    class _Engine:
        async def dispose(self):
            disposed.append(True)

    class _Session:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

    class _Sessions:
        def __call__(self):
            return _Session()

    monkeypatch.setattr(reports, "create_async_engine", lambda url, **kwargs: _Engine())
    monkeypatch.setattr(reports, "async_sessionmaker", lambda engine, **kwargs: _Sessions())
    monkeypatch.setattr(reports, "FinnSharedContextService", lambda session: SimpleNamespace(
        for_user=AsyncMock(return_value={"assets": []}),
    ))

    assert asyncio.run(reports._load_context(7)) == {"assets": []}
    assert disposed == [True]


def test_shared_context_serializes_real_indicator_schema_without_losing_configuration():
    class _Session:
        async def execute(self, _query, _params):
            raise AssertionError("explicit asset must not query watchlist")

    service = FinnSharedContextService(_Session())
    service.users.get_by_id = AsyncMock(return_value=SimpleNamespace(ai_preferences={"locale": "nl"}))
    service.setups.get_all_setups = AsyncMock(return_value=[])
    service.strategies.query_strategies = AsyncMock(return_value=[])
    service.bots.get_bot_configs = AsyncMock(return_value=[])
    service.market_data.get_latest_snapshot = AsyncMock(return_value=SimpleNamespace(
        source_observed_at=datetime.now(timezone.utc), price=61234.5,
        change_24h=1.2, volume=12345,
    ))
    service.benchmark_for_asset = AsyncMock(return_value={
        "source_status": "missing_scores", "benchmark_score": None, "matches": [],
    })
    service.indicators.execute = AsyncMock(return_value={"data": IndicatorConfigurationData(
        symbol="ETH", market=[IndicatorConfigurationItem(indicator="Price", category="market")],
        macro=[IndicatorConfigurationItem(indicator="DXY", category="macro")],
        technical=[IndicatorConfigurationItem(indicator="RSI", category="technical")],
    )})

    snapshot = asyncio.run(service.for_user(7, symbol="ETH"))
    asset = snapshot["assets"][0]
    assert asset["indicator_lookup_status"] == "available"
    assert [asset["indicator_configuration"][category][0]["indicator"]
            for category in ("market", "macro", "technical")] == ["Price", "DXY", "RSI"]
    assert asset["market_snapshot"]["source_status"] == "fresh"
    assert asset["market_snapshot"]["price"] == 61234.5

    service.market_data.get_latest_snapshot.return_value.source_observed_at = (
        datetime.now(timezone.utc) - timedelta(days=10)
    )
    stale = asyncio.run(service.for_user(7, symbol="ETH"))
    assert stale["assets"][0]["market_snapshot"]["source_status"] == "stale_or_missing"
    assert stale["assets"][0]["market_snapshot"]["price"] is None


def test_unified_report_uses_shared_benchmark_and_does_not_claim_missing_score(monkeypatch):
    context = {
        "locale": "nl", "profile": {}, "observed_at": "2026-10-07T12:00:00+00:00",
        "assets": [{
            "symbol": "BTC", "setups": [], "strategies": [], "bots": [],
            "indicator_configuration": {
                "market": [{"indicator": "price"}],
                "macro": [{"indicator": "dxy"}],
                "technical": [{"indicator": "rsi"}],
            },
            "benchmark": {
                "source_status": "missing_scores", "benchmark_score": None,
                "reported_scores": {"market_score": None, "macro_score": None, "technical_score": None},
                "matches": [],
            },
        }],
    }

    async def _load(_user_id):
        return context

    monkeypatch.setattr(reports, "_load_context", _load)
    prompts = []
    def _model_stub(**kwargs):
        prompts.append(json.loads(kwargs["prompt"]))
        return {"error": "provider_unavailable"}
    monkeypatch.setattr(reports, "ask_gpt_json", _model_stub)

    result = reports.generate_unified_daily_report_sections(7)

    assert result["market_score"] is None
    assert result["setup_score"] is None
    assert "geen bevestigde setupmatch" in result["setup_validation"]
    assert result["watchlist"][0]["benchmark"]["benchmark_score"] is None
    assert result["meta"]["source"] == "finn_shared_context.v1"
    assert "Ingesteld: Prijs" in result["market_analysis"]
    assert "Ingesteld: DXY" in result["macro_context"]
    assert "Ingesteld: RSI" in result["technical_analysis"]
    assert "Ingesteld: price" not in result["market_analysis"]
    assert prompts[0]["context"]["assets"][0]["configured_indicators"] == {
        "market": ["Prijs"], "macro": ["DXY"], "technical": ["RSI"],
    }


def test_chat_and_report_project_the_same_verified_score_snapshot(monkeypatch):
    assessment = {
        "symbol": "ETH", "as_of": "2026-10-10", "source_status": "available",
        "benchmark_score": 70,
        "benchmark_weights": {"market_score": 1 / 3, "macro_score": 1 / 3, "technical_score": 1 / 3},
        "reported_scores": {"market_score": 80, "macro_score": 70, "technical_score": 60},
        "component_source_status": {
            "market_score": "fresh", "macro_score": "fresh", "technical_score": "fresh",
        },
        "component_source_observed_at": {
            "market": {"Price": "2026-10-10T05:30:00+00:00"},
            "macro": {"DXY": "2026-10-09T23:59:59+00:00"},
            "technical": {"RSI": "2026-10-10T05:25:00+00:00"},
        },
        "matches": [{"setup_id": 9, "name": "ETH Plan", "symbol": "ETH",
                     "status": "matches", "score": 80, "is_active": True,
                     "components": {}}],
    }
    context = {
        "locale": "nl", "profile": {}, "observed_at": "2026-10-10T05:31:00+00:00", "assets": [{
            "symbol": "ETH", "benchmark": assessment,
            "setups": [{"id": 9, "name": "ETH Plan", "symbol": "ETH", "timeframe": "1D"}],
            "strategies": [{"id": 10, "setup_id": 9, "name": "ETH Strategy"}],
            "bots": [], "indicator_lookup_status": "available",
            "indicator_configuration": {"market": [], "macro": [], "technical": []},
        }],
    }
    source = SimpleNamespace(benchmark_for_asset=AsyncMock(return_value=assessment))
    chat_adapter = ScoreToolAdapter(object())
    chat_adapter.context = source
    chat = asyncio.run(chat_adapter.execute(user_id=7, asset="ETH"))["data"]

    monkeypatch.setattr(reports, "_load_context", lambda _id: asyncio.sleep(0, result=context))
    monkeypatch.setattr(reports, "ask_gpt_json", lambda **_: {"error": "provider_unavailable"})
    report = reports.generate_unified_daily_report_sections(7)

    assert chat.benchmark_score == report["watchlist"][0]["benchmark"]["benchmark_score"] == 70
    assert chat.reported_scores["market_score"] == report["watchlist"][0]["benchmark"]["reported_scores"]["market_score"] == 80
    assert (report["market_score"], report["macro_score"], report["technical_score"]) == (80, 70, 60)
    assert report["setup_score"] == 80
    assert report["active_strategy"]["strategy_name"] == "ETH Strategy"
    assert report["active_strategy"]["setup_name"] == "ETH Plan"
    assert "alle gevolgde assets" in report["setup_validation"]
    assert report["best_setup"]["name"] == "ETH Plan"
    source_snapshot = report["score_source_snapshot"]
    assert source_snapshot["observed_at"] == "2026-10-10T05:31:00+00:00"
    assert source_snapshot["content_locale"] == "nl"
    assert source_snapshot["assets"][0]["reported_scores"] == assessment["reported_scores"]
    assert source_snapshot["assets"][0]["component_source_observed_at"]["market"]["Price"] == "2026-10-10T05:30:00+00:00"
    assert source_snapshot["assets"][0]["score_report_date"] == "2026-10-10"
    # The persisted report reader must retain this measured match. Without
    # provenance it treats the new report as an old AI-score snapshot and
    # clears the side card despite the matching setup in the prose.
    served = ReportService._mark_daily_setup_semantics(report)
    assert served["setup_score_semantics"] == "benchmark_setup_match_v1"
    assert served["best_setup"]["name"] == "ETH Plan"
    assert served["top_setups"][0]["score_semantics"] == "benchmark_setup_match_v1"


def test_daily_report_uses_dated_fresh_price_and_distinct_strategy_name(monkeypatch):
    now = datetime.now(timezone.utc)
    context = {"locale": "nl", "assets": [{
        "symbol": "BTC",
        "benchmark": {"source_status": "missing_scores", "matches": []},
        "market_snapshot": {"source_status": "fresh", "as_of": now.isoformat(),
                            "price": 61234.5, "change_24h": 1.2, "volume": 12345},
        "setups": [{"id": 9, "name": "BTC Setup", "timeframe": "4H"}],
        "strategies": [{"id": 10, "setup_id": 9, "name": "BTC Strategy",
                        "entry": 60000, "stop_loss": 58000, "targets": [65000]}],
        "bots": [],
    }]}
    monkeypatch.setattr(reports, "_load_context", lambda _id: asyncio.sleep(0, result=context))
    monkeypatch.setattr(reports, "ask_gpt_json", lambda **_: {})
    report = reports.generate_unified_daily_report_sections(7)
    assert (report["price"], report["change_24h"], report["volume"]) == (61234.5, 1.2, 12345)
    assert report["active_strategy"]["strategy_name"] == "BTC Strategy"
    assert report["active_strategy"]["setup_name"] == "BTC Setup"
    assert report["active_strategy"]["timeframe"] == "4H"
    assert report["active_strategy"]["entry"] == 60000

    context["assets"][0]["market_snapshot"]["source_status"] = "stale_or_missing"
    assert reports.generate_unified_daily_report_sections(7)["price"] is None


def test_daily_report_keeps_pair_identity_in_scores_and_bot_prose(monkeypatch):
    def asset(pair, market_score):
        return {
            "symbol": "BTC", "pair": pair, "market_id": 41 if pair == "BTC/EUR" else 42,
            "benchmark": {
                "source_status": "available", "benchmark_score": market_score,
                "reported_scores": {"market_score": market_score, "macro_score": 60,
                                    "technical_score": 70},
                "component_source_status": {"market_score": "fresh", "macro_score": "fresh",
                                            "technical_score": "fresh"},
                "matches": [],
            },
            "indicator_configuration": {"market": [], "macro": [], "technical": []},
            "setups": [], "strategies": [],
            "bots": [{"id": 41 if pair == "BTC/EUR" else 42, "name": "Paper bot",
                      "is_live": False, "is_active": True}],
        }

    context = {"locale": "nl", "assets": [asset("BTC/EUR", 40), asset("BTC/USDT", 50)]}
    monkeypatch.setattr(reports, "_load_context", lambda _id: asyncio.sleep(0, result=context))
    monkeypatch.setattr(reports, "ask_gpt_json", lambda **_: {})
    report = reports.generate_unified_daily_report_sections(7)

    assert "BTC/EUR: Geen indicatoren ingesteld; 40/100" in report["market_analysis"]
    assert "BTC/USDT: Geen indicatoren ingesteld; 50/100" in report["market_analysis"]
    assert "Paper bot (BTC/EUR)" in report["bot_strategy"]
    assert "Paper bot (BTC/USDT)" in report["bot_strategy"]
    assert [item["pair"] for item in report["score_source_snapshot"]["assets"]] == [
        "BTC/EUR", "BTC/USDT",
    ]


def test_daily_report_lists_multiple_linked_strategies_and_rejects_false_missing_outlook(monkeypatch):
    context = {"locale": "nl", "assets": [{
        "symbol": "ETH",
        "benchmark": {
            "source_status": "available", "benchmark_score": 40,
            "component_source_status": {"market_score": "fresh", "macro_score": "fresh",
                                        "technical_score": "fresh"},
            "reported_scores": {"market_score": 40, "macro_score": 20,
                                "technical_score": 40},
            "matches": [],
        },
        "indicator_configuration": {"market": [{"indicator": "price"}],
                                    "macro": [{"indicator": "dxy"}],
                                    "technical": [{"indicator": "rsi"}]},
        "setups": [{"id": 1, "name": "ETH Setup A"}, {"id": 2, "name": "ETH Setup B"}],
        "strategies": [{"id": 11, "setup_id": 1, "name": "ETH Strategy A"},
                       {"id": 12, "setup_id": 2, "name": "ETH Strategy B"}],
        "bots": [],
    }]}
    monkeypatch.setattr(reports, "_load_context", lambda _id: asyncio.sleep(0, result=context))
    model_outlook = {"text": "De DXY- en RSI-waarden ontbreken nog, dus wacht af."}
    monkeypatch.setattr(reports, "ask_gpt_json", lambda **_: {
        "outlook": model_outlook["text"]})

    report = reports.generate_unified_daily_report_sections(7)

    assert report["active_strategy"]["strategies"] == [
        {"strategy_name": "ETH Strategy A", "setup_name": "ETH Setup A",
         "symbol": "ETH", "timeframe": None},
        {"strategy_name": "ETH Strategy B", "setup_name": "ETH Setup B",
         "symbol": "ETH", "timeframe": None},
    ]
    assert "ontbreken" not in report["outlook"]
    assert "20/100" in report["macro_context"]
    assert "40/100" in report["technical_analysis"]

    model_outlook["text"] = "Zonder RSI- en DXY-waarden kan ik geen beoordeling geven."
    assert "Zonder RSI" not in reports.generate_unified_daily_report_sections(7)["outlook"]


def test_daily_report_rejects_universal_market_decline_when_one_asset_rises(monkeypatch):
    context = {"locale": "nl", "assets": [
        {"symbol": "AAPL", "market_snapshot": {"source_status": "fresh", "change_24h": 1.74},
         "benchmark": {"source_status": "missing_scores", "matches": []}},
        {"symbol": "BTC", "market_snapshot": {"source_status": "fresh", "change_24h": -0.62},
         "benchmark": {"source_status": "missing_scores", "matches": []}},
    ]}
    monkeypatch.setattr(reports, "_load_context", lambda _id: asyncio.sleep(0, result=context))
    monkeypatch.setattr(reports, "ask_gpt_json", lambda **_: {
        "market_analysis": "Alle gemeten assets dalen vandaag, waaronder AAPL met +1,74%."
    })

    report = reports.generate_unified_daily_report_sections(7)

    assert "Alle gemeten assets dalen" not in report["market_analysis"]
    assert "+1,74%" not in report["market_analysis"]


def test_market_direction_guard_does_not_override_mixed_direction_prose():
    facts = {"assets": [
        {"market_snapshot": {"source_status": "fresh", "change_24h": 1.74}},
        {"market_snapshot": {"source_status": "fresh", "change_24h": -0.62}},
    ]}
    assert not reports._market_direction_contradicts_snapshot(
        "AAPL stijgt, terwijl BTC daalt; de markt is gemengd.", facts,
    )


def test_daily_report_lets_luna_repair_wrong_market_direction(monkeypatch):
    context = {"locale": "nl", "assets": [
        {"symbol": "AAPL", "market_snapshot": {"source_status": "fresh", "change_24h": 1.74},
         "benchmark": {"source_status": "missing_scores", "matches": []}},
        {"symbol": "BTC", "market_snapshot": {"source_status": "fresh", "change_24h": -0.62},
         "benchmark": {"source_status": "missing_scores", "matches": []}},
    ]}
    monkeypatch.setattr(reports, "_load_context", lambda _id: asyncio.sleep(0, result=context))
    model_calls = iter([
        {"market_analysis": "Alle gemeten assets dalen vandaag, waaronder AAPL met +1,74%."},
        {"market_analysis": "AAPL stijgt met 1,74%, terwijl BTC daalt; de koersbewegingen zijn gemengd."},
    ])
    monkeypatch.setattr(reports, "ask_gpt_json", lambda **_: next(model_calls))

    report = reports.generate_unified_daily_report_sections(7)

    assert report["market_analysis"].startswith("AAPL stijgt")


def test_multi_asset_report_keeps_btc_match_when_aapl_scores_are_missing(monkeypatch):
    context = {"locale": "nl", "assets": [
        {"symbol": "BTC", "setups": [], "strategies": [], "bots": [],
         "benchmark": {"source_status": "available", "matches": [
             {"setup_id": 9, "name": "BTC Plan", "symbol": "BTC", "timeframe": "4H",
              "status": "matches", "score": 67, "is_active": True},
         ]}},
        {"symbol": "AAPL", "setups": [], "strategies": [], "bots": [],
         "benchmark": {"source_status": "missing_scores", "matches": []}},
    ]}
    monkeypatch.setattr(reports, "_load_context", lambda _id: asyncio.sleep(0, result=context))
    monkeypatch.setattr(reports, "ask_gpt_json", lambda **_: {})

    report = reports.generate_unified_daily_report_sections(7)
    served = ReportService._mark_daily_setup_semantics(report)
    assert "Over alle gevolgde assets" in served["setup_validation"]
    assert served["best_setup"]["symbol"] == "BTC"
    assert served["top_setups"][0]["score"] == 67
    assert served["watchlist"][1]["benchmark"]["source_status"] == "missing_scores"


def test_report_does_not_claim_best_match_when_setup_score_is_unknown(monkeypatch):
    context = {"locale": "nl", "assets": [{
        "symbol": "AAPL", "setups": [], "strategies": [], "bots": [],
        "benchmark": {"source_status": "missing_scores", "matches": [{
            "setup_id": 13, "name": "Apple Plan", "symbol": "AAPL", "timeframe": "1D",
            "status": "missing_scores", "score": None, "is_active": False,
        }]},
    }]}
    monkeypatch.setattr(reports, "_load_context", lambda _id: asyncio.sleep(0, result=context))
    monkeypatch.setattr(reports, "ask_gpt_json", lambda **_: {})

    report = reports.generate_unified_daily_report_sections(7)

    assert report["best_setup"] is None
    assert report["setup_score"] is None
    assert report["top_setups"][0]["score"] is None


def test_period_report_uses_dated_owner_facts_and_does_not_count_planned_decision_as_trade(monkeypatch):
    captured = {}
    context = {
        "period": "weekly", "period_start": "2026-10-05", "period_end": "2026-10-07",
        "shared": {"locale": "nl", "assets": [{"symbol": "BTC", "bots": [],
            "benchmark": {"source_status": "missing_scores", "matches": []}}]},
        "dated_scores": [],
        "bot_decisions": [{"action": "buy", "status": "planned", "amount_eur": 100}],
        "daily_report_summaries": [],
    }

    async def _load(user_id, period):
        assert (user_id, period) == (7, "weekly")
        return context

    def _provider(**kwargs):
        captured.update(kwargs)
        return {"error": "provider_unavailable"}

    monkeypatch.setattr(reports, "_load_period_context", _load)
    monkeypatch.setattr(reports, "ask_gpt_json", _provider)
    result = reports.generate_weekly_report_sections(7)
    assert result["meta"]["source"] == "finn_shared_context.v1"
    assert result["macro_score"] is None
    assert "geen bevestigde setupmatch" in result["setup_performance"]
    assert "not an executed trade" in captured["system_role"]
    assert captured["model_override"] == "gpt-6-luna"
    assert captured["reasoning_effort"] == "none"


def test_daily_report_keeps_saved_plan_and_unscored_indicators_without_stale_scores(monkeypatch):
    """New-user report must agree with Analyse and the saved plan after persistence."""
    context = {
        "locale": "nl", "profile": {}, "observed_at": "2026-10-08T08:00:00+00:00",
        "assets": [{
            "symbol": "ETH",
            "setups": [{"id": 8, "name": "ETH maandelijkse DCA", "setup_type": "dca"}],
            "strategies": [{"id": 9, "setup_id": 8, "name": "ETH DCA strategie",
                            "setup_name": "ETH maandelijkse DCA", "symbol": "ETH",
                            "timeframe": "1D", "entry": None, "base_amount": 120}],
            "bots": [{"id": 10, "name": "ETH Paper", "is_live": False,
                      "is_active": False}],
            "indicator_lookup_status": "available",
            "indicator_configuration": {
                "market": [{"indicator": "Price", "enabled": True}],
                "macro": [{"indicator": "dxy", "enabled": True}],
                "technical": [{"indicator": "rsi", "enabled": True}],
            },
            "benchmark": {
                "source_status": "stale_sources", "benchmark_score": None,
                "reported_scores": {"market_score": 10, "macro_score": None,
                                    "technical_score": 50},
                "component_source_status": {"market_score": "stale_source",
                                            "macro_score": "missing_score",
                                            "technical_score": "stale_source"},
                "matches": [],
            },
        }],
    }
    captured = {}

    async def _load(_user_id):
        return context

    def _provider(**kwargs):
        captured.update(kwargs)
        return {key: "Actuele marktscore 10/100; technische score 50/100. Geen strategie."
                for key in reports.REPORT_SECTIONS}

    monkeypatch.setattr(reports, "_load_context", _load)
    monkeypatch.setattr(reports, "ask_gpt_json", _provider)
    result = reports.generate_unified_daily_report_sections(7)
    for key in ("executive_summary", "market_analysis", "macro_context",
                "technical_analysis", "setup_validation", "strategy_implication", "bot_strategy"):
        assert "10/100" not in result[key]
        assert "50/100" not in result[key]
        assert "Geen strategie" not in result[key]
    assert "ETH DCA strategie" in result["strategy_implication"]
    assert "Prijs" in result["market_analysis"]
    assert "DXY" in result["macro_context"]
    assert "RSI" in result["technical_analysis"]
    assert "ETH Paper staat gepauzeerd" in result["bot_strategy"]
    assert "criteria niet bereikt" not in result["bot_strategy"]
    assert "Beschikbaar kassaldo is in dit rapport niet vastgesteld" in result["bot_strategy"]
    assert result["active_strategy"]["setup_name"] == "ETH maandelijkse DCA"
    assert result["macro_indicator_highlights"] == [{"indicator": "DXY", "symbol": "ETH"}]
    assert result["technical_indicator_highlights"] == [{"indicator": "RSI", "symbol": "ETH"}]
    assert result["watchlist"][0]["benchmark"]["reported_scores"] == {
        "market_score": None, "macro_score": None, "technical_score": None,
    }
    sent = json.loads(captured["prompt"])["context"]["assets"][0]
    assert sent["scores"] == {"market_score": None, "macro_score": None,
                              "technical_score": None}
    assert "reported_scores" not in sent


def test_daily_report_task_persists_typed_report_facts(monkeypatch):
    """The Celery writer must not drop the facts before the saved report is read."""
    captured = {}

    class _DB:
        def commit(self):
            captured["committed"] = True

        def rollback(self):
            raise AssertionError("unexpected rollback")

        def close(self):
            pass

    class _Writer:
        def __init__(self, _db):
            pass

        def upsert_daily_report(self, **kwargs):
            captured["write"] = kwargs

    monkeypatch.setattr(daily_report_task, "SessionLocal", _DB)
    monkeypatch.setattr(daily_report_task, "DailyReportWriteRepository", _Writer)
    monkeypatch.setattr(daily_report_task, "get_user_email_snapshot", lambda _id: None)
    monkeypatch.setattr(daily_report_task, "ai_usage_context", lambda **_: nullcontext())
    monkeypatch.setattr(daily_report_task, "create_report_snapshot", lambda **_: (1, "local"))
    monkeypatch.setattr(daily_report_task, "generate_unified_daily_report_sections", lambda **_: {
        "executive_summary": "ETH plan opgeslagen; actuele benchmark onvolledig.",
        "market_analysis": "ETH: Price ingesteld; geen bruikbare actuele score.",
        "strategy_implication": "Opgeslagen strategieën: ETH DCA strategie.",
        "active_strategy": {"setup_name": "ETH maandelijkse DCA", "symbol": "ETH"},
        "market_indicator_highlights": [{"indicator": "Price", "symbol": "ETH"}],
        "macro_indicator_highlights": [{"indicator": "DXY", "symbol": "ETH"}],
        "technical_indicator_highlights": [{"indicator": "RSI", "symbol": "ETH"}],
        "market_score": None, "macro_score": None, "technical_score": None,
        "score_source_snapshot": {"observed_at": "2026-10-08T08:00:00+00:00", "assets": []},
    })

    daily_report_task.generate_daily_report.run(7)

    saved = captured["write"]
    assert captured["committed"] is True
    assert saved["market_score"] is None
    assert saved["sections"]["score_source_snapshot"]["observed_at"] == "2026-10-08T08:00:00+00:00"
    assert saved["sections"]["active_strategy"]["setup_name"] == "ETH maandelijkse DCA"
    assert saved["sections"]["macro_indicator_highlights"] == [
        {"indicator": "DXY", "symbol": "ETH"}]
