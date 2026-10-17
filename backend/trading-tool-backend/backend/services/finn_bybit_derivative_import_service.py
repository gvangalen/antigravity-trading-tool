"""Bounded, read-only V5 linear/inverse import with exact order-history joins."""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import text

from backend.infrastructure.repositories.exchange_repository import ExchangeRepository
from backend.services.exchange_service import ExchangeService
from backend.services.finn_bybit_derivative_service import (
    DERIVATIVE_CATEGORIES, derivative_page, initial_cursor, normalize_order,
)
from backend.services.finn_exchange_import_service import _hash_identity
from backend.services.finn_trade_review_rollout import require_trade_review_access
from backend.utils.encryption_utils import EncryptionUtils


MAX_PAGES_PER_SYNC = 4  # Two pages per category, plus at most sixteen order lookups.
MAX_ORDER_LOOKUPS = 16


class FinnBybitDerivativeImportService:
    def __init__(self, session):
        self.session = session

    async def status(self, user_id: int) -> list[dict]:
        require_trade_review_access(user_id)
        result = await self.session.execute(text("""
            SELECT c.source_id, c.category, c.status, c.coverage_start_at,
                   c.coverage_through_at, c.last_error_code,
                   (SELECT COUNT(*) FROM finn_bybit_derivative_executions e
                    WHERE e.user_id=c.user_id AND e.source_id=c.source_id
                      AND e.category=c.category AND e.exec_type='Trade') AS trade_executions,
                   (SELECT COUNT(*) FROM finn_bybit_derivative_executions e
                    WHERE e.user_id=c.user_id AND e.source_id=c.source_id
                      AND e.category=c.category AND e.evidence_status='trade_order_pending') AS unresolved_orders,
                   (SELECT COUNT(*) FROM finn_bybit_derivative_executions e
                    WHERE e.user_id=c.user_id AND e.source_id=c.source_id
                      AND e.category=c.category AND e.evidence_status='material_event_unmodeled') AS material_events
            FROM finn_bybit_derivative_cursors c
            WHERE c.user_id=:user_id ORDER BY c.source_id, c.category
        """), {"user_id": user_id})
        return [{**dict(row._mapping),
                 "auto_review_status": "unavailable_missing_verified_position_baseline",
                 "review_coverage": "user_attestation_only",
                 "history_limit": "two_year_provider_window"}
                for row in result.fetchall()]

    async def executions(self, user_id: int, source_id: int, category: str,
                         *, limit: int = 50, offset: int = 0) -> dict:
        require_trade_review_access(user_id)
        if category not in DERIVATIVE_CATEGORIES or not 1 <= limit <= 100 or not 0 <= offset <= 10_000:
            raise HTTPException(422, "Ongeldige derivatenpagina")
        owner = await self.session.execute(text("""
            SELECT 1 FROM finn_bybit_derivative_cursors
            WHERE user_id=:user_id AND source_id=:source_id AND category=:category
        """), {"user_id": user_id, "source_id": source_id, "category": category})
        if owner.fetchone() is None:
            raise HTTPException(404, "Bybit-derivatenimport niet gevonden")
        result = await self.session.execute(text("""
            SELECT id, category, symbol, exec_type, side, qty, price, execution_value,
                   fee_amount, fee_currency, settle_currency, closed_size, seq,
                   traded_at, position_idx, evidence_status
            FROM finn_bybit_derivative_executions
            WHERE user_id=:user_id AND source_id=:source_id AND category=:category
            ORDER BY traded_at DESC, id DESC LIMIT :limit OFFSET :offset
        """), {"user_id": user_id, "source_id": source_id, "category": category,
               "limit": limit, "offset": offset})
        return {"source_id": source_id, "category": category,
                "items": [dict(row._mapping) for row in result.fetchall()]}

    async def streams(self, user_id: int, source_id: int, category: str,
                      *, limit: int = 50, offset: int = 0) -> dict:
        """Discover contracts separately from the bounded episode scan."""
        require_trade_review_access(user_id)
        if category not in DERIVATIVE_CATEGORIES or not 1 <= limit <= 50 or not 0 <= offset <= 10_000:
            raise HTTPException(422, "Ongeldige derivatenpagina")
        owner = await self.session.execute(text("""
            SELECT 1 FROM finn_bybit_derivative_cursors
            WHERE user_id=:user_id AND source_id=:source_id AND category=:category
        """), {"user_id": user_id, "source_id": source_id, "category": category})
        if owner.fetchone() is None:
            raise HTTPException(404, "Bybit-derivatenimport niet gevonden")
        result = await self.session.execute(text("""
            SELECT symbol, position_idx, COUNT(*) AS executions,
                   MAX(traded_at) AS last_execution_at
            FROM finn_bybit_derivative_executions
            WHERE user_id=:user_id AND source_id=:source_id AND category=:category
              AND evidence_status='trade_order_resolved' AND position_idx IS NOT NULL
            GROUP BY symbol, position_idx
            ORDER BY last_execution_at DESC, symbol, position_idx
            LIMIT :limit OFFSET :offset
        """), {"user_id": user_id, "source_id": source_id, "category": category,
               "limit": limit + 1, "offset": offset})
        rows = [dict(row._mapping) for row in result.fetchall()]
        return {"source_id": source_id, "category": category,
                "items": rows[:limit], "has_more": len(rows) > limit,
                "limit": limit, "offset": offset}

    async def sync(self, user_id: int) -> dict:
        require_trade_review_access(user_id)
        lock = await self.session.execute(text("SELECT pg_try_advisory_xact_lock(:user_id, 741075)"),
                                          {"user_id": user_id})
        if not lock.scalar_one():
            raise HTTPException(409, "Bybit-derivatenimport loopt al")
        recent = await self.session.execute(text("""
            SELECT last_attempt_at > NOW() - INTERVAL '5 minutes'
            FROM finn_bybit_derivative_attempts WHERE user_id=:user_id
        """), {"user_id": user_id})
        if recent.scalar_one_or_none():
            raise HTTPException(429, "Bybit-derivatenimport kan over vijf minuten opnieuw")
        keys = await ExchangeRepository(self.session).get_active_keys(user_id)
        key = next((item for item in keys if item.exchange_name.lower() == "bybit"), None)
        if key is None:
            raise HTTPException(404, "Geen gekoppelde Bybit-account")
        client = None
        source_id = None
        try:
            await self.session.execute(text("""
                INSERT INTO finn_bybit_derivative_attempts(user_id,last_attempt_at,last_error_code)
                VALUES (:user_id,NOW(),NULL)
                ON CONFLICT (user_id) DO UPDATE SET last_attempt_at=NOW(),last_error_code=NULL
            """), {"user_id": user_id})
            client = await ExchangeService.get_client("bybit", key.api_key, key.api_secret,
                                                      key.api_passphrase)
            account = await client.privateGetV5UserQueryApi()
            if not isinstance(account, dict) or account.get("retCode") != 0:
                raise ValueError("Bybit-accountidentiteit ontbreekt")
            uid = str((account.get("result") or {}).get("userID") or "")
            if not uid.isascii() or not uid.isdigit() or not 1 <= len(uid) <= 20:
                raise ValueError("Bybit-accountidentiteit ontbreekt")
            identity_hash = _hash_identity(f"uid:bybit:{uid}")
            credential_hash = _hash_identity(f"key:bybit:{EncryptionUtils.decrypt(key.api_key)}")
            await client.load_markets()
            now_ms = int(time.time() * 1000)
            history_start = initial_cursor(now_ms)["window_start_ms"]
            source = await self.session.execute(text("""
                INSERT INTO finn_exchange_import_sources
                    (user_id,exchange_name,identity_kind,identity_hash,credential_fingerprint,
                     cursor_json,status,coverage_start_at)
                VALUES (:user_id,'bybit','provider_uid',:identity_hash,:credential_hash,
                        CAST(:spot_cursor AS JSONB),'pending',:coverage_start)
                ON CONFLICT (user_id,exchange_name,identity_hash) DO UPDATE
                SET credential_fingerprint=EXCLUDED.credential_fingerprint,updated_at=NOW()
                RETURNING id
            """), {"user_id": user_id, "identity_hash": identity_hash,
                   "credential_hash": credential_hash,
                   "spot_cursor": json.dumps(initial_cursor(now_ms)),
                   "coverage_start": datetime.fromtimestamp(history_start / 1000, tz=timezone.utc)})
            source_id = int(source.scalar_one())
            pages = imported = 0
            for category in ("linear", "inverse"):
                row = await self.session.execute(text("""
                    INSERT INTO finn_bybit_derivative_cursors
                        (user_id,source_id,category,cursor_json,status,coverage_start_at)
                    VALUES (:user_id,:source_id,:category,CAST(:cursor AS JSONB),'pending',:coverage_start)
                    ON CONFLICT (user_id,source_id,category) DO UPDATE
                    SET updated_at=finn_bybit_derivative_cursors.updated_at
                    RETURNING cursor_json
                """), {"user_id": user_id, "source_id": source_id, "category": category,
                       "cursor": json.dumps(initial_cursor(now_ms)),
                       "coverage_start": datetime.fromtimestamp(history_start / 1000, tz=timezone.utc)})
                cursor = dict(row.scalar_one())
                covered_ms = None
                for _ in range(MAX_PAGES_PER_SYNC // 2):
                    fills, cursor, covered = await derivative_page(client, category, cursor, now_ms)
                    for fill in fills:
                        await self._store_execution(user_id, source_id, fill)
                    pages += 1
                    imported += len(fills)
                    if covered is not None:
                        covered_ms = covered
                    if covered is not None and covered >= now_ms - 1000:
                        break
                await self.session.execute(text("""
                    UPDATE finn_bybit_derivative_cursors
                    SET cursor_json=CAST(:cursor AS JSONB),status=:status,
                        coverage_through_at=COALESCE(CAST(:covered AS TIMESTAMPTZ),coverage_through_at),
                        last_success_at=NOW(),last_error_code=NULL,updated_at=NOW()
                    WHERE user_id=:user_id AND source_id=:source_id AND category=:category
                """), {"user_id": user_id, "source_id": source_id, "category": category,
                       "cursor": json.dumps(cursor),
                       "status": "ready" if covered_ms is not None and covered_ms >= now_ms - 1000 else "partial",
                       "covered": datetime.fromtimestamp(covered_ms / 1000, tz=timezone.utc) if covered_ms else None})
            joined = await self._resolve_orders(user_id, source_id, client)
            await self.session.commit()
            return {"source_id": source_id, "pages": pages, "executions_seen": imported,
                    "orders_joined": joined, "coverage_complete": False,
                    "auto_review_status": "unavailable_missing_verified_position_baseline",
                    "review_coverage": "user_attestation_only"}
        except Exception as exc:
            await self.session.rollback()
            await self.session.execute(text("""
                INSERT INTO finn_bybit_derivative_attempts(user_id,last_attempt_at,last_error_code)
                VALUES (:user_id,NOW(),:code)
                ON CONFLICT (user_id) DO UPDATE
                SET last_attempt_at=NOW(),last_error_code=EXCLUDED.last_error_code
            """), {"user_id": user_id, "code": type(exc).__name__[:60]})
            await self.session.commit()
            raise
        finally:
            if client is not None:
                await client.close()

    async def _store_execution(self, user_id: int, source_id: int, fill: dict) -> None:
        result = await self.session.execute(text("""
            INSERT INTO finn_bybit_derivative_executions AS existing
                (user_id,source_id,category,exec_id,order_id,symbol,base_currency,
                 quote_currency,settle_currency,contract_size,exec_type,side,qty,
                 price,execution_value,fee_amount,fee_currency,closed_size,seq,
                 traded_at,evidence_status)
            VALUES (:user_id,:source_id,:category,:exec_id,:order_id,:symbol,:base_currency,
                    :quote_currency,:settle_currency,:contract_size,:exec_type,:side,:qty,
                    :price,:execution_value,:fee_amount,:fee_currency,:closed_size,:seq,
                    :traded_at,:evidence_status)
            ON CONFLICT (user_id,source_id,category,exec_id) DO UPDATE
            SET imported_at=existing.imported_at
            WHERE existing.order_id IS NOT DISTINCT FROM EXCLUDED.order_id
              AND existing.symbol=EXCLUDED.symbol
              AND existing.settle_currency=EXCLUDED.settle_currency
              AND existing.contract_size IS NOT DISTINCT FROM EXCLUDED.contract_size
              AND existing.exec_type=EXCLUDED.exec_type
              AND existing.side IS NOT DISTINCT FROM EXCLUDED.side
              AND existing.qty IS NOT DISTINCT FROM EXCLUDED.qty
              AND existing.price IS NOT DISTINCT FROM EXCLUDED.price
              AND existing.execution_value IS NOT DISTINCT FROM EXCLUDED.execution_value
              AND existing.fee_amount IS NOT DISTINCT FROM EXCLUDED.fee_amount
              AND existing.fee_currency IS NOT DISTINCT FROM EXCLUDED.fee_currency
              AND existing.closed_size IS NOT DISTINCT FROM EXCLUDED.closed_size
              AND existing.seq IS NOT DISTINCT FROM EXCLUDED.seq
              AND existing.traded_at=EXCLUDED.traded_at
            RETURNING id
        """), {"user_id": user_id, "source_id": source_id,
               **{key: fill.get(key) for key in (
                   "category", "exec_id", "order_id", "symbol", "base_currency", "quote_currency",
                   "settle_currency", "contract_size", "exec_type", "side", "qty", "price",
                   "execution_value", "fee_amount", "fee_currency", "closed_size", "seq",
                   "traded_at", "evidence_status")}})
        if result.scalar_one_or_none() is None:
            raise ValueError("Bybit-uitvoeringsidentiteit botst met opgeslagen feiten")

    async def _resolve_orders(self, user_id: int, source_id: int, client) -> int:
        pending = await self.session.execute(text("""
            SELECT category,order_id,symbol,MIN(order_lookup_at) AS oldest_lookup
            FROM finn_bybit_derivative_executions
            WHERE user_id=:user_id AND source_id=:source_id
              AND evidence_status='trade_order_pending'
            GROUP BY category,order_id,symbol
            ORDER BY oldest_lookup NULLS FIRST,category,order_id,symbol LIMIT :limit
        """), {"user_id": user_id, "source_id": source_id, "limit": MAX_ORDER_LOOKUPS})
        joined = 0
        for row in pending.fetchall():
            response = await client.privateGetV5OrderHistory({
                "category": row.category, "orderId": row.order_id, "limit": 1})
            if not isinstance(response, dict) or response.get("retCode") != 0:
                raise ValueError("Bybit-orderhistorie niet beschikbaar")
            data = response.get("result") or {}
            if data.get("category") != row.category or not isinstance(data.get("list"), list):
                raise ValueError("Ongeldige Bybit-orderhistorie")
            await self.session.execute(text("""
                UPDATE finn_bybit_derivative_executions SET order_lookup_at=NOW()
                WHERE user_id=:user_id AND source_id=:source_id AND category=:category
                  AND order_id=:order_id AND symbol=:symbol
                  AND evidence_status='trade_order_pending'
            """), {"user_id": user_id, "source_id": source_id, "category": row.category,
                   "order_id": row.order_id, "symbol": row.symbol})
            matches = [item for item in data["list"] if item.get("orderId") == row.order_id]
            if len(matches) != 1:
                continue  # visible pending mapping; no guessed positionIdx
            try:
                order = normalize_order(matches[0], category=row.category,
                                        order_id=row.order_id, symbol=row.symbol)
            except ValueError:
                continue  # invalid mapping remains pending; later orders still progress
            inserted = await self.session.execute(text("""
                INSERT INTO finn_bybit_derivative_orders AS existing
                    (user_id,source_id,category,order_id,symbol,position_idx,side,reduce_only)
                VALUES (:user_id,:source_id,:category,:order_id,:symbol,
                        :position_idx,:side,:reduce_only)
                ON CONFLICT (user_id,source_id,category,order_id) DO UPDATE
                SET first_seen_at=existing.first_seen_at
                WHERE existing.symbol=EXCLUDED.symbol
                  AND existing.position_idx=EXCLUDED.position_idx
                  AND existing.side=EXCLUDED.side
                  AND existing.reduce_only=EXCLUDED.reduce_only
                RETURNING order_id
            """), {"user_id": user_id, "source_id": source_id, "category": row.category,
                   "order_id": row.order_id, "symbol": row.symbol, **{key: order[key]
                       for key in ("position_idx", "side", "reduce_only")}})
            if inserted.scalar_one_or_none() is None:
                raise ValueError("Bybit-orderidentiteit botst met opgeslagen feiten")
            await self.session.execute(text("""
                UPDATE finn_bybit_derivative_executions
                SET position_idx=:position_idx,evidence_status='trade_order_resolved'
                WHERE user_id=:user_id AND source_id=:source_id AND category=:category
                  AND order_id=:order_id AND symbol=:symbol
                  AND side=:side AND evidence_status='trade_order_pending'
            """), {"user_id": user_id, "source_id": source_id, "category": row.category,
                   "order_id": row.order_id, "symbol": row.symbol,
                   "side": order["side"], "position_idx": order["position_idx"]})
            joined += 1
        return joined
