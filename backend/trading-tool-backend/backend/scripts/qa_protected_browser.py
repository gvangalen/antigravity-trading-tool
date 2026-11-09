"""In-process browser observations for the protected production QA runner.

The caller owns the short-lived server-side bearer token. Neither the token
nor page contents may be returned in a workflow artifact or exception.
"""

from __future__ import annotations

from collections.abc import Callable
import json
from urllib.parse import parse_qs, urlsplit


def request_policy(*, base_url: str, request_url: str) -> str:
    """Classify a browser request before it can leave the isolated context."""
    base = urlsplit(base_url)
    request = urlsplit(request_url)
    if base_url.rstrip("/") != "https://tradamind.com":
        raise ValueError("qa_browser_origin_invalid")
    if request.scheme != base.scheme or request.netloc != base.netloc:
        return "block"
    return "authenticated" if request.path.startswith("/api/") else "public"


async def block_websocket(route) -> None:
    await route.close()


def fixture_onboarding_response(*, base_url: str, request_url: str, method: str,
                                enabled: bool) -> dict | None:
    if (not enabled or method != "GET"
            or request_policy(base_url=base_url, request_url=request_url) != "authenticated"):
        return None
    parsed = urlsplit(request_url)
    if parsed.path != "/api/onboarding/status" or parsed.query:
        return None
    return {
        "onboarding_complete": True,
        "phases_completed": {"complete": True},
        "has_asset": True,
        "has_setup": True,
        "has_strategy": True,
        "has_bot": True,
        "next_route": "/dashboard",
    }


def fixture_exact_selection_allowed(*, base_url: str, request_url: str,
                                    method: str, enabled: bool) -> bool:
    """Allow one QA-only in-memory response; never dispatch the product POST."""
    if (not enabled or method != "POST"
            or request_policy(base_url=base_url, request_url=request_url) != "authenticated"):
        return False
    parsed = urlsplit(request_url)
    if parsed.path != "/api/assets/BTC/trading-markets/USDT/select":
        return False
    query = parse_qs(parsed.query, keep_blank_values=True)
    allowed = {"include_workspace", "market_period", "macro_period",
               "technical_period", "watchlist_symbols"}
    if set(query) - allowed or query.get("include_workspace") != ["true"]:
        return False
    return all(len(values) == 1 for values in query.values())


async def route_protected_request(route, *, base_url: str, token: str,
                                  bypass_fixture_onboarding: bool,
                                  fixture_exact_selection: Callable | None) -> None:
    policy = request_policy(base_url=base_url, request_url=route.request.url)
    if policy == "block":
        await route.abort()
    elif fixture_exact_selection_allowed(
        base_url=base_url, request_url=route.request.url,
        method=route.request.method,
        enabled=fixture_exact_selection is not None,
    ):
        try:
            payload = fixture_exact_selection()
            if not isinstance(payload, dict):
                raise ValueError("invalid protected response")
        except Exception:
            await route.abort()
        else:
            await route.fulfill(
                status=200, content_type="application/json",
                body=json.dumps(payload),
            )
    elif route.request.method not in {"GET", "HEAD"}:
        await route.abort()
    elif (override := fixture_onboarding_response(
        base_url=base_url, request_url=route.request.url,
        method=route.request.method, enabled=bypass_fixture_onboarding,
    )) is not None:
        await route.fulfill(
            status=200, content_type="application/json",
            body=json.dumps(override),
        )
    elif policy == "authenticated":
        await route.continue_(headers={
            **route.request.headers,
            "authorization": f"Bearer {token}",
        })
    else:
        await route.continue_()


async def observe_page(
    *, base_url: str, path: str, token: str,
    inspect: Callable, timezone_id: str = "Europe/Amsterdam",
    timeout_ms: int = 30000, bypass_fixture_onboarding: bool = False,
    observe_response: Callable | None = None,
    observe_page_error: Callable | None = None,
    observe_console: Callable | None = None,
    fixture_exact_selection: Callable | None = None,
):
    """Render one production page, inspect it in memory, and discard context.

    The callback receives a Playwright page and may return only sanitized
    booleans or fixed failure codes. Raw DOM, URLs with fixture data, API
    payloads and screenshots must remain inside the protected process.
    """
    if not path.startswith("/") or path.startswith("//") or not token:
        raise ValueError("qa_browser_input_invalid")
    if bypass_fixture_onboarding and urlsplit(path).path not in {"/bot", "/asset", "/report"}:
        raise ValueError("qa_browser_fixture_override_scope_invalid")
    if fixture_exact_selection is not None and urlsplit(path).path != "/asset":
        raise ValueError("qa_browser_exact_selection_override_scope_invalid")
    if request_policy(base_url=base_url, request_url=base_url) != "public":
        raise ValueError("qa_browser_origin_invalid")

    from playwright.async_api import async_playwright

    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage"],
        )
        try:
            context = await browser.new_context(
                timezone_id=timezone_id,
                locale="nl-NL",
                service_workers="block",
                viewport={"width": 1280, "height": 900},
            )
            try:
                await context.add_init_script(
                    "window.localStorage.setItem('antigravity_locale', 'nl')"
                )
                await context.route_web_socket("**/*", block_websocket)
                async def route_request(route):
                    await route_protected_request(
                        route, base_url=base_url, token=token,
                        bypass_fixture_onboarding=bypass_fixture_onboarding,
                        fixture_exact_selection=fixture_exact_selection,
                    )

                await context.route("**/*", route_request)
                page = await context.new_page()
                if observe_response is not None:
                    page.on("response", observe_response)
                if observe_page_error is not None:
                    page.on("pageerror", observe_page_error)
                if observe_console is not None:
                    page.on("console", observe_console)
                await page.goto(
                    f"{base_url.rstrip('/')}{path}",
                    wait_until="domcontentloaded", timeout=timeout_ms,
                )
                return await inspect(page)
            finally:
                await context.close()
        finally:
            await browser.close()
