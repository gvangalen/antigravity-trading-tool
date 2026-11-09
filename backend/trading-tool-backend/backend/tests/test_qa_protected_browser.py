import asyncio
import pytest

from backend.scripts.qa_protected_browser import (
    block_websocket, fixture_exact_selection_allowed, fixture_onboarding_response,
    observe_page, request_policy, route_protected_request,
)


def test_browser_only_authenticates_same_origin_api():
    base = "https://tradamind.com"
    assert request_policy(base_url=base, request_url=f"{base}/api/auth/me") == "authenticated"
    assert request_policy(base_url=base, request_url=f"{base}/asset?symbol=BTC") == "public"
    assert request_policy(base_url=base, request_url=f"{base}/_next/app.js") == "public"


@pytest.mark.parametrize("url", [
    "https://evil.example/api/auth/me",
    "https://tradamind.com.evil.example/api/auth/me",
    "http://tradamind.com/api/auth/me",
    "https://tradamind.com:8443/api/auth/me",
])
def test_browser_blocks_other_origins(url):
    assert request_policy(base_url="https://tradamind.com", request_url=url) == "block"


def test_browser_rejects_untrusted_base_origin():
    with pytest.raises(ValueError, match="qa_browser_origin_invalid"):
        request_policy(base_url="https://qa.example", request_url="https://qa.example/api/auth/me")
    with pytest.raises(ValueError, match="qa_browser_origin_invalid"):
        request_policy(base_url="https://user:secret@tradamind.com", request_url="https://tradamind.com/api/auth/me")


def test_browser_rejects_websocket_egress():
    class Route:
        closed = False
        async def close(self):
            self.closed = True
    route = Route()
    asyncio.run(block_websocket(route))
    assert route.closed is True


def test_fixture_onboarding_override_is_only_exact_same_origin_get():
    base = "https://tradamind.com"
    kwargs = {"base_url": base, "request_url": f"{base}/api/onboarding/status",
              "method": "GET", "enabled": True}
    result = fixture_onboarding_response(**kwargs)
    assert all(result[key] is True for key in (
        "onboarding_complete", "has_asset", "has_setup", "has_strategy", "has_bot",
    ))
    for change in (
        {"enabled": False}, {"method": "POST"},
        {"request_url": f"{base}/api/onboarding/status?user=private"},
        {"request_url": f"{base}/api/onboarding/profile"},
        {"request_url": "https://evil.example/api/onboarding/status"},
    ):
        assert fixture_onboarding_response(**(kwargs | change)) is None


def test_fixture_navigation_override_cannot_be_used_on_unrelated_pages():
    with pytest.raises(ValueError, match="qa_browser_fixture_override_scope_invalid"):
        asyncio.run(observe_page(
            base_url="https://tradamind.com", path="/portfolio", token="in-memory-token",
            inspect=lambda _page: None, bypass_fixture_onboarding=True,
        ))


def test_exact_selection_override_is_one_owner_scoped_in_memory_post_only():
    base = "https://tradamind.com"
    request = (f"{base}/api/assets/BTC/trading-markets/USDT/select?"
               "include_workspace=true&market_period=day")
    args = {"base_url": base, "request_url": request, "method": "POST", "enabled": True}
    assert fixture_exact_selection_allowed(**args) is True
    for change in (
        {"enabled": False}, {"method": "GET"},
        {"request_url": request.replace("BTC", "ETH")},
        {"request_url": request.replace("USDT", "EUR")},
        {"request_url": request.replace("include_workspace=true", "include_workspace=false")},
        {"request_url": request + "&owner=private"},
        {"request_url": request.replace(base, "https://evil.example")},
    ):
        assert fixture_exact_selection_allowed(**(args | change)) is False


def test_exact_selection_override_requires_asset_page():
    with pytest.raises(ValueError, match="qa_browser_exact_selection_override_scope_invalid"):
        asyncio.run(observe_page(
            base_url="https://tradamind.com", path="/report", token="in-memory-token",
            inspect=lambda _page: None, fixture_exact_selection=lambda: {},
        ))


def test_browser_fulfills_only_allowlisted_selection_post_without_network():
    class Route:
        def __init__(self, url, method):
            self.request = type("Request", (), {
                "url": url, "method": method, "headers": {},
            })()
            self.actions = []
        async def abort(self):
            self.actions.append("abort")
        async def fulfill(self, **kwargs):
            self.actions.append(("fulfill", kwargs["status"]))
        async def continue_(self, **_kwargs):
            self.actions.append("continue")

    base = "https://tradamind.com"
    exact = f"{base}/api/assets/BTC/trading-markets/USDT/select?include_workspace=true"
    for url, method, expected in (
        (exact, "POST", [("fulfill", 200)]),
        (exact.replace("USDT", "EUR"), "POST", ["abort"]),
        (exact + "&owner=private", "POST", ["abort"]),
        ("https://evil.example/api/assets/BTC/trading-markets/USDT/select?include_workspace=true",
         "POST", ["abort"]),
    ):
        route = Route(url, method)
        asyncio.run(route_protected_request(
            route, base_url=base, token="private-token",
            bypass_fixture_onboarding=True,
            fixture_exact_selection=lambda: {"workspace": {"private": "private-value"}},
        ))
        assert route.actions == expected
