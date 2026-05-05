import logging
import io
import asyncio
from typing import Dict, Any, List, Optional
from datetime import datetime
from fastapi.responses import StreamingResponse

from backend.infrastructure.repositories.report_repository import ReportRepository
from backend.utils.pdf_playwright import render_report_pdf_via_playwright
from backend.ai_agents.report_ai_agent import generate_daily_report_sections
from backend.celery_task.daily_report_task import generate_daily_report
from backend.celery_task.weekly_report_task import generate_weekly_report
from backend.celery_task.monthly_report_task import generate_monthly_report
from backend.celery_task.quarterly_report_task import generate_quarterly_report

logger = logging.getLogger(__name__)

class ReportService:
    def __init__(self, repository: ReportRepository):
        self.repository = repository
        
    def _parse_date(self, date_str: str):
        try:
            return datetime.strptime(date_str, "%Y-%m-%d").date()
        except ValueError:
            raise ValueError("Invalid date")

    # =================
    # FETCH REPORTS
    # =================

    async def get_latest_report(self, user_id: int, table_name: str, symbol: Optional[str] = None) -> Dict[str, Any]:
        row = await self.repository.get_latest_report(user_id, table_name, symbol=symbol)
        if not row:
            if table_name == "daily_reports":
                raise ValueError("Geen dagelijks rapport gevonden")
            else:
                return {"_status": "pending"}
                
        if table_name != "daily_reports":
            return {"_status": "ready", **row}
        return row

    async def get_report_by_date(self, user_id: int, table_name: str, date_str: str) -> Dict[str, Any]:
        parsed_date = self._parse_date(date_str)
        row = await self.repository.get_report_by_date(user_id, table_name, parsed_date)
        if not row:
            raise ValueError(f"Report niet gevonden voor {date_str}")
        return row

    async def get_report_history(self, user_id: int, table_name: str) -> List[str]:
        return await self.repository.get_report_history(user_id, table_name)

    # =================
    # GENERATION & PREVIEW
    # =================

    async def preview_daily_report(self, user_id: int) -> Dict[str, Any]:
        try:
            report = await asyncio.to_thread(generate_daily_report_sections, user_id=user_id)
        except TypeError:
            report = await asyncio.to_thread(generate_daily_report_sections)
            
        return {
            "status": "ok",
            "generated_at": datetime.utcnow().isoformat(),
            "user_id": user_id,
            "report": report,
        }

    async def generate_report(self, user_id: int, period: str) -> Dict[str, Any]:
        task_func = {
            "daily": generate_daily_report,
            "weekly": generate_weekly_report,
            "monthly": generate_monthly_report,
            "quarterly": generate_quarterly_report
        }.get(period)
        
        if not task_func:
            raise ValueError("Ongeldige periode")
            
        try:
            task = task_func.delay(user_id=user_id)
        except TypeError:
            task = task_func.delay()

        names = {
            "daily": "Daily report taak gestart",
            "weekly": "Weekrapport taak gestart",
            "monthly": "Maandrapport taak gestart",
            "quarterly": "Kwartaalrapport taak gestart"
        }

        return {
            "message": names[period],
            "task_id": task.id,
            "user_id": user_id,
        }

    # =================
    # EXPORT PDF
    # =================
    async def export_pdf(self, user_id: int, table_name: str, report_type: str, date_str: str):
        parsed_date = self._parse_date(date_str)
        row = await self.repository.get_report_by_date(user_id, table_name, parsed_date)
        
        if not row:
            raise ValueError("Report niet gevonden")

        # 📸 Create a temporary snapshot for the PDF renderer
        # Note: some tables (like daily_reports) use report_date as PK instead of 'id'.
        report_id = row.get("id")
        if report_id is None:
            # Derive an integer ID from the date (YYYYMMDD)
            rd = row.get("report_date")
            if hasattr(rd, 'strftime'):
                report_id = int(rd.strftime("%Y%m%d"))
            else:
                report_id = 0 # Fallback

        token = await self.repository.create_report_snapshot(
            user_id, 
            report_type, 
            report_id, 
            row
        )

        # 🧾 Render via Playwright
        pdf_bytes = await render_report_pdf_via_playwright(token=token)

        filename = f"{report_type}_report_{date_str}.pdf"

        return StreamingResponse(
            io.BytesIO(pdf_bytes),
            media_type="application/pdf",
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"'
            },
        )

    # =================
    # PUBLIC REPORT
    # =================
    async def get_public_report(self, token: str) -> Dict[str, Any]:
        snapshot = await self.repository.get_public_snapshot(token)
        if not snapshot:
            raise KeyError("Snapshot not found")
            
        valid_until = snapshot.get("valid_until")
        status = snapshot.get("status")
        report_json = snapshot.get("report_json")
        
        # Parse datetime if it was returned as string, though SQLAlchemy returns datetime via dict
        if valid_until:
            if isinstance(valid_until, datetime):
                # Ensure it's offset-naive matching utcnow
                vd = valid_until.replace(tzinfo=None)
                if vd < datetime.utcnow():
                    raise PermissionError("Link expired")
            else:
                pass # Unlikely with SQLAlchemy

        if status != "ready":
             raise ValueError("Report not ready")

        return report_json
