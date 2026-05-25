from __future__ import annotations

from datetime import date
from typing import Any, Dict, Optional

from sqlalchemy import bindparam, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Session


class RegimeMemoryRepository:
    """Repository boundary for regime_memory legacy Celery/report flows."""

    def __init__(self, db: Session):
        self.db = db

    def get_latest(self, user_id: int) -> Optional[Dict[str, Any]]:
        result = self.db.execute(
            text(
                """
                SELECT date, regime_label, confidence, signals_json, narrative
                FROM regime_memory
                WHERE user_id = :user_id
                ORDER BY date DESC
                LIMIT 1;
                """
            ),
            {"user_id": user_id},
        )
        row = result.mappings().first()
        if not row:
            return None

        row_date = row["date"]
        confidence = row["confidence"]
        return {
            "date": row_date.isoformat() if row_date else None,
            "regime_label": row["regime_label"],
            "confidence": float(confidence) if confidence is not None else None,
            "signals_json": row["signals_json"],
            "narrative": row["narrative"],
        }

    def upsert(
        self,
        *,
        user_id: int,
        memory_date: date,
        regime_label: str,
        confidence: float,
        signals_json: Dict[str, Any],
        narrative: str,
    ) -> None:
        stmt = text(
            """
            INSERT INTO regime_memory (
                user_id, date, regime_label, confidence, signals_json, narrative
            )
            VALUES (
                :user_id, :memory_date, :regime_label, :confidence, :signals_json, :narrative
            )
            ON CONFLICT (user_id, date)
            DO UPDATE SET
                regime_label = EXCLUDED.regime_label,
                confidence   = EXCLUDED.confidence,
                signals_json = EXCLUDED.signals_json,
                narrative    = EXCLUDED.narrative,
                created_at   = NOW();
            """
        ).bindparams(bindparam("signals_json", type_=JSONB))

        self.db.execute(
            stmt,
            {
                "user_id": user_id,
                "memory_date": memory_date,
                "regime_label": regime_label,
                "confidence": confidence,
                "signals_json": signals_json,
                "narrative": narrative,
            },
        )
