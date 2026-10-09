"""Owner-scoped, read-only setup matching over today's measured score sources."""

from __future__ import annotations

import json

from sqlalchemy import text

from backend.domain.finn_dca_plan_contract import benchmark_score, normalize_benchmark_weights
from backend.domain.setup_market_match import rank_matches
from backend.infrastructure.repositories.setup_repository import SetupRepository
from backend.utils.scoring_utils import score_snapshot_is_current


class SetupMarketMatchService:
    def __init__(self, session, *, daily_rows: dict | None = None):
        self.session = session
        self.setups = SetupRepository(session)
        self.daily_rows = daily_rows
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

    async def _source_is_fresh(self, user_id: int, symbol: str, category: str,
                               row: dict, source_moments: dict | None = None) -> bool:
        table, name_column = {
            "macro": ("macro_data", "name"),
            "technical": ("technical_indicators", "indicator"),
            "market": ("market_data_indicators", "name"),
        }[category]
        parameters = {"user_id": user_id, "symbol": symbol}
        configured_result = await self.session.execute(text("""
            SELECT indicator, updated_at FROM user_indicator_configs
            WHERE user_id = :user_id AND category = :category
              AND symbol = :symbol AND enabled = TRUE
        """), {**parameters, "category": category})
        configured = configured_result.fetchall()
        asset_clause = "" if category == "macro" else "AND symbol = :symbol"
        # Table and column names are selected from the constant map above.
        result = await self.session.execute(text(f"""
            SELECT DISTINCT ON ({name_column}) {name_column}, value, source_observed_at
            FROM {table}
            WHERE user_id = :user_id {asset_clause}
            ORDER BY {name_column}, source_observed_at DESC NULLS LAST, timestamp DESC NULLS LAST
        """), parameters)
        observations = result.fetchall()
        if source_moments is not None:
            configured_names = {str(item[0]).casefold() for item in configured}
            source_moments[category] = {
                str(item[0]): item[2].isoformat() if item[2] is not None else None
                for item in observations if str(item[0]).casefold() in configured_names
            }
        evidence = row.get("indicator_evidence") or {}
        if isinstance(evidence, str):
            try:
                evidence = json.loads(evidence)
            except json.JSONDecodeError:
                evidence = {}
        return score_snapshot_is_current(
            category, symbol, configured, observations,
            evidence.get(category) if isinstance(evidence, dict) else None,
            row.get("calculated_at"),
        )

    async def for_asset(self, user_id: int, symbol: str, *, setups=None) -> dict:
        symbol = str(symbol or "").strip().upper()
        owned = list(setups) if setups is not None else await self.setups.get_all_setups(user_id)
        selected = [dict(row) for row in owned if str(row.get("symbol") or "").upper() == symbol]
        weights = await self._benchmark_weights(user_id)

        if self.daily_rows is not None:
            row = self.daily_rows.get(symbol)
        else:
            result = await self.session.execute(text("""
                SELECT report_date, macro_score, technical_score, market_score,
                       calculated_at, indicator_evidence
                FROM daily_scores
                WHERE user_id = :user_id AND symbol = :symbol AND report_date = CURRENT_DATE
                LIMIT 1
            """), {"user_id": user_id, "symbol": symbol})
            row = result.mappings().first()
        scores = None
        source_status = "missing_scores"
        stored_scores = {
            f"{category}_score": float(row[f"{category}_score"])
            if row and row.get(f"{category}_score") is not None else None
            for category in ("macro", "technical", "market")
        }
        component_source_status = {
            score_key: "missing_score" if value is None else "unverified"
            for score_key, value in stored_scores.items()
        }
        component_source_observed_at: dict[str, dict] = {}
        if weights is None:
            source_status = "invalid_weights"
        elif row and self.daily_rows is not None:
            from datetime import date
            if row.get("report_date") != date.today():
                source_status = "stale_scores"
        if source_status == "stale_scores":
            component_source_status = {
                score_key: "stale_report" if value is not None else "missing_score"
                for score_key, value in stored_scores.items()
            }
        elif row:
            for category in ("macro", "technical", "market"):
                score_key = f"{category}_score"
                value = stored_scores[score_key]
                if value is not None:
                    component_source_status[score_key] = (
                        "fresh" if await self._source_is_fresh(
                            user_id, symbol, category, row, component_source_observed_at,
                        )
                        else "stale_source"
                    )
            if weights is not None and all(
                component_source_status[f"{category}_score"] == "fresh"
                for category in ("macro", "technical", "market")
            ):
                scores = {category: stored_scores[f"{category}_score"]
                          for category in ("macro", "technical", "market")}
                source_status = "available"
            elif weights is not None and all(value is not None for value in stored_scores.values()):
                source_status = "stale_sources"
        # The match response describes what Analyse can use now. Historical or
        # stale database values belong in the explicitly dated saved-report read.
        reported_scores = {
            key: value if component_source_status[key] == "fresh" else None
            for key, value in stored_scores.items()
        }
        total_benchmark = None
        if scores is not None and weights is not None:
            weighted_scores = {f"{category}_score": float(value) for category, value in scores.items()}
            total_benchmark = benchmark_score(
                weighted_scores, weights,
                {component: True for component in weighted_scores},
            )
        matches = rank_matches(selected, scores, weights)
        matches = [{**match, "benchmark_score": total_benchmark,
                    "benchmark_weights": weights,
                    "reported_scores": reported_scores,
                    "component_source_status": component_source_status} for match in matches]
        return {
            "symbol": symbol,
            "as_of": row["report_date"] if row else None,
            "source_status": source_status,
            "benchmark_score": total_benchmark,
            "benchmark_weights": weights,
            "reported_scores": reported_scores,
            "component_source_status": component_source_status,
            "component_source_observed_at": component_source_observed_at,
            "matches": matches,
        }

    async def for_all_assets(self, user_id: int, *, setups=None) -> dict:
        owned = list(setups) if setups is not None else await self.setups.get_all_setups(user_id)
        symbols = sorted({str(row.get("symbol") or "").upper() for row in owned if row.get("symbol")})
        if self.daily_rows is None and symbols:
            result = await self.session.execute(text("""
                SELECT symbol, report_date, macro_score, technical_score, market_score,
                       calculated_at, indicator_evidence
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
