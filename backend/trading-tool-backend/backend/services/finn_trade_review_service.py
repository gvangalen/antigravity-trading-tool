"""Forward-only FINN reviews of fully closed bot-managed spot positions.

Only confirmed execution-ledger fills after the migration cutover are used.
Legacy open positions and uncertain environment sequences are deliberately
excluded until flat. This read-side projector never changes trading state.
"""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Any
from zoneinfo import ZoneInfo

from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from backend.services.finn_trade_screenshot import validate_png
from backend.services.finn_trade_chart_service import historical_eur_chart


EPSILON = Decimal("0.00000001")
REFLECTION_ZONE = ZoneInfo("Europe/Amsterdam")
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


def _utc_instant(value: datetime) -> datetime:
    """Compare legacy UTC timestamps and timezone-aware capture timestamps."""
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def unrecorded_plan_theme(origin: str | None) -> str:
    return ("plan_not_recorded" if origin in {"exchange_user_attested", "bybit_derivative_user_attested"}
            else "missing_plan")


def completed_reflection_week(now: datetime | None = None, selected: date | None = None) -> tuple[date, date, datetime, datetime]:
    """Return one closed Monday–Sunday week, with DST-safe UTC query bounds."""
    local_today = (now or datetime.now(timezone.utc)).astimezone(REFLECTION_ZONE).date()
    current_monday = local_today - timedelta(days=local_today.weekday())
    monday = selected or current_monday - timedelta(days=7)
    if monday.weekday() != 0 or monday >= current_monday:
        raise ValueError("Week must be a completed Monday–Sunday period")
    next_monday = monday + timedelta(days=7)
    start = datetime.combine(monday, datetime.min.time(), REFLECTION_ZONE).astimezone(timezone.utc)
    end = datetime.combine(next_monday, datetime.min.time(), REFLECTION_ZONE).astimezone(timezone.utc)
    return monday, next_monday, start, end


def build_weekly_review_patterns(rows: list[Any]) -> list[dict]:
    """Summarize owner-scoped review evidence without inferring repeated behavior."""
    patterns: dict[str, set[int]] = defaultdict(set)
    pattern_examples: dict[str, str] = {}
    for row in rows:
        if not row.has_plan:
            patterns[unrecorded_plan_theme(row.origin)].add(int(row.id))
        if row.analysis_status == "ready" and isinstance(row.analysis_json, dict):
            observations = row.analysis_json.get("observations")
            for observation in (observations if isinstance(observations, list) else []):
                if not isinstance(observation, dict):
                    continue
                theme = observation.get("theme")
                if theme in {"plan_followed", "risk", "timing", "exit_process", "evidence_gap"}:
                    patterns[theme].add(int(row.id))
                    example = observation.get("text")
                    if theme not in pattern_examples and isinstance(example, str) and example.strip():
                        pattern_examples[theme] = example.strip()[:280]
    return [{"theme": theme, "review_ids": sorted(ids), "count": len(ids),
             "basis": "plan_record" if theme in {"missing_plan", "plan_not_recorded"} else "finn_analysis",
             "example": pattern_examples.get(theme)}
            for theme, ids in sorted(patterns.items(), key=lambda item: -len(item[1]))]


def dependent_review_ids(source_review_id: int, rows: list[Any]) -> list[int]:
    """Find every cached analysis depending directly or indirectly on a lesson."""
    reverse_edges: dict[int, set[int]] = defaultdict(set)
    for row in rows:
        candidates = row.candidate_ids if hasattr(row, "candidate_ids") else row[1]
        if not isinstance(candidates, list):
            continue
        target = int(row.id if hasattr(row, "id") else row[0])
        for candidate in candidates:
            if type(candidate) is int:
                reverse_edges[candidate].add(target)
    seen = {source_review_id}
    queue = [source_review_id]
    for source in queue:
        for target in reverse_edges.get(source, ()):
            if target not in seen:
                seen.add(target)
                queue.append(target)
    return sorted(seen - {source_review_id})


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
                        entry_plan = active[0].get("plan_snapshot")
                        entry_plan_captured_at = active[0].get("plan_captured_at")
                        if not entry_plan_captured_at or _utc_instant(entry_plan_captured_at) > _utc_instant(active[0]["ts"]):
                            entry_plan = None
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
                            "plan_snapshot": entry_plan,
                            "plan_provenance": ({
                                "source": "bot_order_context",
                                "order_id": int(active[0]["plan_order_id"]),
                                "decision_id": active[0].get("plan_decision_id"),
                                "captured_at": entry_plan_captured_at.isoformat(),
                                "relation": "entry_order_before_execution",
                            } if entry_plan is not None else None),
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
    @staticmethod
    def _presented_review(row: dict) -> dict:
        if str(row.get("execution_environment")).lower() == "paper":
            presented = {**row, "pnl_status": "paper_cash_flow_including_simulated_costs"}
            analysis = row.get("analysis_json")
            if isinstance(analysis, dict):
                # Historical deterministic summaries used the old field name
                # as a user-facing fee claim. Correct that presentation without
                # rewriting immutable stored evidence or user-authored notes.
                summary = analysis.get("summary")
                if isinstance(summary, str):
                    analysis = {**analysis, "summary": summary.replace(
                        "Het geregistreerde resultaat vóór kosten",
                        "Het geregistreerde Paper-resultaat op basis van virtuele kassastromen",
                    )}
                presented["analysis_json"] = analysis
            return presented
        return row

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
                   c.plan_snapshot, c.captured_at AS plan_captured_at,
                   c.order_id AS plan_order_id, c.decision_id AS plan_decision_id
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
                    pnl_eur_before_fees, plan_snapshot, plan_provenance, fills, base_currency
                ) VALUES (
                    :user_id, :bot_id, :symbol, :execution_environment, CAST(:execution_sources AS JSONB), :opening_ledger_id,
                    :closing_ledger_id, :entry_at, :exit_at, :entry_qty, :entry_value_eur,
                    :exit_value_eur, :entry_price_eur, :exit_price_eur,
                    :pnl_eur_before_fees, CAST(:plan_snapshot AS JSONB),
                    CAST(:plan_provenance AS JSONB), CAST(:fills AS JSONB), :symbol
                ) ON CONFLICT (user_id, opening_ledger_id) DO NOTHING
            """), {
                **{k: v for k, v in position.items() if k not in {"fills", "plan_snapshot", "plan_provenance", "execution_sources"}},
                "user_id": user_id,
                "execution_sources": json.dumps(position["execution_sources"]),
                "plan_snapshot": json.dumps(position["plan_snapshot"], default=str) if position["plan_snapshot"] is not None else None,
                "plan_provenance": json.dumps(position["plan_provenance"]) if position["plan_provenance"] is not None else None,
                "fills": json.dumps(position["fills"]),
            })
        await self.session.execute(text("""
            DELETE FROM finn_trade_review_dirty_users
            WHERE user_id=:user_id AND generation=:generation
        """), {"user_id": user_id, "generation": generation})
        await self.session.execute(text("""
            INSERT INTO finn_trade_review_projection_status
                (user_id, legacy_or_ambiguous, inconsistent, updated_at)
            VALUES (:user_id, :legacy_or_ambiguous, :inconsistent, NOW())
            ON CONFLICT (user_id) DO UPDATE SET
                legacy_or_ambiguous=EXCLUDED.legacy_or_ambiguous,
                inconsistent=EXCLUDED.inconsistent,
                updated_at=NOW()
        """), {"user_id": user_id, **excluded})
        await self.session.commit()
        return excluded

    async def list_reviews(self, user_id: int, limit: int = 50, offset: int = 0,
                           week_start: date | None = None) -> dict:
        projection = await self.session.execute(text("""
            SELECT s.legacy_or_ambiguous, s.inconsistent,
                   EXISTS (SELECT 1 FROM finn_trade_review_dirty_users d
                           WHERE d.user_id=:user_id) AS projection_pending
            FROM (SELECT CAST(:user_id AS INTEGER) AS user_id) target
            LEFT JOIN finn_trade_review_projection_status s ON s.user_id=target.user_id
        """), {"user_id": user_id})
        projection_row = projection.fetchone()
        excluded = {
            "legacy_or_ambiguous": int(projection_row.legacy_or_ambiguous or 0),
            "inconsistent": int(projection_row.inconsistent or 0),
        }
        projection_pending = bool(projection_row.projection_pending)
        # Individual dossiers remain available as soon as a trade closes.
        # The selected completed week applies only to the saved weekly report.
        params = {"user_id": user_id, "limit": limit, "offset": offset}
        result = await self.session.execute(text("""
            SELECT id, bot_id, symbol, execution_environment, execution_sources, entry_at, exit_at,
                   entry_qty, entry_price_eur, exit_price_eur, pnl_eur_before_fees,
                   note, (plan_snapshot IS NOT NULL AND plan_provenance IS NOT NULL) AS has_plan, created_at,
                   analysis_status, origin, closure_basis, base_currency, pnl_status,
                   cash_legs_by_currency, exchange_name, attested_at, attestation_source_ids,
                   derivative_category, position_idx, direction, settle_currency,
                   native_pnl, native_pnl_status, fee_legs_by_currency
            FROM finn_trade_reviews
            WHERE user_id=:user_id
            ORDER BY exit_at DESC, id DESC LIMIT :limit OFFSET :offset
        """), params)
        items = [self._presented_review(dict(r._mapping)) for r in result.fetchall()]
        count = await self.session.execute(text("""
            SELECT COUNT(*) FROM finn_trade_reviews
            WHERE user_id=:user_id
        """), params)
        total = count.scalar_one()
        weekly = await self.weekly_report(user_id, week_start)
        week_options = await self.session.execute(text("""
            SELECT DISTINCT date_trunc('week', exit_at AT TIME ZONE 'Europe/Amsterdam')::date AS week_start
            FROM finn_trade_reviews
            WHERE user_id=:user_id AND exit_at < :closed_before
            ORDER BY week_start DESC LIMIT 52
        """), {"user_id": user_id, "closed_before": completed_reflection_week()[3]})
        weeks = sorted({weekly["week_start"], *(row.week_start.isoformat() for row in week_options.fetchall())}, reverse=True)
        return {"items": items, "total": total, "excluded": excluded,
                "projection_pending": projection_pending,
                "weekly": weekly, "weeks": weeks}

    async def weekly_report(self, user_id: int, selected: date | None = None) -> dict:
        monday, next_monday, start, end = completed_reflection_week(selected=selected)
        params = {"user_id": user_id, "start": start, "end": end}
        week = await self.session.execute(text("""
            SELECT COUNT(*) AS trades,
                   COUNT(*) FILTER (WHERE plan_snapshot IS NOT NULL AND plan_provenance IS NOT NULL) AS plans,
                   COUNT(*) FILTER (WHERE LENGTH(TRIM(note)) > 0) AS notes,
                   COUNT(*) FILTER (WHERE analysis_status='ready') AS analyzed,
                   COUNT(*) FILTER (WHERE analysis_status='pending') AS pending,
                   COUNT(*) FILTER (WHERE analysis_status IN ('failed','unavailable')) AS unavailable
            FROM finn_trade_reviews
            WHERE user_id=:user_id AND exit_at >= :start AND exit_at < :end
        """), params)
        pattern_rows = await self.session.execute(text("""
            SELECT id, origin,
                   (plan_snapshot IS NOT NULL AND plan_provenance IS NOT NULL) AS has_plan,
                   analysis_status, analysis_json
            FROM finn_trade_reviews
            WHERE user_id=:user_id AND exit_at >= :start AND exit_at < :end
            ORDER BY exit_at DESC LIMIT 500
        """), params)
        patterns = build_weekly_review_patterns(pattern_rows.fetchall())
        lesson_rows = await self.session.execute(text("""
            SELECT r.id, l.lesson_text
            FROM finn_trade_review_lessons l
            JOIN finn_trade_reviews r ON r.id=l.review_id AND r.user_id=l.user_id
            WHERE l.user_id=:user_id AND l.status='active'
              AND l.evidence_revision=r.input_revision
              AND r.exit_at >= :start AND r.exit_at < :end
            ORDER BY r.exit_at DESC,r.id DESC LIMIT 500
        """), params)
        # Exact user-confirmed wording is the only safe equivalence here. A
        # model theme alone cannot prove a repeated personal behavior.
        lesson_groups: dict[str, dict] = {}
        for row in lesson_rows.fetchall():
            key = " ".join(row.lesson_text.casefold().split())
            group = lesson_groups.setdefault(key, {"lesson_text": row.lesson_text, "review_ids": []})
            group["review_ids"].append(int(row.id))
        repeated_lessons = [
            {**group, "review_ids": sorted(group["review_ids"]),
             "count": len(group["review_ids"]), "basis": "user_confirmed_exact_wording",
             "uncertainty": "Herhaalde lesformulering; dit bewijst niet dat het gedrag opnieuw voorkwam."}
            for group in lesson_groups.values() if len(group["review_ids"]) >= 2
        ]
        weekly_counts = dict(week.fetchone()._mapping)
        summary = {**weekly_counts, "patterns": patterns,
                   "confirmed_lesson_repetitions": repeated_lessons,
                   "patterns_truncated": weekly_counts["trades"] > 500}
        await self.session.execute(text("""
            INSERT INTO finn_weekly_trade_reflections
              (user_id, week_start, week_end, summary)
            VALUES (:user_id, :week_start, :week_end, CAST(:summary AS JSONB))
            ON CONFLICT (user_id, week_start) DO UPDATE
              SET summary=EXCLUDED.summary, generated_at=NOW()
            WHERE finn_weekly_trade_reflections.summary IS DISTINCT FROM EXCLUDED.summary
        """), {"user_id": user_id, "week_start": monday, "week_end": next_monday,
                "summary": json.dumps(summary, default=str)})
        await self.session.commit()
        stored = await self.session.execute(text("""
            SELECT generated_at FROM finn_weekly_trade_reflections
            WHERE user_id=:user_id AND week_start=:week_start
        """), {"user_id": user_id, "week_start": monday})
        return {**summary, "week_start": monday.isoformat(), "week_end": next_monday.isoformat(),
                "generated_at": stored.scalar_one().isoformat(), "status": "complete"}

    async def get_review(self, user_id: int, review_id: int) -> dict:
        result = await self.session.execute(text("""
            SELECT id, bot_id, symbol, execution_environment, execution_sources, opening_ledger_id,
                   closing_ledger_id, entry_at, exit_at, entry_qty, entry_value_eur,
                   exit_value_eur, entry_price_eur, exit_price_eur,
                   pnl_eur_before_fees, plan_snapshot, plan_provenance,
                   CASE WHEN plan_snapshot IS NULL THEN 'no_original_plan_recorded'
                        WHEN plan_provenance IS NULL THEN 'legacy_plan_provenance_unknown'
                        ELSE 'entry_order_plan_recorded' END AS plan_status,
                   fills, note, created_at, updated_at,
                   origin, closure_basis, base_currency, pnl_status, cash_legs_by_currency,
                   exchange_name, attested_at, attestation_source_ids,
                   derivative_category, position_idx, direction, settle_currency,
                   native_pnl, native_pnl_status, fee_legs_by_currency,
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
                    WHERE s.user_id=:user_id AND s.review_id=:id) AS screenshot_sha256,
                   (SELECT jsonb_build_object(
                        'lesson_text', l.lesson_text, 'status', l.status,
                        'confirmed_at', l.confirmed_at,
                        'evidence_revision', l.evidence_revision,
                        'source_message_id', l.source_message_id)
                    FROM finn_trade_review_lessons l
                    WHERE l.user_id=:user_id AND l.review_id=:id) AS lesson
            FROM finn_trade_reviews WHERE id=:id AND user_id=:user_id
        """), {"id": review_id, "user_id": user_id})
        row = result.fetchone()
        if row is None:
            raise HTTPException(404, "Trade-review niet gevonden")
        return self._presented_review(dict(row._mapping))

    async def get_chart(self, user_id: int, review_id: int) -> dict:
        review = await self.get_review(user_id, review_id)
        if review.get("origin") in {"exchange_user_attested", "bybit_derivative_user_attested"}:
            return {"status": "unavailable", "chart": None,
                    "reason": "Marktprijsgrafiek voor externe beursuitvoeringen nog niet verifieerbaar"}
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
        await self.session.execute(text("SELECT pg_advisory_xact_lock(:user_id,741068)"),
                                   {"user_id": user_id})
        previous = await self.session.execute(text("""
            SELECT note FROM finn_trade_reviews
            WHERE id=:id AND user_id=:user_id FOR UPDATE
        """), {"id": review_id, "user_id": user_id})
        row = previous.fetchone()
        if row is None:
            await self.session.rollback()
            raise HTTPException(404, "Trade-review niet gevonden")
        if row.note == note:
            await self.session.commit()
            return await self.get_review(user_id, review_id)
        result = await self.session.execute(text("""
            UPDATE finn_trade_reviews SET note=:note, updated_at=NOW(),
                input_revision=input_revision+1,
                analysis_status='pending', analysis_json=NULL, analysis_reason=NULL
            WHERE id=:id AND user_id=:user_id RETURNING id
        """), {"note": note, "id": review_id, "user_id": user_id})
        if result.fetchone() is None:
            await self.session.rollback()
            raise HTTPException(404, "Trade-review niet gevonden")
        await self._invalidate_lesson_dependents(user_id, review_id)
        await self.session.commit()
        return await self.get_review(user_id, review_id)

    async def set_lesson(self, user_id: int, review_id: int, lesson_text: str) -> dict:
        """Only an authenticated user can confirm or withdraw one lesson."""
        if not isinstance(lesson_text, str) or len(lesson_text) > 500:
            raise HTTPException(422, "Les mag maximaal 500 tekens bevatten")
        clean = lesson_text.strip()
        if clean and len(clean) < 10:
            raise HTTPException(422, "Beschrijf de les in minstens 10 tekens")
        await self.session.execute(text("SELECT pg_advisory_xact_lock(:user_id,741068)"),
                                   {"user_id": user_id})
        current = await self.session.execute(text("""
            SELECT input_revision FROM finn_trade_reviews
            WHERE user_id=:user_id AND id=:review_id FOR UPDATE
        """), {"user_id": user_id, "review_id": review_id})
        revision = current.scalar_one_or_none()
        if revision is None:
            await self.session.rollback()
            raise HTTPException(404, "Trade-review niet gevonden")
        prior = await self.session.execute(text("""
            SELECT lesson_text,status,evidence_revision FROM finn_trade_review_lessons
            WHERE user_id=:user_id AND review_id=:review_id
        """), {"user_id": user_id, "review_id": review_id})
        old = prior.fetchone()
        desired_status = "active" if clean else "withdrawn"
        if (old is not None and old.lesson_text == clean and old.status == desired_status
                and (desired_status == "withdrawn" or old.evidence_revision == revision)):
            await self.session.commit()
            return await self.get_review(user_id, review_id)
        if old is None and not clean:
            await self.session.commit()
            return await self.get_review(user_id, review_id)
        await self.session.execute(text("""
            INSERT INTO finn_trade_review_lessons
                (user_id,review_id,lesson_text,status,confirmed_at,evidence_revision,source_message_id)
            VALUES (:user_id,:review_id,:lesson_text,:status,
                    CASE WHEN :status='active' THEN NOW() ELSE NULL END,:revision,NULL)
            ON CONFLICT (user_id,review_id) DO UPDATE SET
                lesson_text=EXCLUDED.lesson_text,status=EXCLUDED.status,
                confirmed_at=EXCLUDED.confirmed_at,
                evidence_revision=EXCLUDED.evidence_revision,
                source_message_id=NULL,updated_at=NOW()
        """), {"user_id": user_id, "review_id": review_id, "lesson_text": clean,
               "status": desired_status, "revision": revision})
        await self._invalidate_lesson_dependents(user_id, review_id)
        await self.session.commit()
        return await self.get_review(user_id, review_id)

    async def _invalidate_lesson_dependents(self, user_id: int, review_id: int) -> None:
        # Caller holds the per-user lesson/analysis advisory lock. Preserve the
        # conversation, but force new analysis when source evidence changes.
        # A's change also makes B's confirmed lesson stale after B's revision
        # increments, so traverse B -> C before clearing cached analyses.
        edges = await self.session.execute(text("""
            SELECT id,analysis_json->'prior_lesson_candidate_ids' AS candidate_ids
            FROM finn_trade_reviews
            WHERE user_id=:user_id AND analysis_json IS NOT NULL
        """), {"user_id": user_id})
        dependents = dependent_review_ids(review_id, edges.fetchall())
        if not dependents:
            return
        await self.session.execute(text("""
            UPDATE finn_trade_reviews SET input_revision=input_revision+1,
                analysis_status='pending',analysis_json=NULL,analysis_reason=NULL,
                updated_at=NOW()
            WHERE user_id=:user_id AND id=ANY(CAST(:review_ids AS BIGINT[]))
        """), {"user_id": user_id, "review_ids": dependents})

    async def save_screenshot(self, user_id: int, review_id: int, png_bytes: bytes) -> dict:
        await self.get_review(user_id, review_id)
        normalized, width, height, digest = validate_png(png_bytes)
        await self.session.execute(text("SELECT pg_advisory_xact_lock(:user_id,741068)"),
                                   {"user_id": user_id})
        await self.session.execute(text("SELECT pg_advisory_xact_lock(:user_id, 741067)"), {"user_id": user_id})
        prior = await self.session.execute(text("""
            SELECT sha256 FROM finn_trade_review_screenshots
            WHERE user_id=:user_id AND review_id=:review_id
        """), {"user_id": user_id, "review_id": review_id})
        row = prior.fetchone()
        if row is not None and row.sha256 == digest:
            await self.session.commit()
            return {"width": width, "height": height, "sha256": digest}
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
        await self._invalidate_lesson_dependents(user_id, review_id)
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
        await self.session.execute(text("SELECT pg_advisory_xact_lock(:user_id,741068)"),
                                   {"user_id": user_id})
        removed = await self.session.execute(text("""
            DELETE FROM finn_trade_review_screenshots
            WHERE user_id=:user_id AND review_id=:review_id
        """), {"user_id": user_id, "review_id": review_id})
        if removed.rowcount == 0:
            await self.session.commit()
            return
        await self.session.execute(text("""
            UPDATE finn_trade_reviews SET input_revision=input_revision+1,
                analysis_status='pending', analysis_json=NULL,
                analysis_reason=NULL WHERE user_id=:user_id AND id=:review_id
        """), {"user_id": user_id, "review_id": review_id})
        await self._invalidate_lesson_dependents(user_id, review_id)
        await self.session.commit()
