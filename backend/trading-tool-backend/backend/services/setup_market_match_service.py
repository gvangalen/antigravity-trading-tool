"""Owner-scoped, read-only setup matching over today's measured score sources."""

from __future__ import annotations

import json

from sqlalchemy import text

from backend.domain.finn_dca_plan_contract import benchmark_score, normalize_benchmark_weights
from backend.domain.setup_market_match import rank_matches
from backend.infrastructure.repositories.setup_repository import SetupRepository
from backend.utils.scoring_utils import score_source_is_fresh


class SetupMarketMatchService:
    def __init__(self, session, *, daily_rows: dict | None = None):
        self.session = session
        self.setups = SetupRepository(session)
        self.daily_rows = daily_rows
        self._macro_fresh_by_user: dict[int, bool] = {}
        self._weights_by_user: dict[int, dict[str, float] | None] = {}

    async def _benchmark_weights(self, user_id: int) -> dict[str, float] | None:
        if user_id in self._weights_by_user:
            return self._weights_by_user[user_id]
        result = await self.session.execute(text("""
            SELECT ai_preferences FROM users WHERE id = :user_id
        """), {"user_id": user_id})
        row = result.mappings().first()
        if row is None:
            self._weights_by_user[user_id] = None
            return None
        preferences = row.get("ai_preferences")
        if isinstance(preferences, str):
            try:
                preferences = json.loads(preferences)
            except json.JSONDecodeError:
                self._weights_by_user[user_id] = None
                return None
        if preferences is not None and not isinstance(preferences, dict):
            self._weights_by_user[user_id] = None
            return None
        custom = preferences.get("intelligence_weights") if isinstance(preferences, dict) else None
        weights = normalize_benchmark_weights(custom)
        self._weights_by_user[user_id] = weights
        return weights

    async def _source_is_fresh(self, user_id: int, symbol: str, category: str) -> bool:
        if category == "macro" and user_id in self._macro_fresh_by_user:
            return self._macro_fresh_by_user[user_id]
        table, name_column = {
            "macro": ("macro_data", "name"),
            "technical": ("technical_indicators", "indicator"),
            "market": ("market_data_indicators", "name"),
        }[category]
        parameters = {"user_id": user_id, "symbol": symbol}
        configured = None
        if category == "technical":
            configured_result = await self.session.execute(text("""
                SELECT indicator FROM user_indicator_configs
                WHERE user_id = :user_id AND category = 'technical'
                  AND symbol = :symbol AND enabled = TRUE
            """), parameters)
            configured = {row[0] for row in configured_result.fetchall()}
            if not configured:
                return False
        asset_clause = "" if category == "macro" else "AND symbol = :symbol"
        # Table and column names are selected from the constant map above.
        result = await self.session.execute(text(f"""
            SELECT DISTINCT ON ({name_column}) {name_column}, source_observed_at
            FROM {table}
            WHERE user_id = :user_id {asset_clause}
            ORDER BY {name_column}, source_observed_at DESC NULLS LAST, timestamp DESC NULLS LAST
        """), parameters)
        rows = result.fetchall()
        if configured is not None:
            rows = [row for row in rows if row[0] in configured]
            if {row[0] for row in rows} != configured:
                return False
        fresh = bool(rows) and all(
            score_source_is_fresh(category, row[0], row[1], symbol=symbol)
            for row in rows
        )
        if category == "macro":
            self._macro_fresh_by_user[user_id] = fresh
        return fresh

    async def for_asset(self, user_id: int, symbol: str, *, setups=None) -> dict:
        symbol = str(symbol or "").strip().upper()
        owned = list(setups) if setups is not None else await self.setups.get_all_setups(user_id)
        selected = [dict(row) for row in owned if str(row.get("symbol") or "").upper() == symbol]
        weights = await self._benchmark_weights(user_id)

        if self.daily_rows is not None:
            row = self.daily_rows.get(symbol)
        else:
            result = await self.session.execute(text("""
                SELECT report_date, macro_score, technical_score, market_score
                FROM daily_scores
                WHERE user_id = :user_id AND symbol = :symbol AND report_date = CURRENT_DATE
                LIMIT 1
            """), {"user_id": user_id, "symbol": symbol})
            row = result.mappings().first()
        scores = None
        source_status = "missing_scores"
        if weights is None:
            source_status = "invalid_weights"
        elif row and self.daily_rows is not None:
            from datetime import date
            if row.get("report_date") != date.today():
                source_status = "stale_scores"
        if weights is not None and source_status != "stale_scores" and row and all(
            row[key] is not None for key in ("macro_score", "technical_score", "market_score")
        ):
            source_status = "stale_sources"
            if all([await self._source_is_fresh(user_id, symbol, category)
                    for category in ("macro", "technical", "market")]):
                scores = {category: row[f"{category}_score"] for category in ("macro", "technical", "market")}
                source_status = "available"
        total_benchmark = None
        if scores is not None and weights is not None:
            weighted_scores = {f"{category}_score": float(value) for category, value in scores.items()}
            total_benchmark = benchmark_score(
                weighted_scores, weights,
                {component: True for component in weighted_scores},
            )
        matches = rank_matches(selected, scores, weights)
        matches = [{**match, "benchmark_score": total_benchmark,
                    "benchmark_weights": weights} for match in matches]
        return {
            "symbol": symbol,
            "as_of": row["report_date"] if row else None,
            "source_status": source_status,
            "benchmark_score": total_benchmark,
            "benchmark_weights": weights,
            "matches": matches,
        }

    async def for_all_assets(self, user_id: int, *, setups=None) -> dict:
        owned = list(setups) if setups is not None else await self.setups.get_all_setups(user_id)
        symbols = sorted({str(row.get("symbol") or "").upper() for row in owned if row.get("symbol")})
        if self.daily_rows is None and symbols:
            result = await self.session.execute(text("""
                SELECT symbol, report_date, macro_score, technical_score, market_score
                FROM daily_scores WHERE user_id = :user_id AND report_date = CURRENT_DATE
                  AND symbol = ANY(:symbols)
            """), {"user_id": user_id, "symbols": symbols})
            self.daily_rows = {str(row["symbol"]).upper(): row for row in result.mappings().all()}
        matches = []
        for symbol in symbols:
            assessment = await self.for_asset(user_id, symbol, setups=owned)
            matches.extend({**match, "as_of": assessment["as_of"],
                            "source_status": assessment["source_status"]}
                           for match in assessment["matches"])
        matches.sort(key=lambda item: (item["is_active"], item["score"] if item["score"] is not None else -1), reverse=True)
        return {"symbol": "ALL", "as_of": None, "source_status": "per_asset", "matches": matches}
