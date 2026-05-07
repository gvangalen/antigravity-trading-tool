from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, text
from backend.infrastructure.models import AiCategoryInsight, Setup, DailySetupScore
from datetime import date
from typing import List, Dict, Any, Optional

class ScoreRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def fetch_active_setups(self, user_id: int) -> List[Dict[str, Any]]:
        today = date.today()
        stmt = text("""
            SELECT DISTINCT ON (s.id)
                   s.id,
                   s.name,
                   COALESCE(s.symbol, 'BTC') AS symbol,
                   COALESCE(s.timeframe, '1D') AS timeframe,
                   COALESCE(s.explanation, '') AS explanation,
                   s.created_at AS timestamp,
                   COALESCE(ds.score, 0) AS score,
                   COALESCE(ds.active, false) AS is_active,
                   COALESCE(ds.breakdown, '{}'::jsonb) AS breakdown
            FROM setups s
            LEFT JOIN daily_setup_scores ds
                ON ds.setup_id = s.id
                AND ds.report_date = :today
            WHERE s.user_id = :user_id
            ORDER BY s.id, ds.report_date DESC
            LIMIT 100
        """)
        
        result = await self.db.execute(stmt, {"today": today, "user_id": user_id})
        
        # Build dictionary from rows
        mapped = []
        for row in result.mappings():
            mapped.append(dict(row))
        return mapped

    async def get_master_score(self, user_id: int, symbol: str = "BTC") -> Optional[AiCategoryInsight]:
        # Filter by user, category and symbol (Master scores are now partitioned by symbol)
        stmt = select(AiCategoryInsight).where(
            AiCategoryInsight.user_id == user_id,
            AiCategoryInsight.category == 'master',
            AiCategoryInsight.symbol == symbol
        ).order_by(AiCategoryInsight.date.desc()).limit(1)
        
        result = await self.db.execute(stmt)
        return result.scalars().first()

    async def get_global_insight(self, category: str) -> Optional[Dict[str, Any]]:
        """
        Haalt de meest recente globale AI-conclusie op voor een categorie.
        Robust to database schema differences (e.g. missing avg_score or fields nested in JSONB in some environments).
        """
        stmt = text("""
            SELECT *
            FROM global_market_insights
            WHERE category = :category
            ORDER BY date DESC, created_at DESC
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
                setup_score, report_date
            FROM daily_scores
            WHERE user_id = :user_id AND report_date = CURRENT_DATE AND symbol = :symbol
            LIMIT 1
        """)
        result = await self.db.execute(stmt, {"user_id": user_id, "symbol": symbol})
        row = result.mappings().first()
        return dict(row) if row else None

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

    async def save_daily_combined_score(self, user_id: int, symbol: str, scores: Dict[str, Any]):
        """
        Persist aggregated scores to daily_scores table (UPSERT).
        """
        stmt = text("""
            INSERT INTO daily_scores (
                user_id, symbol, report_date,
                macro_score, technical_score, market_score, setup_score,
                macro_interpretation, technical_interpretation, market_interpretation
            )
            VALUES (
                :user_id, :symbol, CURRENT_DATE,
                :macro, :technical, :market, :setup,
                :macro_int, :tech_int, :market_int
            )
            ON CONFLICT (user_id, symbol, report_date)
            DO UPDATE SET
                macro_score = EXCLUDED.macro_score,
                technical_score = EXCLUDED.technical_score,
                market_score = EXCLUDED.market_score,
                setup_score = EXCLUDED.setup_score,
                macro_interpretation = EXCLUDED.macro_interpretation,
                technical_interpretation = EXCLUDED.technical_interpretation,
                market_interpretation = EXCLUDED.market_interpretation
        """)
        await self.db.execute(stmt, {
            "user_id": user_id,
            "symbol": symbol,
            "macro": scores.get("macro", 0),
            "technical": scores.get("technical", 0),
            "market": scores.get("market", 0),
            "setup": scores.get("setup", 0),
            "macro_int": scores.get("macro_interpretation", ""),
            "tech_int": scores.get("technical_interpretation", ""),
            "market_int": scores.get("market_interpretation", "")
        })
        await self.db.commit()
