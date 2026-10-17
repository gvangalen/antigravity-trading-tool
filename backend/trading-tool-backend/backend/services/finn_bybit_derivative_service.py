"""Read-only Bybit derivative evidence and conservative position arithmetic.

Execution/list has no positionIdx. Callers must join each execution to its
owner-scoped order/history record before using these functions. A derived flat
episode is not automatically exchange-proven without a provider baseline and
continuous coverage after that baseline.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any
import time


DERIVATIVE_CATEGORIES = {"linear", "inverse"}
POSITION_INDEXES = {0, 1, 2}
MATERIAL_EVENTS = {"AdlTrade", "BustTrade", "Funding", "Delivery", "Settle",
                   "BlockTrade", "MovePosition", "FutureSpread", "SessionSettlePnL",
                   "ForwardSplitSettle", "ReverseSplitSettle"}
DAY_MS = 86_400_000
HISTORY_MS = 2 * 365 * DAY_MS


def initial_cursor(now_ms: int) -> dict:
    return {"window_start_ms": max(0, now_ms - HISTORY_MS),
            "window_end_ms": None, "page_cursor": None}


async def derivative_page(client, category: str, cursor: dict, now_ms: int) -> tuple[list[dict], dict, int | None]:
    """One bounded V5 execution page. Cursor advances only after normalization."""
    if category not in DERIVATIVE_CATEGORIES:
        raise ValueError("Ongeldige Bybit-derivatencategorie")
    start = int(cursor["window_start_ms"])
    end = int(cursor.get("window_end_ms") or min(start + 7 * DAY_MS - 1, now_ms))
    if start <= 0 or end < start or end - start >= 7 * DAY_MS:
        raise ValueError("Ongeldig Bybit-importvenster")
    params = {"category": category, "startTime": start, "endTime": end, "limit": 100}
    if cursor.get("page_cursor"):
        token = str(cursor["page_cursor"])
        if not token.isascii() or not token.isprintable() or len(token) > 512:
            raise ValueError("Ongeldige Bybit-cursor")
        params["cursor"] = token
    response = await client.privateGetV5ExecutionList(params)
    if not isinstance(response, dict) or response.get("retCode") != 0:
        raise ValueError("Bybit-uitvoeringen niet beschikbaar")
    result = response.get("result") or {}
    rows = result.get("list")
    if result.get("category") != category or not isinstance(rows, list) or len(rows) > 100:
        raise ValueError("Ongeldige Bybit-uitvoeringspagina")
    normalized = []
    for row in rows:
        try:
            market = client.market(row.get("symbol"))
        except Exception:
            # Historical delisted instruments may be absent from today's CCXT
            # market catalogue. Keep the provider event as a material gap.
            market = None
        evidence = normalize_execution(row, category=category, market=market)
        ms = round(evidence["traded_at"].timestamp() * 1000)
        if not start <= ms <= end or ms > now_ms + 60_000:
            raise ValueError("Bybit-uitvoering buiten importvenster")
        normalized.append(evidence)
    token = str(result.get("nextPageCursor") or "")
    next_cursor = dict(cursor)
    if token:
        if (token == cursor.get("page_cursor") or len(token) > 512 or
                not token.isascii() or not token.isprintable()):
            raise ValueError("Bybit-cursor schuift niet op")
        next_cursor.update({"page_cursor": token, "window_end_ms": end})
        return normalized, next_cursor, None
    next_cursor.update({"page_cursor": None, "window_end_ms": None,
                        "window_start_ms": end + 1 if end < now_ms else max(now_ms - 7 * DAY_MS, start)})
    return normalized, next_cursor, end


def amount(value: Any, *, allow_zero: bool = False, signed: bool = False) -> Decimal:
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        raise ValueError("Ongeldige Bybit-waarde") from None
    if not parsed.is_finite() or (not signed and (parsed < 0 if allow_zero else parsed <= 0)):
        raise ValueError("Ongeldige Bybit-waarde")
    return parsed


def normalize_execution(raw: dict, *, category: str, market: dict | None) -> dict:
    """Persist normalized provider facts, including non-Trade gap events."""
    if category not in DERIVATIVE_CATEGORIES:
        raise ValueError("Ongeldige Bybit-derivatencategorie")
    symbol = str(raw.get("symbol") or "").upper()
    if not symbol.isascii() or not symbol.isalnum() or not 1 <= len(symbol) <= 40:
        raise ValueError("Ongeldig Bybit-contractsymbool")
    event = str(raw.get("execType") or "")
    if not event.isascii() or not event.isalnum() or not 1 <= len(event) <= 64:
        raise ValueError("Ongeldige Bybit-uitvoeringssoort")
    exec_id = str(raw.get("execId") or "")
    order_id = str(raw.get("orderId") or "")
    if not exec_id.isascii() or not 1 <= len(exec_id) <= 128:
        raise ValueError("Bybit-uitvoerings-ID ontbreekt")
    try:
        millis = int(raw.get("execTime"))
    except (TypeError, ValueError, OverflowError):
        raise ValueError("Bybit-uitvoeringstijd ontbreekt") from None
    if millis <= 0:
        raise ValueError("Bybit-uitvoeringstijd ontbreekt")
    at = datetime.fromtimestamp(millis / 1000, tz=timezone.utc)
    if market is None:
        return {"category": category, "symbol": symbol, "base_currency": None,
                "quote_currency": None, "settle_currency": "UNKNOWN",
                "contract_size": None, "exec_id": exec_id,
                "order_id": order_id or None, "exec_type": event,
                "traded_at": at, "evidence_status": "material_event_unmodeled"}
    if not market.get("contract"):
        raise ValueError("Ongeldig Bybit-derivatencontract")
    if (category == "linear") != bool(market.get("linear")) or (
            category == "inverse") != bool(market.get("inverse")):
        raise ValueError("Bybit-contractcategorie komt niet overeen")
    if symbol != str(market.get("id") or "").upper() or not symbol:
        raise ValueError("Bybit-contractsymbool komt niet overeen")
    settle = str(market.get("settle") or "").upper()
    if not settle or len(settle) > 20 or not settle.isalnum():
        raise ValueError("Bybit-settlementvaluta ontbreekt")
    base = str(market.get("base") or "").upper() or None
    quote = str(market.get("quote") or "").upper() or None
    if any(value and (len(value) > 20 or not value.isalnum()) for value in (base, quote)):
        raise ValueError("Ongeldige Bybit-contractvaluta")
    contract_size = amount(market.get("contractSize")) if market.get("contractSize") is not None else None
    if event == "Trade" and (not order_id.isascii() or not 1 <= len(order_id) <= 128):
        raise ValueError("Bybit-order-ID ontbreekt")
    if event != "Trade":
        return {"category": category, "symbol": symbol, "base_currency": base,
                "quote_currency": quote, "settle_currency": settle,
                "contract_size": contract_size,
                "exec_id": exec_id, "order_id": order_id or None, "exec_type": event,
                "traded_at": at, "evidence_status": "material_event_unmodeled"}
    side = str(raw.get("side") or "").lower()
    if side not in {"buy", "sell"}:
        raise ValueError("Ongeldige Bybit-richting")
    qty = amount(raw.get("execQty"))
    price = amount(raw.get("execPrice"))
    execution_value = amount(raw.get("execValue"))
    fee = amount(raw.get("execFee"), signed=True) if raw.get("execFee") not in (None, "") else None
    closed_raw = raw.get("closedSize")
    closed_size = amount(closed_raw, allow_zero=True) if closed_raw not in (None, "") else None
    if closed_size is not None and closed_size > qty:
        raise ValueError("Bybit-gesloten hoeveelheid groter dan uitvoering")
    fee_currency = str(raw.get("feeCurrency") or "").upper() or None
    if fee_currency and (len(fee_currency) > 20 or not fee_currency.isalnum()):
        raise ValueError("Ongeldige Bybit-feevaluta")
    try:
        seq = int(raw["seq"]) if raw.get("seq") not in (None, "") else None
    except (TypeError, ValueError, OverflowError):
        raise ValueError("Ongeldige Bybit-volgorde") from None
    if seq is not None and seq < 0:
        raise ValueError("Ongeldige Bybit-volgorde")
    return {"category": category, "symbol": symbol, "base_currency": base,
            "quote_currency": quote, "settle_currency": settle,
            "contract_size": contract_size,
            "exec_id": exec_id, "order_id": order_id, "exec_type": event,
            "side": side, "qty": qty, "price": price,
            "execution_value": execution_value, "fee_amount": fee,
            "fee_currency": fee_currency, "closed_size": closed_size,
            "seq": seq, "traded_at": at, "evidence_status": "trade_order_pending"}


def normalize_order(raw: dict, *, category: str, order_id: str, symbol: str) -> dict:
    if category not in DERIVATIVE_CATEGORIES:
        raise ValueError("Ongeldige Bybit-categorie")
    if str(raw.get("orderId")) != order_id or str(raw.get("symbol") or "").upper() != symbol:
        raise ValueError("Bybit-order hoort niet bij uitvoering")
    idx = raw.get("positionIdx")
    if type(idx) is not int or idx not in POSITION_INDEXES:
        raise ValueError("Bybit-positionIdx ontbreekt")
    side = str(raw.get("side") or "").lower()
    if side not in {"buy", "sell"}:
        raise ValueError("Ongeldige Bybit-orderrichting")
    return {"position_idx": idx, "side": side,
            "reduce_only": raw.get("reduceOnly") is True,
            "order_status": str(raw.get("orderStatus") or "")}


def closed_episodes(executions: list[dict], *, initial_signed_qty: Decimal = Decimal(0),
                    stop_after_first: bool = False) -> tuple[list[dict], Decimal]:
    """Split flat episodes, including the close/open slices of a reversal.

    This is arithmetic over selected evidence. The caller must establish the
    provider baseline or obtain explicit user attestation before persistence.
    """
    if not executions:
        return [], initial_signed_qty
    category = executions[0]["category"]
    symbol = executions[0]["symbol"]
    idx = executions[0]["position_idx"]
    if category not in DERIVATIVE_CATEGORIES or idx not in POSITION_INDEXES:
        raise ValueError("Onvolledige orderkoppeling")
    if any((row.get("category"), row.get("symbol"), row.get("position_idx")) !=
           (category, symbol, idx) or row.get("exec_type") != "Trade" for row in executions):
        raise ValueError("Uitvoeringen behoren niet tot één positie-stream")
    ordered = sorted(executions, key=lambda row: (row["traded_at"], row.get("seq") if row.get("seq") is not None else -1, row["exec_id"]))
    balance = amount(initial_signed_qty, signed=True)
    active: list[dict] = []
    completed: list[dict] = []
    direction = "long" if balance > 0 else "short" if balance < 0 else None
    tainted_by_preexisting_position = balance != 0
    previous = None
    for row in ordered:
        if (previous is not None and previous["traded_at"] == row["traded_at"] and
                (previous.get("seq") is None or row.get("seq") is None or
                 previous["seq"] == row["seq"]) and
                previous["side"] != row["side"]):
            raise ValueError("Gelijke Bybit-tijd zonder betrouwbare uitvoeringsvolgorde")
        previous = row
        qty = amount(row["qty"])
        delta = qty if row["side"] == "buy" else -qty
        if idx == 1 and delta < 0 and balance <= 0:
            raise ValueError("Hedge-long sluit meer dan geopend")
        if idx == 2 and delta > 0 and balance >= 0:
            raise ValueError("Hedge-short sluit meer dan geopend")
        before = balance
        after = balance + delta
        if (idx == 1 and after < 0) or (idx == 2 and after > 0):
            raise ValueError("Hedge-positie overschrijdt nul")
        closing = min(abs(before), qty) if before and before * delta < 0 else Decimal(0)
        opening = qty - closing
        reported = row.get("closed_size")
        if reported is not None and amount(reported, allow_zero=True) != closing:
            raise ValueError("Bybit closedSize botst met positieberekening")
        if closing:
            active.append({"execution_id": row["id"], "exec_id": row["exec_id"],
                           "role": "close", "qty": closing, "at": row["traded_at"]})
        balance = before + (closing if before < 0 else -closing)
        if before and balance == 0:
            if not tainted_by_preexisting_position and any(part["role"] == "open" for part in active):
                completed.append({"category": category, "symbol": symbol,
                                  "position_idx": idx, "direction": direction,
                                  "entry_at": active[0]["at"], "exit_at": row["traded_at"],
                                  "slices": active})
                if stop_after_first:
                    return completed, Decimal(0)
            active = []
            direction = None
            tainted_by_preexisting_position = False
        if opening:
            if balance != 0 and before * delta < 0:
                raise ValueError("Ongeldige Bybit-positieovergang")
            if balance == 0:
                direction = "long" if delta > 0 else "short"
            active.append({"execution_id": row["id"], "exec_id": row["exec_id"],
                           "role": "open", "qty": opening, "at": row["traded_at"]})
            balance += opening if delta > 0 else -opening
        if not closing and not opening:
            raise ValueError("Lege Bybit-allocatie")
    return completed, balance
