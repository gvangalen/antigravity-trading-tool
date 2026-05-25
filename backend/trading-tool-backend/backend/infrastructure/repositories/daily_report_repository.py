from __future__ import annotations

from datetime import date
from typing import Any, Dict, Optional

from sqlalchemy import bindparam, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Session


class DailyReportWriteRepository:
    """Repository boundary for the sync Celery daily report write path."""

    JSONB_FIELDS = (
        "executive_summary",
        "market_analysis",
        "macro_context",
        "technical_analysis",
        "setup_validation",
        "strategy_implication",
        "outlook",
        "bot_strategy",
        "bot_snapshot",
        "market_indicator_highlights",
        "macro_indicator_highlights",
        "technical_indicator_highlights",
        "best_setup",
        "top_setups",
        "active_strategy",
    )

    def __init__(self, db: Session):
        self.db = db

    def upsert_daily_report(
        self,
        *,
        user_id: int,
        report_date: date,
        sections: Dict[str, Any],
        price: Optional[float],
        change_24h: Optional[float],
        volume: Optional[float],
        macro_score: Optional[float],
        technical_score: Optional[float],
        market_score: Optional[float],
        setup_score: Optional[float],
    ) -> None:
        stmt = text(
            """
            INSERT INTO daily_reports (
                report_date, user_id,
                executive_summary, market_analysis, macro_context,
                technical_analysis, setup_validation, strategy_implication, outlook,
                bot_strategy, bot_snapshot,
                price, change_24h, volume,
                macro_score, technical_score, market_score, setup_score,
                market_indicator_highlights, macro_indicator_highlights, technical_indicator_highlights,
                best_setup, top_setups, active_strategy
            )
            VALUES (
                :report_date, :user_id,
                :executive_summary, :market_analysis, :macro_context,
                :technical_analysis, :setup_validation, :strategy_implication, :outlook,
                :bot_strategy, :bot_snapshot,
                :price, :change_24h, :volume,
                :macro_score, :technical_score, :market_score, :setup_score,
                :market_indicator_highlights, :macro_indicator_highlights, :technical_indicator_highlights,
                :best_setup, :top_setups, :active_strategy
            )
            ON CONFLICT (user_id, report_date)
            DO UPDATE SET
                executive_summary = EXCLUDED.executive_summary,
                market_analysis = EXCLUDED.market_analysis,
                macro_context = EXCLUDED.macro_context,
                technical_analysis = EXCLUDED.technical_analysis,
                setup_validation = EXCLUDED.setup_validation,
                strategy_implication = EXCLUDED.strategy_implication,
                outlook = EXCLUDED.outlook,
                bot_strategy = EXCLUDED.bot_strategy,
                bot_snapshot = EXCLUDED.bot_snapshot,
                price = EXCLUDED.price,
                change_24h = EXCLUDED.change_24h,
                volume = EXCLUDED.volume,
                macro_score = EXCLUDED.macro_score,
                technical_score = EXCLUDED.technical_score,
                market_score = EXCLUDED.market_score,
                setup_score = EXCLUDED.setup_score,
                market_indicator_highlights = EXCLUDED.market_indicator_highlights,
                macro_indicator_highlights = EXCLUDED.macro_indicator_highlights,
                technical_indicator_highlights = EXCLUDED.technical_indicator_highlights,
                best_setup = EXCLUDED.best_setup,
                top_setups = EXCLUDED.top_setups,
                active_strategy = EXCLUDED.active_strategy,
                generated_at = NOW();
            """
        )
        for field in self.JSONB_FIELDS:
            stmt = stmt.bindparams(bindparam(field, type_=JSONB))

        self.db.execute(
            stmt,
            {
                "report_date": report_date,
                "user_id": user_id,
                "price": price,
                "change_24h": change_24h,
                "volume": volume,
                "macro_score": macro_score,
                "technical_score": technical_score,
                "market_score": market_score,
                "setup_score": setup_score,
                **{field: sections.get(field) for field in self.JSONB_FIELDS},
            },
        )
