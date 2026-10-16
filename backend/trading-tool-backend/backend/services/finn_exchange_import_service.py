"""Read-only, bounded ingestion of linked exchange execution evidence.

Provider payloads and credentials never reach FINN. The staged rows do not
change bot orders, ledgers or portfolios. Bybit history before its two-year
provider window, non-trade transfers and Bitvavo Price Guarantee fills remain
explicit gaps rather than guessed positions or EUR PnL.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import time
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any

from fastapi import HTTPException
from sqlalchemy import text

from backend.infrastructure.repositories.exchange_repository import ExchangeRepository
from backend.services.exchange_service import ExchangeService
from backend.services.finn_trade_review_rollout import require_trade_review_access
from backend.utils.encryption_utils import EncryptionUtils


DAY_MS = 86_400_000
BYBIT_HISTORY_MS = 2 * 365 * DAY_MS
MAX_PAGES_PER_SYNC = 5
MAX_MARKETS = 100
MAX_ACTIVE_DAYS = 10_000
IDENTIFIER = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")
CURRENCY = re.compile(r"^[A-Z0-9]{2,20}$")


def _hash_identity(value: str) -> str:
    secret = os.getenv("ENCRYPTION_KEY")
    if not secret:
        raise RuntimeError("Exchange identity key unavailable")
    return hmac.new(secret.encode(), value.encode(), hashlib.sha256).hexdigest()


def _decimal(value: Any, *, positive: bool = True) -> Decimal:
    try:
        number = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        raise ValueError("Invalid provider amount") from None
    if not number.is_finite() or (positive and number <= 0) or (not positive and number < 0):
        raise ValueError("Invalid provider amount")
    return number


def _identifier(value: Any) -> str:
    result = str(value or "")
    if not IDENTIFIER.fullmatch(result):
        raise ValueError("Invalid provider identity")
    return result


def _pair(symbol: Any) -> tuple[str, str, str]:
    pair = str(symbol or "").upper().replace("-", "/")
    parts = pair.split("/")
    if len(parts) != 2 or not all(CURRENCY.fullmatch(part) for part in parts) or parts[0] == parts[1]:
        raise ValueError("Unsupported provider spot pair")
    return pair, parts[0], parts[1]


def normalize_bitvavo(raw: dict, market: str) -> dict:
    symbol, base, quote = _pair(raw.get("market"))
    if symbol != _pair(market)[0] or raw.get("settled") is not True:
        raise ValueError("Unsettled or mismatched Bitvavo fill")
    side = str(raw.get("side") or "").lower()
    if side not in {"buy", "sell"}:
        raise ValueError("Invalid provider side")
    qty, price = _decimal(raw.get("amount")), _decimal(raw.get("price"))
    fee_currency = str(raw.get("feeCurrency") or "").upper() or None
    if fee_currency and not CURRENCY.fullmatch(fee_currency):
        raise ValueError("Invalid provider fee currency")
    try:
        timestamp = int(raw.get("timestamp"))
    except (TypeError, ValueError, OverflowError):
        raise ValueError("Invalid provider timestamp") from None
    if not 0 < timestamp <= int(time.time() * 1000) + 60_000:
        raise ValueError("Invalid provider timestamp")
    return {
        "exchange_trade_id": _identifier(raw.get("id")),
        "exchange_order_id": _identifier(raw.get("orderId")),
        "symbol": symbol, "base_currency": base, "quote_currency": quote,
        "side": side, "qty": qty, "price_quote": price,
        "cost_quote": qty * price,
        "fee_amount": _decimal(raw["fee"], positive=False) if raw.get("fee") is not None else None,
        "fee_currency": fee_currency,
        "traded_at": datetime.fromtimestamp(timestamp / 1000, tz=timezone.utc),
    }


def normalize_bybit(raw: dict, market_symbol: str) -> dict:
    symbol, base, quote = _pair(market_symbol)
    if str(raw.get("execType")) != "Trade":
        raise ValueError("Non-trade Bybit execution")
    side = str(raw.get("side") or "").lower()
    if side not in {"buy", "sell"}:
        raise ValueError("Invalid provider side")
    qty, price, cost = (_decimal(raw.get("execQty")), _decimal(raw.get("execPrice")),
                        _decimal(raw.get("execValue")))
    if abs(cost - qty * price) > max(Decimal("0.00000001"), cost * Decimal("0.001")):
        raise ValueError("Provider cost differs from quantity and price")
    fee_currency = str(raw.get("feeCurrency") or "").upper() or None
    if fee_currency and not CURRENCY.fullmatch(fee_currency):
        raise ValueError("Invalid provider fee currency")
    try:
        timestamp = int(raw.get("execTime"))
    except (TypeError, ValueError, OverflowError):
        raise ValueError("Invalid provider timestamp") from None
    if not 0 < timestamp <= int(time.time() * 1000) + 60_000:
        raise ValueError("Invalid provider timestamp")
    return {
        "exchange_trade_id": _identifier(raw.get("execId")),
        "exchange_order_id": _identifier(raw.get("orderId")),
        "symbol": symbol, "base_currency": base, "quote_currency": quote,
        "side": side, "qty": qty, "price_quote": price, "cost_quote": cost,
        "fee_amount": _decimal(raw["execFee"], positive=False) if raw.get("execFee") not in (None, "") else None,
        "fee_currency": fee_currency,
        "traded_at": datetime.fromtimestamp(timestamp / 1000, tz=timezone.utc),
    }


def _discover_market(item: dict) -> str | None:
    side = str(item.get("type") or "").lower()
    if side not in {"buy", "sell"}:
        return None
    base = item.get("receivedCurrency") if side == "buy" else item.get("sentCurrency")
    quote = item.get("priceCurrency")
    try:
        market, _, _ = _pair(f"{base}/{quote}")
    except ValueError:
        return None
    return market


def initial_cursor(exchange_name: str, now_ms: int) -> dict:
    since = max(0, now_ms - BYBIT_HISTORY_MS) if exchange_name == "bybit" else 0
    if exchange_name == "bybit":
        return {"window_start_ms": since, "window_end_ms": None, "page_cursor": None}
    return {"phase": "discover", "since_ms": since, "snapshot_until_ms": now_ms, "page": 1,
            "markets": [], "activity_days": {}, "market_index": 0, "day_index": 0,
            "window_start_ms": since,
            "trade_id_to": None}


async def provider_page(client, exchange_name: str, cursor: dict, now_ms: int) -> tuple[list[dict], dict, int | None]:
    """Return one normalized page, next persisted cursor and completed coverage."""
    next_cursor = dict(cursor)
    if exchange_name == "bybit":
        start = int(cursor["window_start_ms"])
        end = int(cursor.get("window_end_ms") or min(start + 7 * DAY_MS - 1, now_ms))
        params = {"category": "spot", "execType": "Trade", "startTime": start,
                  "endTime": end, "limit": 100}
        if cursor.get("page_cursor"):
            page_cursor = str(cursor["page_cursor"])
            if not page_cursor.isascii() or not page_cursor.isprintable() or len(page_cursor) > 512:
                raise ValueError("Invalid Bybit page cursor")
            params["cursor"] = page_cursor
        response = await client.privateGetV5ExecutionList(params)
        if not isinstance(response, dict) or response.get("retCode") != 0:
            raise ValueError("Bybit execution page unavailable")
        result = response.get("result") or {}
        rows = result.get("list")
        if not isinstance(rows, list) or len(rows) > 100 or result.get("category") != "spot":
            raise ValueError("Invalid Bybit execution page")
        normalized = []
        for row in rows:
            market = client.market(row.get("symbol"))
            if not market or not market.get("spot"):
                raise ValueError("Non-spot Bybit market in execution page")
            normalized.append(normalize_bybit(row, market["symbol"]))
        next_page = str(result.get("nextPageCursor") or "")
        if next_page:
            if (next_page == cursor.get("page_cursor") or len(next_page) > 512
                    or not next_page.isascii() or not next_page.isprintable()):
                raise ValueError("Bybit pagination did not advance")
            next_cursor["page_cursor"] = next_page
            next_cursor["window_end_ms"] = end
            return normalized, next_cursor, None
        next_cursor["page_cursor"] = None
        next_cursor["window_end_ms"] = None
        next_cursor["window_start_ms"] = end + 1 if end < now_ms else max(now_ms - 7 * DAY_MS, start)
        return normalized, next_cursor, end

    if exchange_name != "bitvavo":
        raise ValueError("Unsupported exchange")
    if cursor.get("phase") == "discover":
        response = await client.request("account/history", "private", "GET", {
            "fromDate": int(cursor["since_ms"]), "toDate": int(cursor["snapshot_until_ms"]),
            "page": int(cursor["page"]), "maxItems": 100,
        })
        if not isinstance(response, dict) or not isinstance(response.get("items"), list):
            raise ValueError("Bitvavo account history unavailable")
        current, total = int(response.get("currentPage") or 0), int(response.get("totalPages") or 0)
        if (current != int(cursor["page"]) or (total != 0 and total < current)
                or len(response["items"]) > 100 or (total == 0 and response["items"])):
            raise ValueError("Invalid Bitvavo history pagination")
        markets = set(cursor.get("markets") or [])
        activity_days = {key: list(value) for key, value in (cursor.get("activity_days") or {}).items()}
        for item in response["items"]:
            market = _discover_market(item)
            if market:
                markets.add(market)
                try:
                    executed_at = datetime.fromisoformat(str(item["executedAt"]).replace("Z", "+00:00"))
                    if executed_at.tzinfo is None:
                        raise ValueError("Missing provider timezone")
                    executed_ms = int(executed_at.timestamp() * 1000)
                    if (executed_ms < int(cursor["since_ms"])
                            or executed_ms > int(cursor["snapshot_until_ms"])):
                        raise ValueError("Invalid provider timestamp")
                except (KeyError, TypeError, ValueError) as exc:
                    raise ValueError("Invalid Bitvavo account-history timestamp") from exc
                day = executed_ms // DAY_MS * DAY_MS
                days = set(activity_days.get(market, []))
                days.add(day)
                activity_days[market] = sorted(days)
        if len(markets) > MAX_MARKETS:
            raise ValueError("Too many Bitvavo markets for bounded sync")
        if sum(len(days) for days in activity_days.values()) > MAX_ACTIVE_DAYS:
            raise ValueError("Too many Bitvavo activity days for bounded sync")
        next_cursor["markets"] = sorted(markets)
        next_cursor["activity_days"] = activity_days
        if current < total:
            next_cursor["page"] = current + 1
        else:
            next_cursor.update({"phase": "trades", "market_index": 0, "day_index": 0,
                                "window_start_ms": int(activity_days[next_cursor["markets"][0]][0])
                                if markets else int(cursor["since_ms"]), "trade_id_to": None})
        return [], next_cursor, None

    markets = cursor.get("markets") or []
    index = int(cursor.get("market_index") or 0)
    if index >= len(markets):
        next_cursor.update({"phase": "discover", "since_ms": max(now_ms - 2 * DAY_MS, 0),
                            "snapshot_until_ms": now_ms,
                            "page": 1, "markets": [], "activity_days": {},
                            "market_index": 0, "day_index": 0,
                            "window_start_ms": max(now_ms - 2 * DAY_MS, 0),
                            "trade_id_to": None})
        return [], next_cursor, now_ms
    market = _pair(markets[index])[0]
    days = (cursor.get("activity_days") or {}).get(market) or []
    day_index = int(cursor.get("day_index") or 0)
    if day_index >= len(days):
        raise ValueError("Invalid Bitvavo activity-day cursor")
    start = int(days[day_index])
    end = min(start + DAY_MS - 1, int(cursor["snapshot_until_ms"]))
    params = {"market": market.replace("/", "-"), "start": start, "end": end, "limit": 1000}
    if cursor.get("trade_id_to"):
        params["tradeIdTo"] = _identifier(cursor["trade_id_to"])
    rows = await client.privateGetTrades(params)
    if not isinstance(rows, list) or len(rows) > 1000:
        raise ValueError("Invalid Bitvavo trade page")
    normalized = [normalize_bitvavo(row, market) for row in rows]
    if len(rows) == 1000:
        tail_id = _identifier(rows[-1].get("id"))
        if tail_id == cursor.get("trade_id_to"):
            raise ValueError("Bitvavo pagination did not advance")
        next_cursor["trade_id_to"] = tail_id
        return normalized, next_cursor, None
    next_cursor["trade_id_to"] = None
    next_cursor["day_index"] = day_index + 1
    if day_index + 1 >= len(days):
        next_cursor["market_index"] = index + 1
        next_cursor["day_index"] = 0
    complete = index + 1 >= len(markets) and day_index + 1 >= len(days)
    return normalized, next_cursor, now_ms if complete else None


class FinnExchangeImportService:
    def __init__(self, session):
        self.session = session

    async def fills(self, user_id: int, source_id: int, *, limit: int = 50, offset: int = 0) -> dict:
        require_trade_review_access(user_id)
        if not 1 <= limit <= 100 or not 0 <= offset <= 10_000:
            raise HTTPException(422, "Ongeldige importpagina")
        source_result = await self.session.execute(text("""
            SELECT id, exchange_name, status FROM finn_exchange_import_sources
            WHERE id=:source_id AND user_id=:user_id
        """), {"source_id": source_id, "user_id": user_id})
        source = source_result.fetchone()
        if source is None:
            raise HTTPException(404, "Exchange-import niet gevonden")
        count_result = await self.session.execute(text("""
            SELECT COUNT(*) FROM finn_exchange_import_fills
            WHERE user_id=:user_id AND source_id=:source_id
        """), {"user_id": user_id, "source_id": source_id})
        result = await self.session.execute(text("""
            SELECT f.id, f.symbol, f.side, f.qty, f.price_quote, f.cost_quote,
                   f.quote_currency, f.fee_amount, f.fee_currency, f.traded_at,
                   EXISTS (
                       SELECT 1 FROM bot_orders o
                       WHERE o.user_id=f.user_id
                         AND LOWER(o.exchange_name)=:exchange_name
                         AND UPPER(REPLACE(o.exchange_symbol, '-', '/'))=f.symbol
                         AND o.exchange_order_id=f.exchange_order_id
                   ) AS tradamind_order_candidate
            FROM finn_exchange_import_fills f
            WHERE f.user_id=:user_id AND f.source_id=:source_id
            ORDER BY f.traded_at DESC, f.id DESC
            LIMIT :limit OFFSET :offset
        """), {"user_id": user_id, "source_id": source_id,
               "exchange_name": source.exchange_name, "limit": limit, "offset": offset})
        return {"source_id": source_id, "exchange_name": source.exchange_name,
                "status": source.status, "total": count_result.scalar_one(),
                "items": [dict(row._mapping) for row in result.fetchall()]}

    async def status(self, user_id: int) -> list[dict]:
        require_trade_review_access(user_id)
        keys = await ExchangeRepository(self.session).get_active_keys(user_id)
        result = await self.session.execute(text("""
            SELECT s.id, s.exchange_name, s.identity_kind, s.credential_fingerprint, s.status,
                   s.coverage_start_at, s.coverage_through_at, s.last_success_at,
                   s.last_error_code, COUNT(f.id) AS imported_fills,
                   COUNT(f.id) FILTER (WHERE EXISTS (
                       SELECT 1 FROM bot_orders o
                       WHERE o.user_id=f.user_id
                         AND LOWER(o.exchange_name)=s.exchange_name
                         AND UPPER(REPLACE(o.exchange_symbol, '-', '/'))=f.symbol
                         AND o.exchange_order_id=f.exchange_order_id
                   )) AS tradamind_order_candidates
            FROM finn_exchange_import_sources s
            LEFT JOIN finn_exchange_import_fills f ON f.source_id=s.id AND f.user_id=s.user_id
            WHERE s.user_id=:user_id
            GROUP BY s.id ORDER BY s.updated_at DESC
        """), {"user_id": user_id})
        rows = [dict(row._mapping) for row in result.fetchall()]
        attempt_result = await self.session.execute(text("""
            SELECT exchange_name, last_attempt_at, last_error_code
            FROM finn_exchange_import_attempts WHERE user_id=:user_id
        """), {"user_id": user_id})
        attempts = {row.exchange_name: row for row in attempt_result.fetchall()}
        connected = {}
        for key in keys:
            name = key.exchange_name.lower()
            if name in {"bitvavo", "bybit"}:
                credential = EncryptionUtils.decrypt(key.api_key)
                connected[name] = _hash_identity(f"key:{name}:{credential}")
        for row in rows:
            current_fingerprint = connected.get(str(row["exchange_name"]).lower())
            if not current_fingerprint or row["credential_fingerprint"] != current_fingerprint:
                row["status"] = "credential_changed"
            row.pop("credential_fingerprint")
        for name, fingerprint in connected.items():
            if not any(row["exchange_name"] == name and row["status"] != "credential_changed"
                       for row in rows):
                attempt = attempts.get(name)
                rows.append({"exchange_name": name,
                             "status": "error" if attempt and attempt.last_error_code else "not_started",
                             "identity_kind": None, "coverage_start_at": None,
                             "coverage_through_at": None, "last_success_at": None,
                             "last_error_code": attempt.last_error_code if attempt else None,
                             "imported_fills": 0,
                             "tradamind_order_candidates": 0})
        for row in rows:
            row["review_eligibility"] = "unverified_position_basis"
            row["history_limit"] = ("two_year_provider_window" if row["exchange_name"] == "bybit"
                                    else "account_history_discovery_trades_exclude_price_guarantee")
        return rows

    async def sync(self, user_id: int, exchange_name: str) -> dict:
        require_trade_review_access(user_id)
        exchange_name = exchange_name.lower()
        if exchange_name not in {"bitvavo", "bybit"}:
            raise HTTPException(422, "Exchange niet ondersteund")
        lock = await self.session.execute(text("SELECT pg_try_advisory_xact_lock(:user_id, 741072)"),
                                          {"user_id": user_id})
        if not lock.scalar_one():
            raise HTTPException(409, "Exchange-import loopt al")
        recent_attempt = await self.session.execute(text("""
            SELECT last_attempt_at > NOW() - INTERVAL '5 minutes'
            FROM finn_exchange_import_attempts
            WHERE user_id=:user_id AND exchange_name=:exchange_name
        """), {"user_id": user_id, "exchange_name": exchange_name})
        if recent_attempt.scalar_one_or_none():
            raise HTTPException(429, "Exchange-import kan over vijf minuten opnieuw")
        keys = await ExchangeRepository(self.session).get_active_keys(user_id)
        key = next((item for item in keys if item.exchange_name.lower() == exchange_name), None)
        if key is None:
            raise HTTPException(404, "Geen gekoppelde exchange")
        source_id = None
        client = None
        try:
            await self.session.execute(text("""
                INSERT INTO finn_exchange_import_attempts(user_id, exchange_name, last_attempt_at)
                VALUES (:user_id, :exchange_name, NOW())
                ON CONFLICT (user_id, exchange_name) DO UPDATE
                SET last_attempt_at=NOW(), last_error_code=NULL
            """), {"user_id": user_id, "exchange_name": exchange_name})
            client = await ExchangeService.get_client(exchange_name, key.api_key, key.api_secret,
                                                      key.api_passphrase)
            credential = EncryptionUtils.decrypt(key.api_key)
            key_hash = _hash_identity(f"key:{exchange_name}:{credential}")
            if exchange_name == "bybit":
                response = await client.privateGetV5UserQueryApi()
                if not isinstance(response, dict) or response.get("retCode") != 0:
                    raise ValueError("Bybit account identity unavailable")
                uid = str((response.get("result") or {}).get("userID") or "")
                if not uid.isascii() or not uid.isdigit() or not 1 <= len(uid) <= 20:
                    raise ValueError("Bybit account identity unavailable")
                identity_kind = "provider_uid"
                identity_hash = _hash_identity(f"uid:bybit:{uid}")
            else:
                # Bitvavo's documented private REST surface has no stable
                # account UID. Do not merge a rotated key with older history.
                identity_kind = "credential_epoch"
                identity_hash = key_hash
            if exchange_name == "bybit":
                await client.load_markets()
            now_ms = int(time.time() * 1000)
            prior_sources = await self.session.execute(text("""
                SELECT COUNT(*) FROM finn_exchange_import_sources
                WHERE user_id=:user_id AND exchange_name=:exchange_name
                  AND identity_hash<>:identity_hash
            """), {"user_id": user_id, "exchange_name": exchange_name,
                   "identity_hash": identity_hash})
            ambiguous_rotation = exchange_name == "bitvavo" and int(prior_sources.scalar_one()) > 0
            history_start_ms = initial_cursor(exchange_name, now_ms).get("since_ms")
            if history_start_ms is None:
                history_start_ms = initial_cursor(exchange_name, now_ms)["window_start_ms"]
            source_result = await self.session.execute(text("""
                INSERT INTO finn_exchange_import_sources
                    (user_id, exchange_name, identity_kind, identity_hash,
                     credential_fingerprint, cursor_json, status, coverage_start_at)
                VALUES (:user_id, :exchange_name, :identity_kind, :identity_hash,
                        :key_hash, CAST(:cursor AS JSONB), :status, :coverage_start)
                ON CONFLICT (user_id, exchange_name, identity_hash) DO UPDATE SET
                    credential_fingerprint=EXCLUDED.credential_fingerprint,
                    updated_at=NOW()
                RETURNING id, cursor_json, status
            """), {"user_id": user_id, "exchange_name": exchange_name,
                   "identity_kind": identity_kind, "identity_hash": identity_hash,
                   "key_hash": key_hash,
                   "cursor": json.dumps(initial_cursor(exchange_name, now_ms)),
                   "status": "identity_unverified" if ambiguous_rotation else "pending",
                   "coverage_start": datetime.fromtimestamp(history_start_ms / 1000, tz=timezone.utc)})
            source_id, cursor, _ = source_result.fetchone()
            cursor = dict(cursor)
            pages = inserted = 0
            completed_ms = None
            for _ in range(MAX_PAGES_PER_SYNC):
                rows, next_cursor, covered_ms = await provider_page(client, exchange_name, cursor, now_ms)
                for row in rows:
                    inserted_fill = await self.session.execute(text("""
                        INSERT INTO finn_exchange_import_fills AS existing
                            (user_id, source_id, exchange_trade_id, exchange_order_id,
                             symbol, base_currency, quote_currency, side, qty, price_quote,
                             cost_quote, fee_amount, fee_currency, traded_at)
                        VALUES (:user_id, :source_id, :exchange_trade_id, :exchange_order_id,
                                :symbol, :base_currency, :quote_currency, :side, :qty, :price_quote,
                                :cost_quote, :fee_amount, :fee_currency, :traded_at)
                        ON CONFLICT (user_id, source_id, symbol, exchange_trade_id) DO UPDATE
                        SET imported_at=existing.imported_at
                        WHERE existing.exchange_order_id=EXCLUDED.exchange_order_id
                          AND existing.base_currency=EXCLUDED.base_currency
                          AND existing.quote_currency=EXCLUDED.quote_currency
                          AND existing.side=EXCLUDED.side
                          AND existing.qty=EXCLUDED.qty
                          AND existing.price_quote=EXCLUDED.price_quote
                          AND existing.cost_quote=EXCLUDED.cost_quote
                          AND existing.fee_amount IS NOT DISTINCT FROM EXCLUDED.fee_amount
                          AND existing.fee_currency IS NOT DISTINCT FROM EXCLUDED.fee_currency
                          AND existing.traded_at=EXCLUDED.traded_at
                        RETURNING id
                    """), {"user_id": user_id, "source_id": source_id, **row})
                    if inserted_fill.scalar_one_or_none() is None:
                        raise ValueError("Provider fill identity conflicts with recorded immutable facts")
                cursor = next_cursor
                pages += 1
                inserted += len(rows)
                if covered_ms is not None:
                    completed_ms = covered_ms
                if covered_ms is not None and covered_ms >= now_ms - 1000:
                    break
            await self.session.execute(text("""
                UPDATE finn_exchange_import_sources
                SET cursor_json=CAST(:cursor AS JSONB), status=:status,
                    coverage_through_at=CASE WHEN :covered_at IS NULL THEN coverage_through_at
                                             ELSE :covered_at END,
                    last_success_at=NOW(), last_error_code=NULL, updated_at=NOW()
                WHERE id=:source_id AND user_id=:user_id
            """), {"source_id": source_id, "user_id": user_id,
                   "cursor": json.dumps(cursor),
                   "status": "identity_unverified" if ambiguous_rotation else
                             "ready" if exchange_name == "bybit" and completed_ms is not None
                             and completed_ms >= now_ms - 1000 else "partial",
                   "covered_at": datetime.fromtimestamp(completed_ms / 1000, tz=timezone.utc) if completed_ms else None})
            await self.session.commit()
            return {"status": "identity_unverified" if ambiguous_rotation else
                              "ready" if exchange_name == "bybit" and completed_ms is not None
                              and completed_ms >= now_ms - 1000 else "partial",
                    "source_id": source_id, "pages": pages, "fills_seen": inserted,
                    "coverage_complete": False}
        except Exception as exc:
            await self.session.rollback()
            await self.session.execute(text("""
                INSERT INTO finn_exchange_import_attempts(user_id, exchange_name, last_attempt_at, last_error_code)
                VALUES (:user_id, :exchange_name, NOW(), :code)
                ON CONFLICT (user_id, exchange_name) DO UPDATE
                SET last_attempt_at=NOW(), last_error_code=EXCLUDED.last_error_code
            """), {"user_id": user_id, "exchange_name": exchange_name,
                   "code": type(exc).__name__[:60]})
            if source_id is not None:
                await self.session.execute(text("""
                    INSERT INTO finn_exchange_import_sources
                        (user_id, exchange_name, identity_kind, identity_hash,
                         credential_fingerprint, cursor_json, status, coverage_start_at,
                         last_error_code)
                    VALUES (:user_id, :exchange_name, :identity_kind, :identity_hash,
                            :key_hash, CAST(:cursor AS JSONB), 'error', :coverage_start,
                            :code)
                    ON CONFLICT (user_id, exchange_name, identity_hash) DO UPDATE SET
                        status='error', last_error_code=EXCLUDED.last_error_code,
                        updated_at=NOW()
                """), {"user_id": user_id, "exchange_name": exchange_name,
                       "identity_kind": identity_kind, "identity_hash": identity_hash,
                       "key_hash": key_hash,
                       "cursor": json.dumps(initial_cursor(exchange_name, now_ms)),
                       "coverage_start": datetime.fromtimestamp(history_start_ms / 1000, tz=timezone.utc),
                       "code": type(exc).__name__[:60]})
            await self.session.commit()
            raise
        finally:
            if client is not None:
                await client.close()
