"""Owner-scoped, read-only evidence contract for FINN's closed-trade coaching."""

from collections import defaultdict
import re
from typing import Any

from fastapi import HTTPException
from sqlalchemy import text
from backend.services.finn_trade_review_rollout import trade_review_enabled, require_trade_review_access


THEMES = {"plan_followed", "risk", "timing", "exit_process", "evidence_gap"}
REVIEW_PATH = "/report?trade_review_id={review_id}"


class FinnClosedTradeReflectionService:
    def __init__(self, session):
        self.session = session

    async def _available(self) -> bool:
        result = await self.session.execute(text("SELECT to_regclass('public.finn_trade_reviews')"))
        return result.scalar_one_or_none() is not None

    async def recent(self, user_id: int, *, days: int = 7, limit: int = 10,
                     symbol: str | None = None) -> dict[str, Any]:
        if not 1 <= days <= 30 or not 1 <= limit <= 20:
            raise ValueError("Invalid trade-reflection window")
        if not trade_review_enabled(user_id):
            return self._empty("disabled", days)
        if not await self._available():
            return self._empty("migration_unavailable", days)
        symbol = symbol.upper() if symbol else None
        totals = await self.session.execute(text("""
            SELECT COUNT(*) AS trades,
                   COUNT(*) FILTER (WHERE analysis_status='ready') AS analyzed,
                   COUNT(*) FILTER (WHERE analysis_status='pending' OR analysis_status='running') AS pending,
                   COUNT(*) FILTER (WHERE analysis_status IN ('failed','unavailable')) AS unavailable
            FROM finn_trade_reviews
            WHERE user_id=:user_id AND exit_at >= NOW() - (:days * INTERVAL '1 day')
              AND (CAST(:symbol AS TEXT) IS NULL OR symbol=:symbol)
        """), {"user_id": user_id, "days": days, "symbol": symbol})
        coverage = dict(totals.fetchone()._mapping)
        rows = await self.session.execute(text("""
            SELECT id, bot_id,
                   (SELECT b.name FROM bot_configs b WHERE b.id=r.bot_id AND b.user_id=r.user_id) AS bot_name,
                   symbol, execution_environment, execution_sources, entry_at, exit_at,
                   origin, closure_basis, pnl_status, cash_legs_by_currency,
                   derivative_category, position_idx, direction, settle_currency,
                   native_pnl_status,
                   pnl_eur_before_fees, plan_snapshot, plan_provenance,
                   analysis_status, analysis_json, candles_status,
                   (SELECT jsonb_build_object(
                        'lesson_text',l.lesson_text,'confirmed_at',l.confirmed_at,
                        'evidence_revision',l.evidence_revision)
                    FROM finn_trade_review_lessons l
                    WHERE l.user_id=:user_id AND l.review_id=r.id
                      AND l.status='active' AND l.evidence_revision=r.input_revision
                   ) AS confirmed_lesson,
                   EXISTS (SELECT 1 FROM finn_trade_review_screenshots s
                           WHERE s.user_id=:user_id AND s.review_id=r.id) AS has_screenshot,
                   fills
            FROM finn_trade_reviews r
            WHERE user_id=:user_id AND exit_at >= NOW() - (:days * INTERVAL '1 day')
              AND (CAST(:symbol AS TEXT) IS NULL OR r.symbol=:symbol)
            ORDER BY exit_at DESC, id DESC LIMIT :limit
        """), {"user_id": user_id, "days": days, "limit": limit, "symbol": symbol})
        reviews = []
        themes: dict[str, set[int]] = defaultdict(set)
        for row in rows.fetchall():
            item = self._safe_row(dict(row._mapping))
            reviews.append(item)
            for theme in item["themes"]:
                themes[theme].add(item["review_id"])
        return {
            "contract": "closed_trade_reflection.v1", "action_class": "prepare_only",
            "allowed_side_effects": [], "status": "ready" if coverage["trades"] else "no_data",
            "time_window_days": days, "coverage": coverage,
            "reviews": reviews, "review_ids": [r["review_id"] for r in reviews],
            "patterns": [{"theme": theme, "review_ids": sorted(ids), "count": len(ids)}
                         for theme, ids in sorted(themes.items(), key=lambda item: (-len(item[1]), item[0]))],
            "patterns_limited_to_recent": coverage["trades"] > limit,
            "legacy_notice": "Tradamind-posities komen na bewezen sluiting in beeld. Exchange-reviews met een onvolledige positiebasis verschijnen alleen na expliciete gebruikersbevestiging; oudere of ongekoppelde uitvoeringen kunnen ontbreken.",
        }

    async def review(self, user_id: int, review_id: int) -> dict[str, Any]:
        require_trade_review_access(user_id)
        if not await self._available():
            raise HTTPException(503, "Trade-reflecties nog niet beschikbaar")
        result = await self.session.execute(text("""
            SELECT id, bot_id,
                   (SELECT b.name FROM bot_configs b WHERE b.id=r.bot_id AND b.user_id=r.user_id) AS bot_name,
                   symbol, execution_environment, execution_sources, entry_at, exit_at,
                   origin, closure_basis, pnl_status, cash_legs_by_currency,
                   derivative_category, position_idx, direction, settle_currency,
                   native_pnl_status,
                   pnl_eur_before_fees, plan_snapshot, plan_provenance,
                   analysis_status, analysis_json, candles_status,
                   (SELECT jsonb_build_object(
                        'lesson_text',l.lesson_text,'confirmed_at',l.confirmed_at,
                        'evidence_revision',l.evidence_revision)
                    FROM finn_trade_review_lessons l
                    WHERE l.user_id=:user_id AND l.review_id=r.id
                      AND l.status='active' AND l.evidence_revision=r.input_revision
                   ) AS confirmed_lesson,
                   EXISTS (SELECT 1 FROM finn_trade_review_screenshots s
                           WHERE s.user_id=:user_id AND s.review_id=r.id) AS has_screenshot,
                   fills
            FROM finn_trade_reviews r WHERE r.user_id=:user_id AND r.id=:review_id
        """), {"user_id": user_id, "review_id": review_id})
        row = result.fetchone()
        if row is None:
            raise HTTPException(404, "Trade-reflectie niet gevonden")
        item = self._safe_row(dict(row._mapping))
        return {
            "contract": "closed_trade_reflection.v1", "action_class": "prepare_only",
            "allowed_side_effects": [], "status": item["analysis_status"],
            "review": item, "legacy_notice": "Exchange-sluiting op basis van gebruikersbevestiging blijft onderscheiden van een door de administratie bewezen gesloten positie.",
        }

    @staticmethod
    def _safe_row(row: dict) -> dict:
        analysis = row.get("analysis_json") or {}
        observations = analysis.get("observations") if isinstance(analysis, dict) else []
        themes = sorted({str(item.get("theme")) for item in observations or []
                         if isinstance(item, dict) and item.get("theme") in THEMES})
        fills = row.get("fills") or []
        sampled_fills = fills[:10] + fills[-10:] if len(fills) > 20 else fills
        derivative = row.get("origin") == "bybit_derivative_user_attested"
        exchange = row.get("origin") == "exchange_user_attested"
        has_proven_plan = bool(row.get("plan_snapshot") and row.get("plan_provenance"))
        lesson = row.get("confirmed_lesson")
        confirmed_lesson = None
        if isinstance(lesson, dict) and isinstance(lesson.get("lesson_text"), str) and lesson.get("confirmed_at"):
            confirmed_lesson = {
                "lesson_text": lesson["lesson_text"][:500],
                "confirmed_at": str(lesson["confirmed_at"]),
                "evidence_revision": lesson.get("evidence_revision"),
                "source": "user_confirmed_reflection_not_trade_fact_or_original_plan",
            }
        evidence_ids = ([f"derivative_exec:{item['derivative_execution_id']}:{item['role']}"
                         for item in sampled_fills if isinstance(item, dict)
                         and isinstance(item.get("derivative_execution_id"), int)
                         and item.get("role") in {"open", "close"}]
                        if derivative else
                        [f"exchange_fill:{item['exchange_fill_id']}" for item in sampled_fills
                         if isinstance(item, dict) and isinstance(item.get("exchange_fill_id"), int)]
                        if exchange else
                        [f"fill:{item['ledger_id']}" for item in sampled_fills
                         if isinstance(item, dict) and isinstance(item.get("ledger_id"), int)])
        if exchange or derivative:
            evidence_ids.append("closure:user-confirmed")
        if has_proven_plan:
            evidence_ids.append("plan:snapshot")
        if row.get("candles_status") == "ready":
            evidence_ids.append("chart:binance-eur")
        if row.get("has_screenshot"):
            evidence_ids.append("screenshot:user-upload")
        return {
            "review_id": int(row["id"]), "review_url": REVIEW_PATH.format(review_id=int(row["id"])),
            "symbol": re.sub(r"[^A-Z0-9._-]", "", str(row["symbol"]).upper())[:24],
            "environment": row["execution_environment"],
            "bot_id": row.get("bot_id"),
            "bot_name": row.get("bot_name"),
            "origin": row.get("origin") or "bot_position",
            "closure_basis": row.get("closure_basis") or "ledger_flat",
            "closure_label": "Afsluiting bevestigd door gebruiker" if exchange or derivative else "Afgesloten positie",
            "pnl_status": ("paper_cash_flow_including_simulated_costs"
                           if str(row.get("execution_environment")).lower() == "paper"
                           else row.get("pnl_status") or "before_fees_eur"),
            "cash_legs_by_currency": row.get("cash_legs_by_currency") if exchange else None,
            "derivative_category": row.get("derivative_category") if derivative else None,
            "position_idx": row.get("position_idx") if derivative else None,
            "direction": row.get("direction") if derivative else None,
            "settle_currency": row.get("settle_currency") if derivative else None,
            "native_pnl_status": row.get("native_pnl_status") if derivative else None,
            "execution_sources": row.get("execution_sources") or [],
            "entry_at": row["entry_at"].isoformat(), "exit_at": row["exit_at"].isoformat(),
            "pnl_eur_before_fees": str(row["pnl_eur_before_fees"]) if row.get("pnl_eur_before_fees") is not None else None,
            "has_plan": has_proven_plan,
            "confirmed_lesson": confirmed_lesson,
            "analysis_status": str(row["analysis_status"]),
            "chart_status": str(row["candles_status"]),
            "has_screenshot": bool(row.get("has_screenshot")),
            "evidence_ids": evidence_ids, "themes": themes,
            "evidence_truncated": len(fills) > 20,
            "interpretation_status": "model_assessment" if row["analysis_status"] == "ready" else "no_model_assessment",
        }

    @staticmethod
    def _empty(status: str, days: int) -> dict[str, Any]:
        return {
            "contract": "closed_trade_reflection.v1", "action_class": "prepare_only",
            "allowed_side_effects": [], "status": status, "time_window_days": days,
            "coverage": {"trades": 0, "analyzed": 0, "pending": 0, "unavailable": 0},
            "reviews": [], "review_ids": [], "patterns": [],
            "patterns_limited_to_recent": False,
            "legacy_notice": "Tradamind-posities komen na bewezen sluiting in beeld. Exchange-reviews met een onvolledige positiebasis verschijnen alleen na expliciete gebruikersbevestiging; oudere of ongekoppelde uitvoeringen kunnen ontbreken.",
        }
