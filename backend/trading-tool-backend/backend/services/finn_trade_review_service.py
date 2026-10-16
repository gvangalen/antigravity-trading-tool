"""Forward-only FINN reviews of fully closed bot-managed spot positions.

Only confirmed execution-ledger fills after the migration cutover are used.
Legacy open positions and uncertain environment sequences are deliberately
excluded until flat. This read-side projector never changes trading state.
"""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any

from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from backend.services.finn_trade_screenshot import validate_png
from backend.services.finn_trade_chart_service import historical_eur_chart


EPSILON = Decimal("0.00000001")
TERMINAL_ORDER_STATUSES = {"filled", "partial", "cancelled", "rejected", "error", "failed"}


def _decimal(value: Any) -> Decimal:
    try:
        number = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        raise ValueError("Invalid recorded fill value") from None
    if not number.is_finite():
        raise ValueError("Invalid recorded fill value")
    return number


def _near_zero(value: Decimal) -> bool:
    return abs(value) <= EPSILON


def build_closed_positions(
    fills: list[dict], baselines: dict[tuple[int, str], Decimal],
    current_quantities: dict[tuple[int, str], Decimal],
) -> tuple[list[dict], dict[str, int]]:
    """Project long-only round trips; fail closed for inconsistent streams.

    The caller supplies all committed fills after the cutover. A baseline
    position predating that point is excluded until its first flat event.
    """
    grouped: dict[tuple[int, str], list[dict]] = defaultdict(list)
    for fill in fills:
        grouped[(int(fill["bot_id"]), str(fill["symbol"]))].append(fill)
    positions: list[dict] = []
    excluded = {"legacy_or_ambiguous": 0, "inconsistent": 0}
    for key, rows in grouped.items():
        rows.sort(key=lambda item: int(item["ledger_id"]))
        baseline = baselines.get(key, Decimal(0))
        try:
            total = baseline + sum((_decimal(row["qty_delta"]) for row in rows), Decimal(0))
        except ValueError:
            excluded["inconsistent"] += 1
            continue
        if key not in current_quantities or not _near_zero(total - current_quantities[key]):
            excluded["inconsistent"] += 1
            continue
        balance = baseline
        blocked = not _near_zero(baseline)
        active: list[dict] = []
        environment = None
        for row in rows:
            try:
                delta = _decimal(row["qty_delta"])
                cash = _decimal(row["cash_delta_eur"])
            except ValueError:
                blocked = True
                excluded["inconsistent"] += 1
                continue
            previous = balance
            balance += delta
            if _near_zero(balance):
                balance = Decimal(0)
            valid = (
                delta != 0 and ((delta > 0 and cash < 0) or (delta < 0 and cash > 0))
                and row.get("order_id") is not None
                and row.get("source") in {"manual", "bot"}
                and row.get("environment") in {"paper", "live"}
                and (
                    (row.get("environment") == "paper" and int(row.get("valuation_version") or 0) >= 2)
                    or (
                        row.get("environment") == "live"
                        and bool(row.get("exchange_order_id"))
                        and str(row.get("exchange_symbol") or "").upper().replace("-", "/")
                        == f"{key[1].upper()}/EUR"
                    )
                )
                and str(row.get("order_status") or "") in TERMINAL_ORDER_STATUSES
                and (previous >= -EPSILON and balance >= -EPSILON)
            )
            if not valid or (environment and row.get("environment") != environment):
                blocked = True
            if not blocked:
                if not active:
                    if delta < 0 or not _near_zero(previous):
                        blocked = True
                    else:
                        environment = row["environment"]
                if not blocked:
                    active.append(row)
            if _near_zero(balance):
                if active and not blocked and any(_decimal(part["qty_delta"]) < 0 for part in active):
                    buys = [part for part in active if _decimal(part["qty_delta"]) > 0]
                    sells = [part for part in active if _decimal(part["qty_delta"]) < 0]
                    buy_qty = sum((_decimal(part["qty_delta"]) for part in buys), Decimal(0))
                    sell_qty = -sum((_decimal(part["qty_delta"]) for part in sells), Decimal(0))
                    buy_cost = -sum((_decimal(part["cash_delta_eur"]) for part in buys), Decimal(0))
                    sell_proceeds = sum((_decimal(part["cash_delta_eur"]) for part in sells), Decimal(0))
                    if (
                        buy_qty > 0 and sell_qty > 0 and _near_zero(buy_qty - sell_qty)
                        and active[-1]["ts"] >= active[0]["ts"]
                    ):
                        positions.append({
                            "bot_id": key[0], "symbol": key[1],
                            "execution_environment": environment,
                            "execution_sources": sorted({str(part.get("source")) for part in active}),
                            "opening_ledger_id": int(active[0]["ledger_id"]),
                            "closing_ledger_id": int(active[-1]["ledger_id"]),
                            "entry_at": active[0]["ts"], "exit_at": active[-1]["ts"],
                            "entry_qty": buy_qty, "entry_value_eur": buy_cost,
                            "exit_value_eur": sell_proceeds,
                            "entry_price_eur": buy_cost / buy_qty,
                            "exit_price_eur": sell_proceeds / sell_qty,
                            "pnl_eur_before_fees": sell_proceeds - buy_cost,
                            "plan_snapshot": next((part.get("plan_snapshot") for part in active if part.get("plan_snapshot")), None),
                            "fills": [{
                                "ledger_id": int(part["ledger_id"]),
                                "order_id": int(part["order_id"]),
                                "side": "buy" if _decimal(part["qty_delta"]) > 0 else "sell",
                                "qty": str(abs(_decimal(part["qty_delta"]))),
                                "cash_eur": str(abs(_decimal(part["cash_delta_eur"]))),
                                "price_eur": str(_decimal(part["price_eur"])) if part.get("price_eur") is not None else None,
                                "at": part["ts"].isoformat(),
                                "source": part.get("source"),
                                "valuation_version": int(part.get("valuation_version") or 0),
                            } for part in active],
                        })
                    else:
                        excluded["inconsistent"] += 1
                elif active or blocked:
                    excluded["legacy_or_ambiguous"] += 1
                active = []
                environment = None
                blocked = False
        if active or blocked:
            excluded["legacy_or_ambiguous"] += 1
    return positions, excluded


class FinnTradeReviewService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def _project(self, user_id: int) -> dict[str, int]:
        # Authentication and earlier reads may already have started the API
        # session's transaction. PostgreSQL only accepts SET TRANSACTION before
        # its first query, so projection owns a fresh transaction/connection.
        bind = getattr(self.session, "bind", None)
        if bind is not None:
            factory = async_sessionmaker(bind=bind, expire_on_commit=False)
            async with factory() as project_session:
                return await FinnTradeReviewService(project_session)._project_in_session(user_id)
        return await self._project_in_session(user_id)

    async def _project_in_session(self, user_id: int) -> dict[str, int]:
        for attempt in range(3):
            try:
                return await self._project_once(user_id)
            except DBAPIError as exc:
                await self.session.rollback()
                if getattr(exc.orig, "sqlstate", None) != "40001" or attempt == 2:
                    raise
        raise RuntimeError("Unreachable projection retry state")

    async def _project_once(self, user_id: int) -> dict[str, int]:
        # A single snapshot covers portfolio, orders and fills. The dirty row
        # survives failed projections and concurrent commits for a later retry.
        await self.session.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ"))
        await self.session.execute(text("SELECT pg_advisory_xact_lock(:user_id, 741066)"), {"user_id": user_id})
        available = await self.session.execute(text("SELECT to_regclass('public.finn_trade_review_cutover')"))
        if available.scalar_one_or_none() is None:
            raise HTTPException(503, "FINN trade-review migratie ontbreekt")
        cutover = await self.session.execute(text("SELECT ledger_high_watermark FROM finn_trade_review_cutover WHERE singleton=TRUE"))
        row = cutover.fetchone()
        if row is None:
            raise HTTPException(503, "FINN trade-review migratie ontbreekt")
        dirty_result = await self.session.execute(text("""
            SELECT generation FROM finn_trade_review_dirty_users WHERE user_id=:user_id
        """), {"user_id": user_id})
        generation = dirty_result.scalar_one_or_none()
        if generation is None:
            await self.session.commit()
            return {"legacy_or_ambiguous": 0, "inconsistent": 0}
        watermark = int(row[0])
        baseline_result = await self.session.execute(text("""
            SELECT bot_id, symbol, position_qty FROM finn_trade_review_baselines
            WHERE user_id=:user_id
        """), {"user_id": user_id})
        baselines = {(int(r.bot_id), str(r.symbol)): _decimal(r.position_qty) for r in baseline_result.fetchall()}
        current_result = await self.session.execute(text("""
            SELECT bot_id, symbol, position_qty FROM bot_portfolios WHERE user_id=:user_id
        """), {"user_id": user_id})
        current = {(int(r.bot_id), str(r.symbol)): _decimal(r.position_qty) for r in current_result.fetchall()}
        fill_result = await self.session.execute(text("""
            SELECT l.id AS ledger_id, l.bot_id, l.symbol, l.order_id, l.qty_delta,
                   l.cash_delta_eur, l.price_eur, l.valuation_version, l.ts,
                   o.status AS order_status, o.execution_environment AS environment,
                   o.exchange_symbol, o.exchange_order_id,
                   CASE WHEN o.id IS NULL THEN NULL
                        WHEN o.decision_id IS NULL THEN 'manual'
                        WHEN d.executed_by = 'manual' THEN 'manual'
                        WHEN d.executed_by = 'auto' THEN 'bot'
                        ELSE NULL END AS source,
                   c.plan_snapshot
            FROM bot_ledger l
            LEFT JOIN bot_orders o ON o.id=l.order_id AND o.user_id=l.user_id
            LEFT JOIN bot_decisions d ON d.id=o.decision_id AND d.user_id=l.user_id
            LEFT JOIN finn_trade_order_context c ON c.order_id=l.order_id AND c.user_id=l.user_id
            WHERE l.user_id=:user_id AND l.id>:watermark AND l.entry_type='execute'
            ORDER BY l.id
        """), {"user_id": user_id, "watermark": watermark})
        positions, excluded = build_closed_positions([dict(r._mapping) for r in fill_result.fetchall()], baselines, current)
        for position in positions:
            await self.session.execute(text("""
                INSERT INTO finn_trade_reviews (
                    user_id, bot_id, symbol, execution_environment, execution_sources, opening_ledger_id,
                    closing_ledger_id, entry_at, exit_at, entry_qty, entry_value_eur,
                    exit_value_eur, entry_price_eur, exit_price_eur,
                    pnl_eur_before_fees, plan_snapshot, fills, base_currency
                ) VALUES (
                    :user_id, :bot_id, :symbol, :execution_environment, CAST(:execution_sources AS JSONB), :opening_ledger_id,
                    :closing_ledger_id, :entry_at, :exit_at, :entry_qty, :entry_value_eur,
                    :exit_value_eur, :entry_price_eur, :exit_price_eur,
                    :pnl_eur_before_fees, CAST(:plan_snapshot AS JSONB), CAST(:fills AS JSONB), :symbol
                ) ON CONFLICT (user_id, opening_ledger_id) DO NOTHING
            """), {
                **{k: v for k, v in position.items() if k not in {"fills", "plan_snapshot", "execution_sources"}},
                "user_id": user_id,
                "execution_sources": json.dumps(position["execution_sources"]),
                "plan_snapshot": json.dumps(position["plan_snapshot"], default=str) if position["plan_snapshot"] is not None else None,
                "fills": json.dumps(position["fills"]),
            })
        await self.session.execute(text("""
            DELETE FROM finn_trade_review_dirty_users
            WHERE user_id=:user_id AND generation=:generation
        """), {"user_id": user_id, "generation": generation})
        await self.session.commit()
        return excluded

    async def list_reviews(self, user_id: int, limit: int = 50, offset: int = 0) -> dict:
        excluded = await self._project(user_id)
        result = await self.session.execute(text("""
            SELECT id, bot_id, symbol, execution_environment, execution_sources, entry_at, exit_at,
                   entry_qty, entry_price_eur, exit_price_eur, pnl_eur_before_fees,
                   note, plan_snapshot IS NOT NULL AS has_plan, created_at,
                   analysis_status, origin, closure_basis, base_currency, pnl_status,
                   cash_legs_by_currency, exchange_name, attested_at, attestation_source_ids
            FROM finn_trade_reviews WHERE user_id=:user_id
            ORDER BY exit_at DESC, id DESC LIMIT :limit OFFSET :offset
        """), {"user_id": user_id, "limit": limit, "offset": offset})
        items = [dict(r._mapping) for r in result.fetchall()]
        count = await self.session.execute(text("SELECT COUNT(*) FROM finn_trade_reviews WHERE user_id=:user_id"), {"user_id": user_id})
        total = count.scalar_one()
        week = await self.session.execute(text("""
            SELECT COUNT(*) AS trades,
                   COUNT(*) FILTER (WHERE plan_snapshot IS NOT NULL) AS plans,
                   COUNT(*) FILTER (WHERE LENGTH(TRIM(note)) > 0) AS notes,
                   COUNT(*) FILTER (WHERE analysis_status='ready') AS analyzed,
                   COUNT(*) FILTER (WHERE analysis_status='pending') AS pending,
                   COUNT(*) FILTER (WHERE analysis_status IN ('failed','unavailable')) AS unavailable
            FROM finn_trade_reviews
            WHERE user_id=:user_id AND exit_at >= NOW() - INTERVAL '7 days'
        """), {"user_id": user_id})
        pattern_rows = await self.session.execute(text("""
            SELECT id, plan_snapshot IS NOT NULL AS has_plan, analysis_status, analysis_json
            FROM finn_trade_reviews
            WHERE user_id=:user_id AND exit_at >= NOW() - INTERVAL '7 days'
            ORDER BY exit_at DESC LIMIT 500
        """), {"user_id": user_id})
        patterns: dict[str, set[int]] = defaultdict(set)
        for row in pattern_rows.fetchall():
            if not row.has_plan:
                patterns["missing_plan"].add(int(row.id))
            if row.analysis_status == "ready" and isinstance(row.analysis_json, dict):
                for observation in row.analysis_json.get("observations", []):
                    theme = observation.get("theme")
                    if theme in {"plan_followed", "risk", "timing", "exit_process", "evidence_gap"}:
                        patterns[theme].add(int(row.id))
        weekly_counts = dict(week.fetchone()._mapping)
        return {
            "items": items,
            "total": total, "excluded": excluded,
            "weekly": {**weekly_counts,
                       "patterns": [{"theme": theme, "review_ids": sorted(ids), "count": len(ids)}
                                    for theme, ids in sorted(patterns.items(), key=lambda item: -len(item[1]))],
                       "patterns_truncated": weekly_counts["trades"] > 500},
        }

    async def get_review(self, user_id: int, review_id: int) -> dict:
        result = await self.session.execute(text("""
            SELECT id, bot_id, symbol, execution_environment, execution_sources, opening_ledger_id,
                   closing_ledger_id, entry_at, exit_at, entry_qty, entry_value_eur,
                   exit_value_eur, entry_price_eur, exit_price_eur,
                   pnl_eur_before_fees, plan_snapshot, fills, note, created_at, updated_at,
                   origin, closure_basis, base_currency, pnl_status, cash_legs_by_currency,
                   exchange_name, attested_at, attestation_source_ids,
                   (SELECT a.identity_basis FROM finn_exchange_review_attestations a
                    WHERE a.user_id=:user_id AND a.review_id=:id) AS attestation_identity_basis,
                   (SELECT a.same_account_confirmed FROM finn_exchange_review_attestations a
                    WHERE a.user_id=:user_id AND a.review_id=:id) AS same_account_confirmed,
                   (SELECT a.confirmation_version FROM finn_exchange_review_attestations a
                    WHERE a.user_id=:user_id AND a.review_id=:id) AS attestation_version,
                   analysis_status, analysis_json, analysis_version, analysis_model,
                   analysis_reason, analysis_updated_at, input_revision,
                   candles_json, candles_status,
                   candles_reason, candles_updated_at, candles_attempts,
                   EXISTS (SELECT 1 FROM finn_trade_review_screenshots s
                           WHERE s.user_id=:user_id AND s.review_id=:id) AS has_screenshot,
                   (SELECT s.sha256 FROM finn_trade_review_screenshots s
                    WHERE s.user_id=:user_id AND s.review_id=:id) AS screenshot_sha256
            FROM finn_trade_reviews WHERE id=:id AND user_id=:user_id
        """), {"id": review_id, "user_id": user_id})
        row = result.fetchone()
        if row is None:
            raise HTTPException(404, "Trade-review niet gevonden")
        return dict(row._mapping)

    async def get_chart(self, user_id: int, review_id: int) -> dict:
        review = await self.get_review(user_id, review_id)
        if review.get("origin") == "exchange_user_attested":
            return {"status": "unavailable", "chart": None,
                    "reason": "Uitvoeringsgrafiek voor externe beursfills nog niet verifieerbaar"}
        if review["candles_status"] in {"ready", "unavailable"} or (
            review["candles_status"] in {"failed", "loading"} and review["candles_updated_at"]
            and (datetime.now(timezone.utc) - review["candles_updated_at"]).total_seconds()
            < (300 if review["candles_status"] == "failed" else 120)
        ):
            return {"status": review["candles_status"], "chart": review["candles_json"],
                    "reason": review["candles_reason"]}
        claimed = await self.session.execute(text("""
            UPDATE finn_trade_reviews SET candles_status='loading',
                candles_updated_at=NOW(), candles_attempts=candles_attempts+1
            WHERE user_id=:user_id AND id=:review_id AND
              (candles_status='pending' OR
               (candles_status='failed' AND candles_updated_at < NOW() - INTERVAL '5 minutes') OR
               (candles_status='loading' AND candles_updated_at < NOW() - INTERVAL '2 minutes'))
            RETURNING candles_updated_at, candles_attempts
        """), {"user_id": user_id, "review_id": review_id})
        claimed_row = claimed.fetchone()
        if claimed_row is None:
            await self.session.rollback()
            fresh = await self.get_review(user_id, review_id)
            return {"status": fresh["candles_status"], "chart": fresh["candles_json"],
                    "reason": fresh["candles_reason"]}
        await self.session.commit()
        claim_time = claimed_row[0]
        attempts = int(claimed_row[1])
        chart, reason = await historical_eur_chart(review)
        status = "ready" if chart else (
            "failed" if reason.startswith("Tijdelijk:") and attempts < 3 else "unavailable"
        )
        await self.session.execute(text("""
            UPDATE finn_trade_reviews SET candles_status=:status,
                candles_json=CAST(:chart AS JSONB), candles_reason=:reason,
                candles_updated_at=NOW()
            WHERE user_id=:user_id AND id=:review_id AND candles_status='loading'
              AND candles_updated_at=:claim_time
        """), {"status": status, "chart": json.dumps(chart) if chart else None,
               "reason": reason or None, "user_id": user_id, "review_id": review_id,
               "claim_time": claim_time})
        await self.session.commit()
        return {"status": status, "chart": chart, "reason": reason or None}

    async def update_note(self, user_id: int, review_id: int, note: str) -> dict:
        result = await self.session.execute(text("""
            UPDATE finn_trade_reviews SET note=:note, updated_at=NOW(),
                input_revision=input_revision+1,
                analysis_status='pending', analysis_json=NULL, analysis_reason=NULL
            WHERE id=:id AND user_id=:user_id RETURNING id
        """), {"note": note, "id": review_id, "user_id": user_id})
        if result.fetchone() is None:
            await self.session.rollback()
            raise HTTPException(404, "Trade-review niet gevonden")
        await self.session.execute(text("""
            DELETE FROM finn_trade_review_messages WHERE user_id=:user_id AND review_id=:review_id
        """), {"user_id": user_id, "review_id": review_id})
        await self.session.commit()
        return await self.get_review(user_id, review_id)

    async def save_screenshot(self, user_id: int, review_id: int, png_bytes: bytes) -> dict:
        await self.get_review(user_id, review_id)
        normalized, width, height, digest = validate_png(png_bytes)
        await self.session.execute(text("SELECT pg_advisory_xact_lock(:user_id, 741067)"), {"user_id": user_id})
        usage = await self.session.execute(text("""
            SELECT COALESCE(SUM(OCTET_LENGTH(png_bytes)), 0)
            FROM finn_trade_review_screenshots
            WHERE user_id=:user_id AND review_id<>:review_id
        """), {"user_id": user_id, "review_id": review_id})
        if int(usage.scalar_one()) + len(normalized) > 100 * 1024 * 1024:
            raise HTTPException(413, "Screenshotopslaglimiet van 100 MB bereikt")
        await self.session.execute(text("""
            INSERT INTO finn_trade_review_screenshots
                (user_id, review_id, png_bytes, width, height, sha256)
            VALUES (:user_id, :review_id, :png_bytes, :width, :height, :digest)
            ON CONFLICT (user_id, review_id) DO UPDATE SET
                png_bytes=EXCLUDED.png_bytes, width=EXCLUDED.width,
                height=EXCLUDED.height, sha256=EXCLUDED.sha256, created_at=NOW()
        """), {"user_id": user_id, "review_id": review_id, "png_bytes": normalized,
               "width": width, "height": height, "digest": digest})
        await self.session.execute(text("""
            UPDATE finn_trade_reviews SET input_revision=input_revision+1,
                analysis_status='pending', analysis_json=NULL,
                analysis_reason=NULL WHERE user_id=:user_id AND id=:review_id
        """), {"user_id": user_id, "review_id": review_id})
        await self.session.execute(text("""
            DELETE FROM finn_trade_review_messages WHERE user_id=:user_id AND review_id=:review_id
        """), {"user_id": user_id, "review_id": review_id})
        await self.session.commit()
        return {"width": width, "height": height, "sha256": digest}

    async def get_screenshot(self, user_id: int, review_id: int) -> bytes:
        await self.get_review(user_id, review_id)
        result = await self.session.execute(text("""
            SELECT png_bytes FROM finn_trade_review_screenshots
            WHERE user_id=:user_id AND review_id=:review_id
        """), {"user_id": user_id, "review_id": review_id})
        row = result.fetchone()
        if row is None:
            raise HTTPException(404, "Screenshot niet gevonden")
        return bytes(row[0])

    async def delete_screenshot(self, user_id: int, review_id: int) -> None:
        await self.get_review(user_id, review_id)
        await self.session.execute(text("""
            DELETE FROM finn_trade_review_screenshots
            WHERE user_id=:user_id AND review_id=:review_id
        """), {"user_id": user_id, "review_id": review_id})
        await self.session.execute(text("""
            UPDATE finn_trade_reviews SET input_revision=input_revision+1,
                analysis_status='pending', analysis_json=NULL,
                analysis_reason=NULL WHERE user_id=:user_id AND id=:review_id
        """), {"user_id": user_id, "review_id": review_id})
        await self.session.execute(text("""
            DELETE FROM finn_trade_review_messages WHERE user_id=:user_id AND review_id=:review_id
        """), {"user_id": user_id, "review_id": review_id})
        await self.session.commit()
