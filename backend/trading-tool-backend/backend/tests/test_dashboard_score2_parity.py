import asyncio

from backend.services.dashboard_service import DashboardService


def test_web_and_mobile_dashboard_use_the_same_current_score_projection(monkeypatch):
    assessment = {
        "reported_scores": {"market_score": 40, "macro_score": None, "technical_score": 75},
        "component_source_status": {
            "market_score": "fresh", "macro_score": "stale_source", "technical_score": "fresh",
        },
        "benchmark_score": None,
        "matches": [],
        "source_status": "stale_sources",
        "as_of": None,
    }

    class Repository:
        async def get_latest_market_data(self, *_args):
            return []

        async def get_latest_technical_data(self, *_args):
            return []

        async def get_latest_macro_data(self, *_args):
            return []

        async def get_user_setups_summary(self, *_args):
            return []

        async def get_latest_prices_and_changes(self, *_args):
            return {"ETH": {"price": 2500, "change_24h": 1}}

    class MatchService:
        def __init__(self, _session):
            pass

        async def for_asset(self, *_args, **_kwargs):
            return assessment

    class SetupService:
        def __init__(self, _session):
            pass

        async def get_active_setup(self, *_args):
            return {"active": None}

    class SetupRepository:
        def __init__(self, _session):
            pass

        async def get_all_setups(self, *_args):
            return []

    class AssetCatalogService:
        def __init__(self, _session):
            pass

        async def get_assets(self, *_args):
            return {"ETH": {"display_name": "Ethereum"}}

    class BotService:
        def __init__(self, _session):
            pass

        async def get_bot_portfolios(self, *_args):
            return []

    monkeypatch.setattr(
        "backend.services.setup_market_match_service.SetupMarketMatchService", MatchService,
    )
    monkeypatch.setattr("backend.services.setup_service.SetupService", SetupService)
    monkeypatch.setattr("backend.infrastructure.repositories.setup_repository.SetupRepository", SetupRepository)
    monkeypatch.setattr("backend.services.dashboard_service.AssetCatalogService", AssetCatalogService)
    monkeypatch.setattr("backend.services.bot_service.BotService", BotService)
    service = DashboardService(object())
    service.repository = Repository()
    web = asyncio.run(service.get_dashboard_data(7, "ETH"))
    mobile = asyncio.run(service.get_mobile_overview(7, symbol="ETH"))

    assert web.scores.market == mobile.watchlist[0].market_score == 40
    assert web.scores.technical == mobile.watchlist[0].technical_score == 75
    assert web.scores.macro is mobile.watchlist[0].macro_score is None
    assert mobile.watchlist[0].benchmark_score is None
    assert "finn_briefing" not in mobile.dict()
    assert "intelligence_events" not in mobile.dict()
