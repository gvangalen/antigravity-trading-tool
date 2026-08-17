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
