from __future__ import annotations

from backend.infrastructure.repositories.report_repository import ReportRepository
from backend.schemas.finn_v2_evidence_schema import LatestReportData


class ReportToolAdapter:
    def __init__(self, session):
        self.repository = ReportRepository(session)

    async def execute(self, *, user_id: int, asset: str, selector: dict, **_kwargs):
        table_name = selector.get("report_type") or "daily_reports"
        row = await self.repository.get_latest_report(user_id, table_name)
        if not row:
            raise LookupError("report_not_found")
        payload = LatestReportData(
            report_type=table_name,
            report_date=row.get("report_date"),
            symbol=asset,
            status=row.get("status"),
            id=row.get("id"),
        )
        return {
            "data": payload,
            "summary": {"title": "latest_report", "report_type": table_name, "report_date": str(payload.report_date) if payload.report_date else None},
            "as_of": row.get("report_date"),
            "source": table_name,
            "schema_name": "LatestReportData",
            "entity_type": "latest_report",
            "asset": asset,
        }
