from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import func, select, text
from backend.infrastructure.models import DailyScore, Setup
from typing import List, Dict, Any, Optional

class ScoreRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def fetch_active_setups(self, user_id: int) -> List[Dict[str, Any]]:
        from backend.infrastructure.repositories.setup_repository import SetupRepository
        from backend.services.setup_market_match_service import SetupMarketMatchService

        owned = [dict(row) for row in await SetupRepository(self.db).get_all_setups(user_id)]
        assessments = await SetupMarketMatchService(self.db).for_all_assets(user_id, setups=owned)
        by_id = {int(item["setup_id"]): item for item in assessments["matches"]}
        rows = []
        for setup in owned:
            match = by_id.get(int(setup["id"]))
            rows.append({
                **setup,
                "timestamp": setup.get("created_at"),
                "score": match["score"] if match else None,
                "is_active": match["is_active"] if match else False,
                "is_best": match["is_best"] if match else False,
                "status": match["status"] if match else "insufficient_data",
                "breakdown": match["components"] if match else {},
                "score_semantics": "benchmark_setup_match_v1",
            })
        rows.sort(key=lambda row: (row["is_active"], row["score"] if row["score"] is not None else -1), reverse=True)
        return rows

    async def get_global_insight(self, category: str) -> Optional[Dict[str, Any]]:
        """
        Haalt de meest recente globale AI-conclusie op voor een categorie.
        Robust to database schema differences (e.g. missing avg_score or fields nested in JSONB in some environments).
        """
        stmt = text("""
            SELECT *
            FROM global_market_insights
            WHERE category = :category
            ORDER BY date DESC, updated_at DESC
            LIMIT 1
        """)
        try:
            result = await self.db.execute(stmt, {"category": category})
            row = result.mappings().first()
            if not row:
                return None
            
            data = dict(row)
            # Ensure avg_score exists even if column is named 'score' or missing
            if "avg_score" not in data:
                data["avg_score"] = data.get("score", 0)
                
            # If production schema has fields nested in a JSONB 'data' column, unpack them robustly
            if "data" in data and isinstance(data["data"], dict):
                for k, v in data["data"].items():
                    if k not in data:
                        data[k] = v
                        
            return data
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(f"⚠️ Robust DB get_global_insight fallback activated: {e}")
            try:
                await self.db.rollback()
            except Exception:
                pass
            return None

    async def fetch_daily_scores(self, user_id: int, symbol: str = "BTC") -> Optional[Dict[str, Any]]:
        """
        Native async fetch of daily scores for the dashboard.
        """
        stmt = text("""
            SELECT 
                macro_score, macro_interpretation, macro_top_contributors,
                technical_score, technical_interpretation, technical_top_contributors,
                market_score, market_interpretation, market_top_contributors,
                setup_score, report_date, calculated_at, indicator_evidence
            FROM daily_scores
            WHERE user_id = :user_id AND report_date = CURRENT_DATE AND symbol = :symbol
            LIMIT 1
        """)
        result = await self.db.execute(stmt, {"user_id": user_id, "symbol": symbol})
        row = result.mappings().first()
        return dict(row) if row else None

    async def fetch_daily_scores_batch(
        self,
        user_id: int,
        symbols: List[str],
    ) -> Dict[str, Dict[str, Any]]:
        normalized = list(dict.fromkeys(str(symbol).upper() for symbol in symbols if symbol))
        if not normalized:
            return {}

        ranked = (
            select(
                DailyScore.id.label("id"),
                func.row_number()
                .over(partition_by=DailyScore.symbol, order_by=DailyScore.report_date.desc())
                .label("row_number"),
            )
            .where(
                DailyScore.user_id == user_id,
                DailyScore.symbol.in_(normalized),
            )
            .subquery()
        )
        stmt = (
            select(DailyScore)
            .join(ranked, DailyScore.id == ranked.c.id)
            .where(ranked.c.row_number == 1)
        )
        result = await self.db.execute(stmt)
        return {
            str(row.symbol).upper(): {
                "symbol": row.symbol,
                "macro_score": row.macro_score,
                "technical_score": row.technical_score,
                "market_score": row.market_score,
                "setup_score": row.setup_score,
                "report_date": row.report_date,
                "calculated_at": row.calculated_at,
                "indicator_evidence": row.indicator_evidence,
            }
            for row in result.scalars().all()
        }

    async def fetch_historical_scores(self, user_id: int, days: int = 30, symbol: str = "BTC") -> List[Dict[str, Any]]:
        """
        Fetches historical scores and asset prices for the analytics chart.
        """
        stmt = text("""
            SELECT 
                ds.report_date as date,
                ds.macro_score,
                ds.technical_score,
                ds.market_score,
                ds.setup_score,
                md.price as btc_price,
                md.price as asset_price
            FROM daily_scores ds
            LEFT JOIN (
                SELECT DISTINCT ON (symbol, timestamp::date) symbol, price, timestamp::date as d
                FROM market_data
                ORDER BY symbol, timestamp::date, timestamp DESC
            ) md ON md.symbol = ds.symbol AND md.d = ds.report_date
            WHERE ds.user_id = :user_id AND ds.symbol = :symbol
            AND ds.report_date >= CURRENT_DATE - INTERVAL '1 day' * :days
            ORDER BY ds.report_date ASC
        """)
        result = await self.db.execute(stmt, {"user_id": user_id, "days": days, "symbol": symbol})
        return [dict(row) for row in result.mappings()]
