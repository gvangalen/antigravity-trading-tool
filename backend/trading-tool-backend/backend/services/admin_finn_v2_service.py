"""Bounded, aggregate FINN V2 operational data for administrators."""

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.services.finn_v2_flag_service import FinnV2FlagService


class AdminFinnV2Service:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def overview(self) -> dict:
        row = (await self.db.execute(text("""
            SELECT
                COUNT(*) FILTER (WHERE created_at >= NOW() - INTERVAL '24 hours') AS runs_24h,
                COUNT(*) FILTER (WHERE created_at >= NOW() - INTERVAL '24 hours' AND visibility = 'visible') AS visible_runs_24h,
                COUNT(*) FILTER (WHERE created_at >= NOW() - INTERVAL '24 hours' AND status = 'completed') AS completed_24h,
                COUNT(*) FILTER (WHERE created_at >= NOW() - INTERVAL '24 hours' AND status = 'clarification_required') AS clarifications_24h,
                COUNT(*) FILTER (WHERE created_at >= NOW() - INTERVAL '24 hours' AND status IN ('unavailable', 'failed', 'downgraded')) AS unavailable_24h,
                COUNT(*) FILTER (WHERE created_at >= NOW() - INTERVAL '24 hours' AND status NOT IN ('completed', 'clarification_required', 'unavailable', 'failed', 'downgraded', 'cancelled')) AS in_progress_24h,
                AVG(EXTRACT(EPOCH FROM (completed_at - created_at)) * 1000)
                    FILTER (WHERE created_at >= NOW() - INTERVAL '24 hours' AND status = 'completed') AS avg_completed_latency_ms_24h,
                MAX(created_at) AS latest_run_at
            FROM finn_v2_runs
        """))).mappings().one()
        issues = (await self.db.execute(text("""
            SELECT trace_id, status, error_code, created_at
            FROM finn_v2_runs
            WHERE status IN ('unavailable', 'failed', 'downgraded')
            ORDER BY created_at DESC
            LIMIT 10
        """))).mappings().all()
        return {
            "runtime_mode": FinnV2FlagService().runtime_mode(),
            "runs_24h": int(row["runs_24h"] or 0),
            "visible_runs_24h": int(row["visible_runs_24h"] or 0),
            "completed_24h": int(row["completed_24h"] or 0),
            "clarifications_24h": int(row["clarifications_24h"] or 0),
            "unavailable_24h": int(row["unavailable_24h"] or 0),
            "in_progress_24h": int(row["in_progress_24h"] or 0),
            "avg_completed_latency_ms_24h": float(row["avg_completed_latency_ms_24h"])
            if row["avg_completed_latency_ms_24h"] is not None else None,
            "latest_run_at": row["latest_run_at"],
            "recent_issues": [dict(issue) for issue in issues],
        }
