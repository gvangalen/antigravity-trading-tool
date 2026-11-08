"""In-process browser observations for the protected production QA runner.

The caller owns the short-lived server-side bearer token. Neither the token
nor page contents may be returned in a workflow artifact or exception.
"""

from __future__ import annotations

from collections.abc import Callable
from urllib.parse import urlsplit


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


async def observe_page(
    *, base_url: str, path: str, token: str,
    inspect: Callable, timezone_id: str = "Europe/Amsterdam",
    timeout_ms: int = 30000,
):
    """Render one production page, inspect it in memory, and discard context.

    The callback receives a Playwright page and may return only sanitized
    booleans or fixed failure codes. Raw DOM, URLs with fixture data, API
    payloads and screenshots must remain inside the protected process.
    """
    if not path.startswith("/") or path.startswith("//") or not token:
        raise ValueError("qa_browser_input_invalid")
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
                    policy = request_policy(
                        base_url=base_url, request_url=route.request.url,
                    )
                    if policy == "block" or route.request.method not in {"GET", "HEAD"}:
                        await route.abort()
                    elif policy == "authenticated":
                        await route.continue_(headers={
                            **route.request.headers,
                            "authorization": f"Bearer {token}",
                        })
                    else:
                        await route.continue_()

                await context.route("**/*", route_request)
                page = await context.new_page()
                await page.goto(
                    f"{base_url.rstrip('/')}{path}",
                    wait_until="domcontentloaded", timeout=timeout_ms,
                )
                return await inspect(page)
            finally:
                await context.close()
        finally:
            await browser.close()
