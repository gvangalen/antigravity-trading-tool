from types import SimpleNamespace
import asyncio

from backend.services.finn_v2_entity_resolution_service import FinnV2EntityResolutionService


def test_asset_resolution_prefers_explicit_selector(monkeypatch):
    service = FinnV2EntityResolutionService(session=object())
    monkeypatch.setattr(service.states, "get_state", lambda _user_id: asyncio.sleep(0, result={"asset": "ETH"}))

    result = asyncio.run(service.resolve_asset(user_id=7, selector={"asset": "BTC"}))

    assert result == {"asset": "BTC", "resolution_source": "explicit_selector"}


def test_asset_resolution_has_no_btc_default(monkeypatch):
    service = FinnV2EntityResolutionService(session=object())
    monkeypatch.setattr(service.states, "get_state", lambda _user_id: asyncio.sleep(0, result=None))
    monkeypatch.setattr(service.users, "get_by_id", lambda _user_id: asyncio.sleep(0, result=SimpleNamespace(ai_preferences={})))

    try:
        asyncio.run(service.resolve_asset(user_id=7, selector={}))
    except LookupError as exc:
        assert str(exc) == "asset_not_resolved"
    else:
        raise AssertionError("Expected asset_not_resolved")


def test_asset_resolution_is_account_scoped_between_btc_and_aapl(monkeypatch):
    service = FinnV2EntityResolutionService(session=object())
    monkeypatch.setattr(service.states, "get_state", lambda _user_id: asyncio.sleep(0, result=None))

    async def _get_by_id(user_id):
        prefs = {"selected_asset": "BTC"} if user_id == 7 else {"selected_asset": "AAPL"}
        return SimpleNamespace(ai_preferences=prefs)

    monkeypatch.setattr(service.users, "get_by_id", _get_by_id)

    btc = asyncio.run(service.resolve_asset(user_id=7, selector={}))
    aapl = asyncio.run(service.resolve_asset(user_id=8, selector={}))

    assert btc == {"asset": "BTC", "resolution_source": "selected_asset"}
    assert aapl == {"asset": "AAPL", "resolution_source": "selected_asset"}


def test_asset_resolution_prefers_authenticated_workspace_state_before_user_preferences(monkeypatch):
    service = FinnV2EntityResolutionService(session=object())
    monkeypatch.setattr(service.states, "get_state", lambda _user_id: asyncio.sleep(0, result=None))
    monkeypatch.setattr(service.users, "get_by_id", lambda _user_id: asyncio.sleep(0, result=SimpleNamespace(ai_preferences={"selected_asset": "BTC"})))
    monkeypatch.setattr(service.assets, "get_asset", lambda symbol: asyncio.sleep(0, result={"symbol": symbol}))

    result = asyncio.run(
        service.resolve_asset(
            user_id=7,
            selector={},
            workspace_hints={"workspace_asset": "AAPL"},
        )
    )

    assert result == {"asset": "AAPL", "resolution_source": "workspace_state"}


def test_strategy_resolution_does_not_fall_back_to_unlinked_last_strategy_when_setup_is_known(monkeypatch):
    service = FinnV2EntityResolutionService(session=object())
    monkeypatch.setattr(service.strategies, "get_strategy_by_setup", lambda setup_id, user_id: asyncio.sleep(0, result=None))
    monkeypatch.setattr(service.strategies, "get_last_strategy", lambda user_id: asyncio.sleep(0, result={"id": 999, "setup_id": 12}))

    try:
        asyncio.run(service.resolve_strategy(user_id=7, selector={}, setup={"id": 287, "symbol": "BTC"}))
    except LookupError as exc:
        assert str(exc) == "strategy_not_resolved"
    else:
        raise AssertionError("Expected strategy_not_resolved when no strategy is linked to the selected setup")


def test_bot_resolution_does_not_fall_back_to_unlinked_single_bot_when_strategy_is_known(monkeypatch):
    service = FinnV2EntityResolutionService(session=object())
    monkeypatch.setattr(service.bots, "get_bot_configs", lambda user_id: asyncio.sleep(0, result=[{"id": 164, "strategy_id": 999}]))

    try:
        asyncio.run(service.resolve_bot(user_id=7, selector={}, strategy={"id": 303}))
    except LookupError as exc:
        assert str(exc) == "bot_not_resolved"
    else:
        raise AssertionError("Expected bot_not_resolved when no bot is linked to the selected strategy")
