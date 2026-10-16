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

    async def recent(self, user_id: int, *, days: int = 7, limit: int = 10) -> dict[str, Any]:
        if not 1 <= days <= 30 or not 1 <= limit <= 20:
            raise ValueError("Invalid trade-reflection window")
        if not trade_review_enabled(user_id):
            return self._empty("disabled", days)
        if not await self._available():
            return self._empty("migration_unavailable", days)
        totals = await self.session.execute(text("""
            SELECT COUNT(*) AS trades,
                   COUNT(*) FILTER (WHERE analysis_status='ready') AS analyzed,
                   COUNT(*) FILTER (WHERE analysis_status='pending' OR analysis_status='running') AS pending,
                   COUNT(*) FILTER (WHERE analysis_status IN ('failed','unavailable')) AS unavailable
            FROM finn_trade_reviews
            WHERE user_id=:user_id AND exit_at >= NOW() - (:days * INTERVAL '1 day')
        """), {"user_id": user_id, "days": days})
        coverage = dict(totals.fetchone()._mapping)
        rows = await self.session.execute(text("""
            SELECT id, symbol, execution_environment, execution_sources, entry_at, exit_at,
                   pnl_eur_before_fees, plan_snapshot IS NOT NULL AS has_plan,
                   analysis_status, analysis_json, candles_status,
                   EXISTS (SELECT 1 FROM finn_trade_review_screenshots s
                           WHERE s.user_id=:user_id AND s.review_id=r.id) AS has_screenshot,
                   fills
            FROM finn_trade_reviews r
            WHERE user_id=:user_id AND exit_at >= NOW() - (:days * INTERVAL '1 day')
            ORDER BY exit_at DESC, id DESC LIMIT :limit
        """), {"user_id": user_id, "days": days, "limit": limit})
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
            "legacy_notice": "Alleen bevestigde gesloten trades binnen ondersteunde botportfolio's na de overgang; externe en oudere trades zijn niet opgenomen.",
        }

    async def review(self, user_id: int, review_id: int) -> dict[str, Any]:
        require_trade_review_access(user_id)
        if not await self._available():
            raise HTTPException(503, "Trade-reflecties nog niet beschikbaar")
        result = await self.session.execute(text("""
            SELECT id, symbol, execution_environment, execution_sources, entry_at, exit_at,
                   pnl_eur_before_fees, plan_snapshot IS NOT NULL AS has_plan,
                   analysis_status, analysis_json, candles_status,
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
            "review": item, "legacy_notice": "Alleen bevestigde gesloten trades binnen ondersteunde botportfolio's na de overgang; externe trades zijn niet opgenomen.",
        }

    @staticmethod
    def _safe_row(row: dict) -> dict:
        analysis = row.get("analysis_json") or {}
        observations = analysis.get("observations") if isinstance(analysis, dict) else []
        themes = sorted({str(item.get("theme")) for item in observations or []
                         if isinstance(item, dict) and item.get("theme") in THEMES})
        fills = row.get("fills") or []
        sampled_fills = fills[:10] + fills[-10:] if len(fills) > 20 else fills
        evidence_ids = [f"fill:{item['ledger_id']}" for item in sampled_fills
                        if isinstance(item, dict) and isinstance(item.get("ledger_id"), int)]
        if row.get("has_plan"):
            evidence_ids.append("plan:snapshot")
        if row.get("candles_status") == "ready":
            evidence_ids.append("chart:binance-eur")
        if row.get("has_screenshot"):
            evidence_ids.append("screenshot:user-upload")
        return {
            "review_id": int(row["id"]), "review_url": REVIEW_PATH.format(review_id=int(row["id"])),
            "symbol": re.sub(r"[^A-Z0-9._-]", "", str(row["symbol"]).upper())[:24],
            "environment": row["execution_environment"],
            "execution_sources": row.get("execution_sources") or [],
            "entry_at": row["entry_at"].isoformat(), "exit_at": row["exit_at"].isoformat(),
            "pnl_eur_before_fees": str(row["pnl_eur_before_fees"]),
            "has_plan": bool(row.get("has_plan")),
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
            "legacy_notice": "Alleen bevestigde gesloten trades binnen ondersteunde botportfolio's na de overgang; externe en oudere trades zijn niet opgenomen.",
        }
