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

    def format_report_for_mobile(self, report: Dict[str, Any]) -> Dict[str, Any]:
        """
        Formats and compresses a report payload to offer ultra-fast, clean,
        easily parsable metrics, summaries, and indicator highlights for native mobile screens.
        """
        if not report:
            return {}

        import json

        # Safe parsing helper
        def safe_json_parse(val):
            if isinstance(val, str):
                try:
                    return json.loads(val)
                except Exception:
                    return val
            return val

        # If it's a non-daily report and has meta_json, unpack it
        meta_json_raw = report.get("meta_json")
        meta = safe_json_parse(meta_json_raw) if meta_json_raw else None

        # Build composite highlights/narratives
        if meta and isinstance(meta, dict):
            # For weekly/monthly/quarterly, unpack sections from meta
            exec_summary = safe_json_parse(meta.get("executive_summary") or report.get("executive_summary") or report.get("summary") or "Status ok.")
            market_analysis = safe_json_parse(meta.get("market_analysis") or meta.get("market_overview") or report.get("market_overview") or "")
            outlook = safe_json_parse(meta.get("outlook") or report.get("outlook") or "")
            
            kpi_metrics = {
                "macro_score": meta.get("macro_score") or report.get("macro_score"),
                "technical_score": meta.get("technical_score") or report.get("technical_score"),
                "market_score": meta.get("market_score") or report.get("market_score"),
                "setup_score": meta.get("setup_score") or report.get("setup_score"),
                "price": meta.get("price") or report.get("price"),
                "change_24h": meta.get("change_24h") or report.get("change_24h"),
                "volume": meta.get("volume") or report.get("volume"),
            }
            
            # Watchlist
            watchlist = safe_json_parse(meta.get("watchlist") or report.get("watchlist") or [])
            best_setup = safe_json_parse(meta.get("best_setup") or report.get("best_setup"))
            top_setups = safe_json_parse(meta.get("top_setups") or report.get("top_setups") or [])
            bot_snapshot = safe_json_parse(meta.get("bot_snapshot") or report.get("bot_snapshot"))
            active_strategy = safe_json_parse(meta.get("active_strategy") or report.get("active_strategy"))
            
            # Highlights
            market_ind = safe_json_parse(meta.get("market_indicator_highlights") or report.get("market_indicator_highlights") or [])
            macro_ind = safe_json_parse(meta.get("macro_indicator_highlights") or report.get("macro_indicator_highlights") or [])
            tech_ind = safe_json_parse(meta.get("technical_indicator_highlights") or report.get("technical_indicator_highlights") or [])
        else:
            # Daily report format
            exec_summary = safe_json_parse(report.get("executive_summary") or report.get("summary") or "Status ok.")
            market_analysis = safe_json_parse(report.get("market_analysis") or report.get("market_overview") or "")
            outlook = safe_json_parse(report.get("outlook") or "")
            
            kpi_metrics = {
                "macro_score": report.get("macro_score"),
                "technical_score": report.get("technical_score"),
                "market_score": report.get("market_score"),
                "setup_score": report.get("setup_score"),
                "price": report.get("price"),
                "change_24h": report.get("change_24h"),
                "volume": report.get("volume"),
            }
            
            watchlist = safe_json_parse(report.get("watchlist") or [])
            best_setup = safe_json_parse(report.get("best_setup"))
            top_setups = safe_json_parse(report.get("top_setups") or [])
            bot_snapshot = safe_json_parse(report.get("bot_snapshot"))
            active_strategy = safe_json_parse(report.get("active_strategy"))
            
            market_ind = safe_json_parse(report.get("market_indicator_highlights") or [])
            macro_ind = safe_json_parse(report.get("macro_indicator_highlights") or [])
            tech_ind = safe_json_parse(report.get("technical_indicator_highlights") or [])

        # Normalize indicator highlights to a single list
        highlights = []
        if isinstance(market_ind, list):
            for item in market_ind:
                if isinstance(item, dict):
                    highlights.append({
                        "category": "market",
                        "name": item.get("indicator") or item.get("name"),
                        "value": item.get("value"),
                        "score": item.get("score"),
                        "interpretation": item.get("interpretation") or item.get("explanation"),
                    })
        if isinstance(macro_ind, list):
            for item in macro_ind:
                if isinstance(item, dict):
                    highlights.append({
                        "category": "macro",
                        "name": item.get("indicator") or item.get("name"),
                        "value": item.get("value"),
                        "score": item.get("score"),
                        "interpretation": item.get("interpretation") or item.get("explanation"),
                    })
        if isinstance(tech_ind, list):
            for item in tech_ind:
                if isinstance(item, dict):
                    highlights.append({
                        "category": "technical",
                        "name": item.get("indicator") or item.get("name"),
                        "value": item.get("value"),
                        "score": item.get("score"),
                        "interpretation": item.get("interpretation") or item.get("explanation"),
                    })

        # Dates & keys formatting
        rdate = report.get("report_date")
        if hasattr(rdate, 'isoformat'):
            rdate = rdate.isoformat()

        p_start = report.get("period_start")
        if hasattr(p_start, 'isoformat'):
            p_start = p_start.isoformat()

        p_end = report.get("period_end")
        if hasattr(p_end, 'isoformat'):
            p_end = p_end.isoformat()

        return {
            "report_date": rdate,
            "period_start": p_start,
            "period_end": p_end,
            "generated_at": report.get("generated_at"),
            "executive_summary_compact": exec_summary,
            "market_analysis_compact": market_analysis,
            "outlook_compact": outlook,
            "kpi_metrics": kpi_metrics,
            "highlights": highlights,
            "best_setup": best_setup,
            "top_setups": top_setups,
            "bot_snapshot": bot_snapshot,
            "active_strategy": active_strategy,
            "watchlist": watchlist,
        }

    async def get_latest_report(self, user_id: int, table_name: str, symbol: Optional[str] = None, format_type: Optional[str] = None) -> Dict[str, Any]:
        row = await self.repository.get_latest_report(user_id, table_name, symbol=symbol)
        if not row:
            if table_name == "daily_reports":
                raise ValueError("Geen dagelijks rapport gevonden")
            else:
                return {"_status": "pending"}
                
        if table_name == "daily_reports":
            import json
            from backend.infrastructure.repositories.score_repository import ScoreRepository
            score_repo = ScoreRepository(self.repository.db)
            target_symbol = symbol or "BTC"
            master = await score_repo.get_master_score(user_id, symbol=target_symbol)
            if master and master.top_signals:
                meta = master.top_signals
                if isinstance(meta, str):
                    try: meta = json.loads(meta)
                    except: meta = {}
                domains = meta.get("domains", {})
                if domains:
                    if "macro" in domains: row["macro_score"] = domains["macro"].get("score", row.get("macro_score"))
                    if "technical" in domains: row["technical_score"] = domains["technical"].get("score", row.get("technical_score"))
                    if "market" in domains: row["market_score"] = domains["market"].get("score", row.get("market_score"))
                    if "setup" in domains: row["setup_score"] = domains["setup"].get("score", row.get("setup_score"))

        # Format for mobile if requested
        if format_type == "mobile":
            return self.format_report_for_mobile(row)

        if table_name != "daily_reports":
            return {"_status": "ready", **row}
        return row

    async def get_report_by_date(self, user_id: int, table_name: str, date_str: str, format_type: Optional[str] = None) -> Dict[str, Any]:
        parsed_date = self._parse_date(date_str)
        row = await self.repository.get_report_by_date(user_id, table_name, parsed_date)
        if not row:
            raise ValueError(f"Report niet gevonden voor {date_str}")

        if table_name == "daily_reports":
            import json
            from backend.infrastructure.repositories.score_repository import ScoreRepository
            score_repo = ScoreRepository(self.repository.db)
            master = await score_repo.get_master_score(user_id, symbol="BTC")
            if master and master.top_signals:
                meta = master.top_signals
                if isinstance(meta, str):
                    try: meta = json.loads(meta)
                    except: meta = {}
                domains = meta.get("domains", {})
                if domains:
                    if "macro" in domains: row["macro_score"] = domains["macro"].get("score", row.get("macro_score"))
                    if "technical" in domains: row["technical_score"] = domains["technical"].get("score", row.get("technical_score"))
                    if "market" in domains: row["market_score"] = domains["market"].get("score", row.get("market_score"))
                    if "setup" in domains: row["setup_score"] = domains["setup"].get("score", row.get("setup_score"))

        # Format for mobile if requested
        if format_type == "mobile":
            return self.format_report_for_mobile(row)

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
