"""Read-only browser check of deployed FINN watchlist choices.

All asset mention responses are bounded in-memory fixtures and all FINN POSTs
remain blocked by qa_protected_browser. Only fixed outcome codes leave this probe.
"""

from __future__ import annotations

import asyncio
import json
from urllib.parse import urlsplit

from backend.scripts.qa_protected_browser import observe_page


SCENARIOS = (
    ("ambiguous_scope", "Mijn aandeel aanpassen in bitcoin", ("Watchlist", "Portfolio"), "Watchlist", None),
    ("btc_eur_click", "Voeg BTC toe aan mijn watchlist", ("BTC/EUR toevoegen", "BTC/USDT toevoegen"), "BTC/EUR toevoegen", "BTC/EUR"),
    ("eth_usdt_click", "Voeg ETH toe aan mijn watchlist", ("ETH/EUR toevoegen", "ETH/USDT toevoegen"), "ETH/USDT toevoegen", "ETH/USDT"),
    ("apple_stock_click", "Voeg Apple toe aan mijn watchlist", ("Apple toevoegen",), "Apple toevoegen", "AAPL"),
    ("apple_btc_replacement", "Apple niet meer volgen; volg Bitcoin in mijn watchlist", ("AAPL vervangen door BTC/EUR", "AAPL vervangen door BTC/USDT"), "AAPL vervangen door BTC/EUR", "BTC/EUR"),
)


def _mentions(body: str | None) -> dict:
    try:
        message = json.loads(body or "")["text"]
    except (ValueError, KeyError, TypeError):
        raise ValueError("watchlist_mentions_request_invalid") from None
    if message not in {scenario[1] for scenario in SCENARIOS}:
        raise ValueError("watchlist_mentions_request_unexpected")
    found = []
    for names, symbol, asset_class, display in (
        (("Apple",), "AAPL", "stock", "Apple"),
        (("Bitcoin", "bitcoin", "BTC"), "BTC", "crypto", "Bitcoin"),
        (("ETH",), "ETH", "crypto", "Ethereum"),
    ):
        positions = [(message.find(name), name) for name in names if message.find(name) >= 0]
        if positions:
            start, name = min(positions)
            found.append({"symbol": symbol, "asset_class": asset_class,
                          "display_name": display, "start": start, "end": start + len(name)})
    return {"mentions": sorted(found, key=lambda row: row["start"])}


async def _scenario(token: str, scenario: tuple) -> dict[str, str | bool]:
    case_id, prompt, expected_labels, click_label, expected_submission = scenario
    state = {"stage": "browser_open", "route": "unknown"}

    async def inspect(page):
        route = urlsplit(page.url).path
        state["route"] = route if route in {"/asset", "/login", "/onboarding", "/dashboard"} else "other"
        outgoing = []
        failed = []
        page.on("request", lambda request: outgoing.append(request)
                if request.method == "POST" and urlsplit(request.url).path == "/api/assistant/chat/stream" else None)
        page.on("requestfailed", lambda request: failed.append(request)
                if request.method == "POST" and urlsplit(request.url).path == "/api/assistant/chat/stream" else None)
        state["stage"] = "composer_open"
        launcher = page.locator('form input[type="text"]').last
        await launcher.wait_for(state="visible", timeout=15000)
        await launcher.click()
        composer = page.locator("textarea").last
        state["stage"] = "composer_visible"
        await composer.wait_for(state="visible", timeout=15000)
        state["stage"] = "composer_submit"
        await composer.fill(prompt)
        await composer.press("Enter")
        choices = page.locator('[aria-label="Watchlistkeuzes"]')
        state["stage"] = "choices_visible"
        await choices.wait_for(state="visible", timeout=15000)
        labels = [value.strip() for value in await choices.locator("button").all_text_contents()]
        options_ok = all(label in labels for label in expected_labels)
        if not options_ok:
            return {"case_id": case_id, "options_visible": False, "click_handled": False,
                    "product_post_blocked": True}
        state["stage"] = "choice_click"
        await choices.get_by_role("button", name=click_label, exact=True).click()
        if expected_submission is None:
            next_choices = page.locator('[aria-label="Watchlistkeuzes"]')
            state["stage"] = "followup_choices_visible"
            replacement = next_choices.locator("button").filter(has_text="vervangen").first
            await replacement.wait_for(state="visible", timeout=10000)
            return {"case_id": case_id, "options_visible": True,
                    "click_handled": True,
                    "product_post_blocked": len(outgoing) == 0}
        await page.wait_for_timeout(1200)
        matched = False
        for request in outgoing:
            try:
                body = json.loads(request.post_data or "")
            except ValueError:
                continue
            matched = matched or expected_submission in str(body.get("query") or "")
        return {"case_id": case_id, "options_visible": True,
                "click_handled": matched, "product_post_blocked": bool(outgoing) and len(failed) == len(outgoing)}

    try:
        return await observe_page(
            base_url="https://tradamind.com", path="/asset", token=token,
            inspect=inspect, bypass_fixture_onboarding=True,
            fixture_asset_mentions=_mentions,
            fixture_watchlist_rows=lambda: [{"symbol": "AAPL", "market_id": None,
                                             "asset_class": "stock", "display_name": "Apple"}],
        )
    except Exception:
        return {"case_id": case_id, "options_visible": False,
                "click_handled": False, "product_post_blocked": False,
                "error_code": state["stage"] + "_failed",
                "route_code": state["route"]}


async def _saved_pair_visibility(token: str) -> dict[str, str | bool]:
    """Check deployed rendering and account scoping with in-memory watchlists.

    The first identity is the authenticated protected fixture. The second is a
    synthetic in-memory owner; no second account or product mutation is made.
    """
    state = {"phase": "first", "auth_user": None, "stage": "browser_open",
             "watchlist_gets": 0, "route": "unknown"}
    first_rows = [
        {"symbol": "BTC", "market_id": 410001, "quote_currency": "EUR",
         "asset_class": "crypto", "display_name": "Bitcoin"},
        {"symbol": "BTC", "market_id": 410002, "quote_currency": "USDT",
         "asset_class": "crypto", "display_name": "Bitcoin"},
    ]
    second_rows = [
        {"symbol": "ETH", "market_id": 410003, "quote_currency": "EUR",
         "asset_class": "crypto", "display_name": "Ethereum"},
    ]

    def rows():
        state["watchlist_gets"] += 1
        return first_rows if state["phase"] == "first" else second_rows

    def user():
        return state["auth_user"] if state["phase"] == "second" else None

    async def inspect(page):
        state["route"] = urlsplit(page.url).path if urlsplit(page.url).path in {
            "/asset", "/login", "/onboarding", "/dashboard",
        } else "other"
        product_posts = []
        failed_posts = []
        page.on("request", lambda request: product_posts.append(request)
                if request.method == "POST" else None)
        page.on("requestfailed", lambda request: failed_posts.append(request)
                if request.method == "POST" else None)
        first_eur = page.get_by_role("button", name="Asset verwijderen: BTC/EUR")
        first_usdt = page.get_by_role("button", name="Asset verwijderen: BTC/USDT")
        second_eth = page.get_by_role("button", name="Asset verwijderen: ETH/EUR")
        state["stage"] = "crypto_group"
        await page.get_by_role("button", name="Crypto", exact=True).click()
        state["stage"] = "first_rows"
        try:
            await first_eur.wait_for(state="visible", timeout=15000)
            await first_usdt.wait_for(state="visible", timeout=15000)
        except Exception:
            body = await page.locator("body").inner_text()
            return {"case_id": "saved_pair_owner_switch", "both_initial": False,
                    "both_after_eur": False, "both_after_usdt": False,
                    "isolated_second": False, "restored_first": False,
                    "product_post_blocked": len(product_posts) == len(failed_posts),
                    "error_code": "first_rows_failed", "route_code": state["route"],
                    "watchlist_get_seen": state["watchlist_gets"] > 0,
                    "eur_label_in_dom": "BTC/EUR" in body,
                    "usdt_label_in_dom": "BTC/USDT" in body,
                    "eur_button_count_positive": await first_eur.count() > 0,
                    "usdt_button_count_positive": await first_usdt.count() > 0}
        both_initial = await first_eur.is_visible() and await first_usdt.is_visible()

        state["stage"] = "select_eur"
        await first_eur.locator("xpath=..").click()
        await page.wait_for_url("**/asset?*quote=EUR*", timeout=10000)
        both_after_eur = await first_eur.is_visible() and await first_usdt.is_visible()

        state["stage"] = "select_usdt"
        await first_usdt.locator("xpath=..").click()
        await page.wait_for_url("**/asset?*quote=USDT*", timeout=10000)
        both_after_usdt = await first_eur.is_visible() and await first_usdt.is_visible()

        state["stage"] = "switch_owner"
        real_user = await page.evaluate("""async () => {
            const response = await fetch('/api/auth/me', {credentials: 'include'});
            return response.ok ? await response.json() : null;
        }""")
        if not isinstance(real_user, dict) or not real_user.get("id"):
            raise ValueError("protected_identity_unavailable")
        state["auth_user"] = {**real_user, "id": "qa-synthetic-secondary-owner"}
        state["phase"] = "second"
        await page.reload(wait_until="domcontentloaded")
        await second_eth.wait_for(state="visible", timeout=15000)
        isolated_second = (await second_eth.is_visible()
                           and await first_eur.count() == 0 and await first_usdt.count() == 0)

        state["stage"] = "restore_owner"
        state["phase"] = "first"
        await page.reload(wait_until="domcontentloaded")
        await first_eur.wait_for(state="visible", timeout=15000)
        await first_usdt.wait_for(state="visible", timeout=15000)
        restored_first = (await first_eur.is_visible() and await first_usdt.is_visible()
                          and await second_eth.count() == 0)
        return {"case_id": "saved_pair_owner_switch", "both_initial": both_initial,
                "both_after_eur": both_after_eur, "both_after_usdt": both_after_usdt,
                "isolated_second": isolated_second, "restored_first": restored_first,
                "product_post_blocked": len(product_posts) == len(failed_posts)}

    try:
        return await observe_page(
            base_url="https://tradamind.com", path="/asset", token=token,
            inspect=inspect, bypass_fixture_onboarding=True,
            fixture_watchlist_rows=rows, fixture_auth_user=user,
        )
    except Exception:
        return {"case_id": "saved_pair_owner_switch", "both_initial": False,
                "both_after_eur": False, "both_after_usdt": False,
                "isolated_second": False, "restored_first": False,
                "product_post_blocked": False, "error_code": state["stage"] + "_failed",
                "route_code": state["route"],
                "watchlist_get_seen": state["watchlist_gets"] > 0}


def run(token: str) -> dict:
    cases = [asyncio.run(_scenario(token, scenario)) for scenario in SCENARIOS]
    choices_passed = all(
        case["options_visible"] and case["click_handled"] and case["product_post_blocked"]
        for case in cases
    )
    visibility = asyncio.run(_saved_pair_visibility(token))
    cases.append(visibility)
    visibility_passed = all(visibility.get(field) is True for field in (
        "both_initial", "both_after_eur", "both_after_usdt",
        "isolated_second", "restored_first", "product_post_blocked",
    ))
    return {"cases": cases, "passed": choices_passed and visibility_passed}
