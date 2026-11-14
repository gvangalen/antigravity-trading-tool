from __future__ import annotations

import json
from datetime import date

from backend.infrastructure.repositories.report_repository import ReportRepository
from backend.schemas.finn_v2_evidence_schema import LatestReportData
from backend.services.finn_v2_tool_adapters.display_source_moment import (
    amsterdam_source_moment, display_source_moment,
)


class ReportToolAdapter:
    def __init__(self, session):
        self.repository = ReportRepository(session)

    async def execute(self, *, user_id: int, asset: str, selector: dict, **_kwargs):
        table_name = selector.get("report_type") or "daily_reports"
        if selector.get("report_date_unresolved"):
            raise LookupError("report_date_required")
        requested_date = selector.get("report_date")
        row = (await self.repository.get_report_by_date(
            user_id, table_name, date.fromisoformat(str(requested_date)),
        ) if requested_date else await self.repository.get_latest_report(user_id, table_name))
        if not row:
            raise LookupError("report_not_found")
        snapshot = row.get("score_source_snapshot") if table_name == "daily_reports" else None
        if isinstance(snapshot, str):
            try:
                snapshot = json.loads(snapshot)
            except ValueError:
                snapshot = None
        if not isinstance(snapshot, dict):
            snapshot = None
        elif isinstance(snapshot.get("assets"), list):
            if asset and not any(
                isinstance(item, dict) and str(item.get("symbol") or "").upper() == asset.upper()
                for item in snapshot["assets"]
            ):
                raise LookupError("report_asset_not_found")
            # Read only the saved, owner-scoped report facts; bound the context
            # size without substituting today's scores for a historical report.
            snapshot = {**snapshot, "assets": (
                [item for item in snapshot["assets"] if isinstance(item, dict)
                 and str(item.get("symbol") or "").upper() == asset.upper()]
                if requested_date and asset else snapshot["assets"][:30]
            )}
        report_assets = snapshot.get("assets") if snapshot else None
        report_symbol = None if not isinstance(report_assets, list) else (
            report_assets[0].get("symbol") if len(report_assets) == 1
            and isinstance(report_assets[0], dict) else None
        )
        best_setup = row.get("best_setup")
        top_setups = row.get("top_setups")
        if isinstance(best_setup, str):
            try:
                best_setup = json.loads(best_setup)
            except ValueError:
                best_setup = None
        if isinstance(top_setups, str):
            try:
                top_setups = json.loads(top_setups)
            except ValueError:
                top_setups = None
        payload = LatestReportData(
            report_type=table_name,
            report_date=row.get("report_date"),
            symbol=report_symbol,
            status=row.get("status"),
            id=row.get("id"),
            generated_at=display_source_moment(row.get("generated_at")),
            generated_at_amsterdam=amsterdam_source_moment(row.get("generated_at")),
            market_score=row.get("market_score"),
            macro_score=row.get("macro_score"),
            technical_score=row.get("technical_score"),
            setup_score=row.get("setup_score"),
            score_source_snapshot=snapshot,
            best_setup=best_setup if isinstance(best_setup, dict) else None,
            top_setups=[item for item in top_setups[:20] if isinstance(item, dict)]
            if isinstance(top_setups, list) else [],
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
