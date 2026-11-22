"""Read-only AAPL Paper quote gate. This never invokes a bot worker."""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

from backend.scripts import probe_protected_score2_stale_paper as fixture
from backend.services.portfolio_fx_service import trade_quote_context


FAILURES = frozenset({
    "aapl_quote_read_not_authorized", "aapl_quote_read_owner_invalid",
    "aapl_quote_read_contract_failed", "aapl_quote_read_runtime_failed",
})


def _bound_owner() -> int:
    if (os.getenv("FINN_QA_ALLOW_AAPL_STALE_QUOTE_READ") != "1"
            or os.getenv("FINN_QA_ALLOW_FIXTURE_ACTIONS") != "0"
            or os.getenv("FINN_QA_ALLOW_FIXTURE_EXECUTION") != "0"):
        raise RuntimeError("aapl_quote_read_not_authorized")
    value = os.getenv("FINN_QA_USER_ID", "")
    if not value.isdecimal() or int(value) <= 0:
        raise RuntimeError("aapl_quote_read_not_authorized")
    return int(value)


def _owner_preflight(owner: int) -> None:
    connection = fixture._connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT role,is_active,ai_preferences FROM users WHERE id=%s", (owner,))
            row = cursor.fetchone()
            if (not row or row[0] != "user" or row[1] is not True
                    or (row[2] or {}).get("qa_fixture") != fixture.QA_OWNER_MARKER):
                raise RuntimeError("aapl_quote_read_owner_invalid")
            cursor.execute("SELECT COUNT(*) FROM exchange_keys WHERE user_id=%s", (owner,))
            if cursor.fetchone()[0]:
                raise RuntimeError("aapl_quote_read_owner_invalid")
    finally:
        connection.close()


def _contract_cases() -> bool:
    now = datetime(2026, 11, 22, 12, tzinfo=timezone.utc)
    fx = {"eur_per_unit": 0.9, "observed_at": now - timedelta(minutes=5)}
    common = {"price": 250, "row_quote": "USD", "catalog_quote": "USD",
              "usd_fx": fx, "quote_fx": fx, "now": now}
    fresh = trade_quote_context(**common, price_at=now - timedelta(minutes=29))
    stale = trade_quote_context(**common, price_at=now - timedelta(minutes=31))
    undated = trade_quote_context(**common, price_at=None)
    wrong_quote = trade_quote_context(**{**common, "row_quote": "EUR"}, price_at=now)
    return (fresh.get("reason") is None and fresh.get("market_price_eur") is not None
            and stale == {"reason": "market_price_stale"}
            and undated == {"reason": "market_price_stale"}
            and wrong_quote == {"reason": "market_quote_unverified"})


def run() -> dict:
    owner = _bound_owner()
    _owner_preflight(owner)
    if not _contract_cases():
        raise RuntimeError("aapl_quote_read_contract_failed")
    from backend.engine.trading_bot_execution import _get_trade_quote_fx_context

    connection = fixture._connection()
    try:
        # The same reader used by Paper execution, but no execution function.
        context = _get_trade_quote_fx_context(connection, "AAPL", require_usd=True)
    finally:
        connection.close()
    reason = context.get("reason")
    if reason == "market_price_stale":
        if context.get("market_price_eur") is not None:
            raise RuntimeError("aapl_quote_read_contract_failed")
        return {"result": "PASS", "boundary_cases": True,
                "live_source": "stale", "quote_reason": "market_price_stale",
                "worker_invoked": False}
    if reason is None:
        return {"result": "INCONCLUSIVE", "boundary_cases": True,
                "live_source": "fresh", "worker_invoked": False}
    if reason in {"market_quote_unverified", "usd_eur_fx_unavailable",
                  "market_quote_eur_fx_unavailable", "trade_quote_sources_out_of_sync"}:
        return {"result": "INCONCLUSIVE", "boundary_cases": True,
                "live_source": "unavailable", "quote_reason": reason,
                "worker_invoked": False}
    raise RuntimeError("aapl_quote_read_contract_failed")
