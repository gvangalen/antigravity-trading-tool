import logging
from typing import Optional, List, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

logger = logging.getLogger(__name__)

class ReportRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    def _validate_table_name(self, table_name: str) -> None:
        allowed = {"daily_reports", "weekly_reports", "monthly_reports", "quarterly_reports"}
        if table_name not in allowed:
            raise ValueError("Invalid report table name")

    async def get_latest_report(self, user_id: int, table_name: str) -> Optional[Dict[str, Any]]:
        self._validate_table_name(table_name)
        stmt = text(f"""
            SELECT *
            FROM {table_name}
            WHERE user_id = :u
            ORDER BY report_date DESC
            LIMIT 1;
        """)
        result = await self.db.execute(stmt, {"u": user_id})
        row = result.mappings().first()
        return dict(row) if row else None

    async def get_report_by_date(self, user_id: int, table_name: str, report_date) -> Optional[Dict[str, Any]]:
        self._validate_table_name(table_name)
        stmt = text(f"""
            SELECT *
            FROM {table_name}
            WHERE report_date = :d
            AND user_id = :u
            LIMIT 1;
        """)
        result = await self.db.execute(stmt, {"d": report_date, "u": user_id})
        row = result.mappings().first()
        return dict(row) if row else None

    async def get_report_history(self, user_id: int, table_name: str, limit: int = 10) -> List[str]:
        self._validate_table_name(table_name)
        stmt = text(f"""
            SELECT report_date
            FROM {table_name}
            WHERE user_id = :u
            ORDER BY report_date DESC
            LIMIT :l;
        """)
        result = await self.db.execute(stmt, {"u": user_id, "l": limit})
        return [row[0].isoformat() for row in result.fetchall()]

    async def get_public_snapshot(self, token: str) -> Optional[Dict[str, Any]]:
        stmt = text("""
            SELECT report_json, valid_until, status
            FROM report_snapshots
            WHERE token = :token
            LIMIT 1;
        """)
        result = await self.db.execute(stmt, {"token": token})
        row = result.mappings().first()
        return dict(row) if row else None

    async def create_report_snapshot(self, user_id: int, report_type: str, report_id: int, report_json: Dict[str, Any]) -> str:
        import uuid
        import json
        from datetime import datetime, timedelta, date
        from decimal import Decimal
        
        # Helper to serialize dates and decimals
        def json_serial(obj):
            if isinstance(obj, (datetime, date)):
                return obj.isoformat()
            if isinstance(obj, Decimal):
                return float(obj)
            raise TypeError("Type %s not serializable" % type(obj))

        token = str(uuid.uuid4())
        valid_until = datetime.utcnow() + timedelta(minutes=10)
        
        json_str = json.dumps(report_json, default=json_serial)

        stmt = text("""
            INSERT INTO report_snapshots (token, user_id, report_type, report_id, report_json, valid_until, status, created_at)
            VALUES (:t, :u, :rt, :rid, CAST(:j AS JSONB), :v, 'ready', NOW())
            ON CONFLICT (user_id, report_type, report_id) 
            DO UPDATE SET 
                token = EXCLUDED.token, 
                report_json = EXCLUDED.report_json, 
                valid_until = EXCLUDED.valid_until,
                created_at = NOW()
            RETURNING token;
        """)
        
        result = await self.db.execute(stmt, {
            "t": token,
            "u": user_id,
            "rt": report_type,
            "rid": report_id,
            "j": json_str,
            "v": valid_until
        })
        
        row = result.mappings().first()
        await self.db.commit()
        
        return row["token"] if row else token
