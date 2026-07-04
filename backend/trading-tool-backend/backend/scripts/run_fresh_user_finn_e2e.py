#!/usr/bin/env python3
"""Run a fresh-user FINN creation-flow E2E against a live environment.

This script intentionally uses the public HTTP/API flow with separate cookie
sessions per user. It does not use direct DB inserts.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import requests


DEFAULT_BASE_URL = "https://www.tradamind.com"
DEFAULT_TIMEOUT = 45


def now_slug() -> str:
    return time.strftime("%Y%m%d-%H%M%S")


def pretty(data: Any) -> str:
    return json.dumps(data, indent=2, ensure_ascii=False, sort_keys=True)


@dataclass
class StepResult:
    name: str
    status: str
    expected: str
    actual: str
    detail: Dict[str, Any] = field(default_factory=dict)


class ApiSession:
    def __init__(self, base_url: str, locale: str = "nl") -> None:
        self.base_url = base_url.rstrip("/")
        self.locale = locale
        self.session = requests.Session()
        self.session.headers.update(
            {
                "Accept": "application/json",
                "Content-Type": "application/json",
                "X-Locale": locale,
                "User-Agent": "CodexFreshUserE2E/1.0",
            }
        )

    def _csrf(self) -> Optional[str]:
        return self.session.cookies.get("csrf_token")

    def _headers(self, method: str, extra: Optional[Dict[str, str]] = None) -> Dict[str, str]:
        headers = dict(self.session.headers)
        if method.upper() in {"POST", "PUT", "PATCH", "DELETE"} and self._csrf():
            headers["X-CSRF-Token"] = self._csrf() or ""
        if extra:
            headers.update(extra)
        return headers

    def request(
        self,
        method: str,
        path: str,
        *,
        json_body: Optional[Dict[str, Any]] = None,
        allow_status: Tuple[int, ...] = (200,),
        extra_headers: Optional[Dict[str, str]] = None,
    ) -> Tuple[requests.Response, Any]:
        url = f"{self.base_url}{path}"
        response = self.session.request(
            method.upper(),
            url,
            json=json_body,
            headers=self._headers(method, extra_headers),
            timeout=DEFAULT_TIMEOUT,
        )
        try:
            payload = response.json()
        except Exception:
            payload = response.text
        if response.status_code not in allow_status:
            raise RuntimeError(
                f"{method} {path} -> {response.status_code}\nPayload: {pretty(payload)}"
            )
        return response, payload

    def register(self, *, first_name: str, email: str, password: str) -> Dict[str, Any]:
        _, payload = self.request(
            "POST",
            "/api/auth/register",
            json_body={
                "first_name": first_name,
                "last_name": "",
                "email": email,
                "password": password,
                "locale": self.locale,
            },
        )
        return payload

    def login(self, *, email: str, password: str) -> Dict[str, Any]:
        _, payload = self.request(
            "POST",
            "/api/auth/login",
            json_body={"email": email, "password": password, "locale": self.locale},
        )
        return payload

    def logout(self) -> Dict[str, Any]:
        _, payload = self.request("POST", "/api/auth/logout")
        return payload

    def me(self) -> Dict[str, Any]:
        _, payload = self.request("GET", "/api/auth/me")
        return payload


def build_user_email(prefix: str) -> str:
    return f"codex-{prefix}-{now_slug()}-{uuid.uuid4().hex[:6]}@example.net"


def extract_action_id(payload: Dict[str, Any]) -> Optional[str]:
    actions = payload.get("actions") or []
    for action in actions:
        action_id = action.get("action_id") or action.get("id")
        if action_id:
            return str(action_id)
    return None


def draft_missing_fields(payload: Dict[str, Any]) -> List[str]:
    return [str(item) for item in (payload.get("missing_fields") or [])]


def assert_contains_case_insensitive(text: str, needle: str) -> bool:
    return needle.lower() in (text or "").lower()


def find_saved_setup(setups: List[Dict[str, Any]], symbol: str) -> Optional[Dict[str, Any]]:
    for setup in setups:
        if str(setup.get("symbol") or "").upper() == symbol.upper():
            return setup
    return None


def find_saved_bot(configs: List[Dict[str, Any]], strategy_id: int) -> Optional[Dict[str, Any]]:
    for config in configs:
        config_strategy_id = (
            config.get("strategy_id")
            or ((config.get("strategy") or {}).get("id") if isinstance(config.get("strategy"), dict) else None)
        )
        if int(config_strategy_id or 0) == int(strategy_id):
            return config
    return None


def onboarding_completed(payload: Dict[str, Any]) -> bool:
    if not isinstance(payload, dict):
        return False
    if payload.get("completed") is True:
        return True
    return bool(payload.get("onboarding_complete"))


def normalize_watchlist(payload: Any) -> List[str]:
    if isinstance(payload, list):
        return [str(item).upper() for item in payload]
    return []


def step_ok_from_execute(payload: Optional[Dict[str, Any]]) -> bool:
    if not isinstance(payload, dict):
        return False
    if payload.get("ok") is True:
        return True
    if str(payload.get("status") or "").lower() == "success":
        return True
    result = payload.get("result")
    if isinstance(result, dict) and str(result.get("status") or "").lower() == "success":
        return True
    return False


def nested_setup_id(payload: Any) -> int:
    if not isinstance(payload, dict):
        return 0
    setup = payload.get("setup")
    if isinstance(setup, dict):
        return int(setup.get("id") or 0)
    return 0


def nested_strategy_id(payload: Any) -> int:
    if not isinstance(payload, dict):
        return 0
    return int(payload.get("id") or 0)


def create_or_follow_up_setup(api: ApiSession, symbol: str = "BTC") -> Dict[str, Any]:
    session_id = f"fresh-setup-{uuid.uuid4().hex[:8]}"
    first_ctx = {"page": "setup", "symbol": symbol}
    _, payload = api.request(
        "POST",
        "/api/assistant/chat",
        json_body={
            "query": f"Maak een setup voor {symbol} swing trading met daily trend en 4H entry.",
            "context": first_ctx,
            "history": [],
            "session_id": session_id,
        },
    )

    missing = draft_missing_fields(payload)
    if payload.get("can_confirm") and extract_action_id(payload):
        return payload

    follow_up_map = {
        "setup.timeframe": "4H",
        "timeframe": "4H",
        "setup_type": "trade",
        "plan_type": "trade setup",
        "strategy.entry_type": "limit entry",
        "dca.frequency": "wekelijks",
    }
    current = payload
    for _ in range(4):
        missing = draft_missing_fields(current)
        if current.get("can_confirm") and extract_action_id(current):
            return current
        if not missing:
            return current
        answer = follow_up_map.get(missing[0], "4H")
        _, current = api.request(
            "POST",
            "/api/assistant/chat",
            json_body={
                "query": answer,
                "context": {"finn_draft": current.get("draft"), "page": "setup", "symbol": symbol},
                "history": [],
                "session_id": session_id,
            },
        )
    return current


def create_or_follow_up_strategy(api: ApiSession, setup_id: int, symbol: str = "BTC") -> Dict[str, Any]:
    session_id = f"fresh-strategy-{uuid.uuid4().hex[:8]}"
    ctx = {"page": "strategy", "setup_id": setup_id, "setup_symbol": symbol}
    _, payload = api.request(
        "POST",
        "/api/assistant/chat",
        json_body={
            "query": "Maak hier een strategie van met duidelijke entry, invalidatie en risk management.",
            "context": ctx,
            "history": [],
            "session_id": session_id,
        },
    )

    current = payload
    follow_up_map = {
        "timeframe": "4H",
        "setup_id": str(setup_id),
        "strategy.base_amount_eur": "100 euro",
        "strategy.entry": "Entry 62000",
        "strategy.stop_loss": "Stop loss 59800",
        "strategy.targets": "Targets 64500 en 67000",
        "strategy.entry_type": "limit entry",
        "strategy.market_execution_ack": "ik wil limit entry",
    }
    for _ in range(6):
        if current.get("can_confirm") and extract_action_id(current):
            return current
        missing = draft_missing_fields(current)
        if not missing:
            return current
        answer = follow_up_map.get(missing[0], "4H")
        _, current = api.request(
            "POST",
            "/api/assistant/chat",
            json_body={
                "query": answer,
                "context": {"finn_draft": current.get("draft"), "page": "strategy", "setup_id": setup_id, "setup_symbol": symbol},
                "history": [],
                "session_id": session_id,
            },
        )
    return current


def create_or_follow_up_bot(api: ApiSession, strategy_id: int, symbol: str = "BTC") -> Dict[str, Any]:
    session_id = f"fresh-bot-{uuid.uuid4().hex[:8]}"
    ctx = {"page": "bot", "strategy_id": strategy_id, "symbol": symbol}
    _, payload = api.request(
        "POST",
        "/api/assistant/chat",
        json_body={
            "query": "Maak een paper bot voor deze strategie met 1000 euro budget.",
            "context": ctx,
            "history": [],
            "session_id": session_id,
        },
    )

    current = payload
    follow_up_map = {
        "strategy_id": str(strategy_id),
        "bot.budget_total_eur": "budget 1000",
        "bot.budget_daily_limit_eur": "daglimiet 100",
        "bot.budget_min_order_eur": "min order 25",
        "bot.budget_max_order_eur": "max order 100",
        "bot.live_trading_ack": "paper bot",
    }
    for _ in range(6):
        if current.get("can_confirm") and extract_action_id(current):
            return current
        missing = draft_missing_fields(current)
        if not missing:
            return current
        answer = follow_up_map.get(missing[0], str(strategy_id))
        _, current = api.request(
            "POST",
            "/api/assistant/chat",
            json_body={
                "query": answer,
                "context": {"finn_draft": current.get("draft"), "page": "bot", "strategy_id": strategy_id, "symbol": symbol},
                "history": [],
                "session_id": session_id,
            },
        )
    return current


def run_flow(api: ApiSession, first_name: str, email: str, password: str) -> Tuple[List[StepResult], Dict[str, Any]]:
    steps: List[StepResult] = []
    collected: Dict[str, Any] = {}

    def add(name: str, ok: bool, expected: str, actual: str, detail: Optional[Dict[str, Any]] = None) -> None:
        steps.append(
            StepResult(
                name=name,
                status="pass" if ok else "fail",
                expected=expected,
                actual=actual,
                detail=detail or {},
            )
        )

    # register
    reg = api.register(first_name=first_name, email=email, password=password)
    collected["register"] = reg
    add("register", bool(reg.get("id")), "Nieuwe user wordt aangemaakt", f"id={reg.get('id')}", {"response": reg})

    # login
    login = api.login(email=email, password=password)
    collected["login"] = login
    add("login", bool(login.get("success")), "User kan inloggen", f"success={login.get('success')}", {"response": login})

    me = api.me()
    collected["me"] = me
    user_id = me.get("id")
    add("auth_me", bool(user_id), "Auth-me geeft juiste user terug", f"user_id={user_id}", {"response": me})

    _, onboarding = api.request("GET", "/api/onboarding/status")
    collected["onboarding_before"] = onboarding
    add(
        "onboarding_status_before",
        isinstance(onboarding, dict),
        "Onboarding-status is leesbaar",
        f"completed={onboarding.get('completed')} progress={onboarding.get('progress_percent')}",
        {"response": onboarding},
    )

    # trader profile save
    profile_payload = {
        "locale": api.locale,
        "trader_types": ["swing_trader"],
        "primary_timeframes": ["4h", "1d"],
        "asset_focus": ["bitcoin"],
        "investment_goals_list": ["build_wealth"],
        "experience_levels": ["intermediate"],
        "risk_profiles": ["balanced"],
        "behavior_flags": ["fomo"],
    }
    _, prefs = api.request("PATCH", "/api/assistant/preferences", json_body=profile_payload)
    _, prefs_roundtrip = api.request("GET", "/api/assistant/preferences")
    collected["preferences"] = prefs_roundtrip
    pref_ok = all(
        item in (prefs_roundtrip.get("preferences") or {}).get("trader_types", [])
        for item in ["swing_trader"]
    )
    add(
        "profile_save",
        pref_ok,
        "Traderprofiel wordt opgeslagen voor juiste user",
        pretty((prefs_roundtrip.get("preferences") or {})),
        {"patch_response": prefs, "roundtrip": prefs_roundtrip},
    )

    # onboarding asset anchor
    _, asset_prefs = api.request(
        "PATCH",
        "/api/assistant/preferences",
        json_body={"onboarding_asset": "BTC", "selected_asset": "BTC"},
    )
    _, watch_seed = api.request("POST", "/api/watchlist", json_body={"symbol": "BTC"})
    try:
        api.request("POST", "/api/market/asset/initialize", json_body={"symbol": "BTC"})
    except Exception:
        pass
    _, asset_status = api.request("POST", "/api/onboarding/complete_step", json_body={"step": "asset"})
    _, watchlist_after_asset = api.request("GET", "/api/watchlist")
    collected["onboarding_asset"] = {
        "preferences": asset_prefs,
        "watch_seed": watch_seed,
        "status": asset_status,
        "watchlist": watchlist_after_asset,
    }
    add(
        "onboarding_asset",
        bool(asset_status.get("has_asset")) and "BTC" in normalize_watchlist(watchlist_after_asset),
        "Nieuwe user kiest eerst een onboarding-asset die aan watchlist en state wordt gekoppeld",
        pretty({"status": asset_status, "watchlist": watchlist_after_asset}),
        {"preferences": asset_prefs, "watch_seed": watch_seed, "status": asset_status, "watchlist": watchlist_after_asset},
    )

    # watchlist add via FINN
    _, watch_payload = api.request(
        "POST",
        "/api/assistant/chat",
        json_body={
            "query": "Voeg ETH toe aan mijn watchlist.",
            "context": {"page": "dashboard"},
            "history": [],
            "session_id": f"fresh-watch-{uuid.uuid4().hex[:8]}",
        },
    )
    watch_action = extract_action_id(watch_payload)
    watch_exec = None
    if watch_action:
        _, watch_exec = api.request("POST", "/api/assistant/actions/execute", json_body={"action_id": watch_action})
    _, watchlist = api.request("GET", "/api/watchlist")
    collected["watchlist"] = {"chat": watch_payload, "execute": watch_exec, "list": watchlist}
    add(
        "watchlist_add",
        "ETH" in [str(item).upper() for item in watchlist],
        "Een extra asset wordt via FINN aan de volglijst toegevoegd",
        pretty(watchlist),
        {"chat": watch_payload, "execute": watch_exec},
    )

    # setup creation
    setup_payload = create_or_follow_up_setup(api, "BTC")
    setup_action = extract_action_id(setup_payload)
    setup_exec = None
    if setup_action:
        _, setup_exec = api.request("POST", "/api/assistant/actions/execute", json_body={"action_id": setup_action})
    _, setups = api.request("GET", "/api/setups")
    saved_setup = find_saved_setup(setups if isinstance(setups, list) else [], "BTC")
    setup_saved_ok = bool(saved_setup) and step_ok_from_execute(setup_exec)
    collected["setup"] = {"chat": setup_payload, "execute": setup_exec, "setups": setups, "saved_ok": setup_saved_ok}
    add(
        "setup_save",
        setup_saved_ok,
        "Setup wordt echt opgeslagen en blijft leesbaar",
        pretty({"execute": setup_exec, "saved_setup": saved_setup}),
        {"chat": setup_payload, "execute": setup_exec, "setups": setups, "saved_setup": saved_setup, "saved_ok": setup_saved_ok},
    )

    setup_id = int(
        (setup_exec or {}).get("setup_id")
        or nested_setup_id((setup_exec or {}).get("result"))
        or (saved_setup or {}).get("id")
        or 0
    )
    # strategy creation
    strategy_payload = create_or_follow_up_strategy(api, setup_id, "BTC")
    strategy_action = extract_action_id(strategy_payload)
    strategy_exec = None
    if strategy_action:
        _, strategy_exec = api.request("POST", "/api/assistant/actions/execute", json_body={"action_id": strategy_action})
    _, strategies = api.request("GET", f"/api/strategies/by_setup/{setup_id}")
    strategy_ok = isinstance(strategies, dict) and int(strategies.get("id") or 0) > 0
    strategy_saved_ok = bool(strategy_ok) and step_ok_from_execute(strategy_exec)
    collected["strategy"] = {"chat": strategy_payload, "execute": strategy_exec, "strategy": strategies, "saved_ok": strategy_saved_ok}
    add(
        "strategy_save",
        strategy_saved_ok,
        "Strategie wordt echt opgeslagen en gekoppeld aan setup",
        pretty({"execute": strategy_exec, "strategy": strategies}),
        {"chat": strategy_payload, "execute": strategy_exec, "strategy": strategies, "saved_ok": strategy_saved_ok},
    )

    strategy_id = int(
        (strategy_exec or {}).get("strategy_id")
        or nested_strategy_id((strategy_exec or {}).get("result"))
        or (strategies or {}).get("id")
        or 0
    )
    # bot/dca creation
    bot_payload = create_or_follow_up_bot(api, strategy_id, "BTC")
    bot_action = extract_action_id(bot_payload)
    bot_exec = None
    if bot_action:
        _, bot_exec = api.request("POST", "/api/assistant/actions/execute", json_body={"action_id": bot_action})
    _, bots = api.request("GET", "/api/bot/configs")
    saved_bot = find_saved_bot(bots if isinstance(bots, list) else [], strategy_id)
    bot_saved_ok = bool(step_ok_from_execute(bot_exec) and (saved_bot or (bot_exec or {}).get("bot_id")))
    collected["bot"] = {"chat": bot_payload, "execute": bot_exec, "bots": bots, "saved_bot": saved_bot, "saved_ok": bot_saved_ok}
    add(
        "bot_save",
        bot_saved_ok,
        "Bot/DCA-draft wordt echt opgeslagen of confirmable bot wordt aangemaakt",
        pretty({"execute": bot_exec, "saved_bot": saved_bot}),
        {"chat": bot_payload, "execute": bot_exec, "bots": bots, "saved_bot": saved_bot, "saved_ok": bot_saved_ok},
    )

    # dashboard and persistence
    _, dashboard = api.request("GET", "/api/dashboard")
    _, watchlist_after = api.request("GET", "/api/watchlist")
    _, setup_last = api.request("GET", "/api/setups/last")
    _, strategy_last = api.request("GET", "/api/strategies/last")
    _, bot_today = api.request("GET", "/api/bot/today?symbol=BTC")
    collected["dashboard"] = {
        "dashboard": dashboard,
        "watchlist": watchlist_after,
        "setup_last": setup_last,
        "strategy_last": strategy_last,
        "bot_today": bot_today,
    }
    dashboard_ok = "BTC" in normalize_watchlist(watchlist_after)
    add(
        "dashboard_check",
        dashboard_ok,
        "Dashboard/read endpoints tonen user-data na save",
        pretty({"watchlist": watchlist_after, "setup_last": setup_last, "strategy_last": strategy_last}),
        collected["dashboard"],
    )

    # logout/login persistence
    api.logout()
    api.login(email=email, password=password)
    _, watchlist_relogin = api.request("GET", "/api/watchlist")
    _, setup_last_relogin = api.request("GET", "/api/setups/last")
    _, strategy_last_relogin = api.request("GET", "/api/strategies/last")
    persisted = "BTC" in normalize_watchlist(watchlist_relogin)
    add(
        "logout_login_persistence",
        persisted,
        "Data blijft zichtbaar na opnieuw inloggen",
        pretty({"watchlist": watchlist_relogin, "setup_last": setup_last_relogin, "strategy_last": strategy_last_relogin}),
        {
            "watchlist": watchlist_relogin,
            "setup_last": setup_last_relogin,
            "strategy_last": strategy_last_relogin,
        },
    )

    return steps, collected


def run_isolation_check(
    *,
    user_a: ApiSession,
    user_b: ApiSession,
    user_a_data: Dict[str, Any],
) -> StepResult:
    _, watchlist_b = user_b.request("GET", "/api/watchlist")
    _, setup_last_b = user_b.request("GET", "/api/setups/last")
    _, strategy_last_b = user_b.request("GET", "/api/strategies/last")

    a_watchlist = normalize_watchlist(user_a_data.get("dashboard", {}).get("watchlist"))
    b_watchlist = normalize_watchlist(watchlist_b)
    leak = False
    reasons = []
    if "BTC" in b_watchlist and "BTC" in a_watchlist:
        # BTC alone is too generic to prove a leak; compare ids too.
        pass

    a_setup = (user_a_data.get("dashboard", {}).get("setup_last") or {}).get("setup")
    a_setup_id = int((a_setup or {}).get("id") or 0) if isinstance(a_setup, dict) else 0
    b_setup = (setup_last_b or {}).get("setup") if isinstance(setup_last_b, dict) else None
    b_setup_id = int((b_setup or {}).get("id") or 0)
    a_strategy = user_a_data.get("dashboard", {}).get("strategy_last")
    a_strategy_id = int((a_strategy or {}).get("id") or 0) if isinstance(a_strategy, dict) else 0
    b_strategy_id = int((strategy_last_b or {}).get("id") or 0) if isinstance(strategy_last_b, dict) else 0

    if a_setup_id and b_setup_id and a_setup_id == b_setup_id:
        leak = True
        reasons.append(f"setup_id shared ({a_setup_id})")
    if a_strategy_id and b_strategy_id and a_strategy_id == b_strategy_id:
        leak = True
        reasons.append(f"strategy_id shared ({a_strategy_id})")

    return StepResult(
        name="user_isolation",
        status="fail" if leak else "pass",
        expected="User B ziet nooit User A data",
        actual=pretty(
            {
                "user_b_watchlist": watchlist_b,
                "user_b_setup_last": setup_last_b,
                "user_b_strategy_last": strategy_last_b,
                "reasons": reasons,
            }
        ),
        detail={
            "user_b_watchlist": watchlist_b,
            "user_b_setup_last": setup_last_b,
            "user_b_strategy_last": strategy_last_b,
            "reasons": reasons,
        },
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default=os.getenv("TRADAMIND_BASE_URL", DEFAULT_BASE_URL))
    parser.add_argument("--locale", default="nl")
    parser.add_argument("--output", default="")
    args = parser.parse_args()

    base_url = args.base_url.rstrip("/")
    locale = args.locale
    password = "Codex!FreshE2E123"
    email_a = build_user_email("fresh-a")
    email_b = build_user_email("fresh-b")

    api_a = ApiSession(base_url, locale=locale)
    api_b = ApiSession(base_url, locale=locale)

    report: Dict[str, Any] = {
        "base_url": base_url,
        "locale": locale,
        "started_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "user_a": {"email": email_a},
        "user_b": {"email": email_b},
        "steps": [],
        "status": "pass",
    }

    try:
        steps_a, collected_a = run_flow(api_a, "FreshA", email_a, password)
        report["steps"].extend([step.__dict__ for step in steps_a])

        # B only registers/logs in for isolation baseline.
        api_b.register(first_name="FreshB", email=email_b, password=password)
        api_b.login(email=email_b, password=password)
        api_b.me()
        isolation = run_isolation_check(user_a=api_a, user_b=api_b, user_a_data=collected_a)
        report["steps"].append(isolation.__dict__)
        if any(step.status == "fail" for step in steps_a) or isolation.status == "fail":
            report["status"] = "fail"

    except Exception as exc:
        report["status"] = "fail"
        report["fatal_error"] = str(exc)

    payload = pretty(report)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as fh:
            fh.write(payload + "\n")
    print(payload)
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    sys.exit(main())
