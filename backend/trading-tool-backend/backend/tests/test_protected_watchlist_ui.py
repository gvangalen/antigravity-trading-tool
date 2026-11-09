import pytest

from backend.scripts.probe_protected_watchlist_ui import SCENARIOS, _mentions


def test_watchlist_browser_mentions_are_bounded_and_ordered():
    text = "Apple niet meer volgen; volg Bitcoin in mijn watchlist"
    result = _mentions('{"text":"' + text + '"}')
    assert [(item["symbol"], item["start"]) for item in result["mentions"]] == [
        ("AAPL", text.index("Apple")), ("BTC", text.index("Bitcoin")),
    ]
    assert len(SCENARIOS) == 5


def test_watchlist_browser_rejects_unapproved_prompt():
    with pytest.raises(ValueError, match="watchlist_mentions_request_unexpected"):
        _mentions('{"text":"Koop BTC live"}')
