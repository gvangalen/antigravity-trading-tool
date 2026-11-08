import asyncio
import pytest

from backend.scripts.qa_protected_browser import block_websocket, request_policy


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
