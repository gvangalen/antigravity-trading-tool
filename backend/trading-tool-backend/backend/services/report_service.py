import logging
import io
import asyncio
import os
import time
from typing import Dict, Any, List, Optional
from copy import deepcopy
from datetime import datetime
from fastapi.responses import StreamingResponse

from backend.infrastructure.repositories.report_repository import ReportRepository
from backend.infrastructure.repositories.user_repository import UserRepository
from backend.services.locale_service import localize_report_payload, resolve_locale
from backend.utils.pdf_playwright import render_report_pdf_via_playwright
from backend.ai_agents.report_ai_agent import generate_daily_report_sections
from backend.celery_task.daily_report_task import generate_daily_report
from backend.celery_task.weekly_report_task import generate_weekly_report
from backend.celery_task.monthly_report_task import generate_monthly_report
from backend.celery_task.quarterly_report_task import generate_quarterly_report
from backend.services.ai_usage_observability_service import ai_usage_context, get_user_email_snapshot

logger = logging.getLogger(__name__)

DAILY_REPORT_PREVIEW_CACHE_TTL_SECONDS = int(os.getenv("DAILY_REPORT_PREVIEW_CACHE_TTL_SECONDS", "30"))
DAILY_REPORT_REGEN_COOLDOWN_SECONDS = int(os.getenv("DAILY_REPORT_REGEN_COOLDOWN_SECONDS", "1800"))
_daily_report_preview_cache: Dict[int, Dict[str, Any]] = {}

from backend.services.intelligence_semantics import get_macro_semantics, get_technical_semantics, get_market_semantics

def _get_structure_label(score: Optional[float], category: str) -> str:
    if category == "macro":
        res = get_macro_semantics(score)
        return f"{res['regime']} · Conviction {res['conviction']}%"
    elif category == "technical":
        res = get_technical_semantics(score)
        return f"{res['structure']} · Conviction {res['conviction']}%"
    elif category == "market":
        res = get_market_semantics(score)
        return f"{res['posture']} · Conviction {res['conviction']}%"
    else: # setup
        val = 0.0 if score is None else float(score)
        if val >= 70: return f"Premium Alignment · Conviction {int(val)}%"
        if val >= 50: return f"Standard Setup · Conviction {int(val)}%"
        return f"Sub-optimal Alignment · Conviction {int(val)}%"

class ReportService:
    def __init__(self, repository: ReportRepository):
        self.repository = repository

    @staticmethod
    def _get_cached_daily_preview(user_id: int) -> Optional[Dict[str, Any]]:
        cached = _daily_report_preview_cache.get(int(user_id))
        if not cached:
            return None
        if float(cached.get("expires_at") or 0) <= time.time():
            _daily_report_preview_cache.pop(int(user_id), None)
            return None
        return deepcopy(cached.get("response"))

    @staticmethod
    def _store_cached_daily_preview(user_id: int, response: Dict[str, Any]) -> None:
        _daily_report_preview_cache[int(user_id)] = {
            "expires_at": time.time() + max(1, DAILY_REPORT_PREVIEW_CACHE_TTL_SECONDS),
            "response": deepcopy(response),
        }
        
    def _parse_date(self, date_str: str):
        try:
            return datetime.strptime(date_str, "%Y-%m-%d").date()
        except ValueError:
            raise ValueError("Invalid date")

    async def _get_user_locale(self, user_id: int) -> str:
        user = await UserRepository(self.repository.db).get_by_id(user_id)
        preferences = getattr(user, "ai_preferences", {}) or {} if user else {}
        return resolve_locale(preferences)

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
            exec_summary = safe_json_parse(meta.get("executive_summary") or report.get("executive_summary") or report.get("summary") or "Status ok.")
            market_analysis = safe_json_parse(meta.get("market_analysis") or meta.get("market_overview") or report.get("market_overview") or "")
            outlook = safe_json_parse(meta.get("outlook") or report.get("outlook") or "")
            
            macro_sc = meta.get("macro_score") or report.get("macro_score")
            tech_sc = meta.get("technical_score") or report.get("technical_score")
            mkt_sc = meta.get("market_score") or report.get("market_score")
            stp_sc = meta.get("setup_score") or report.get("setup_score")
            
            kpi_metrics = {
                "macro_score": macro_sc,
                "macro_label": _get_structure_label(macro_sc, "macro"),
                "technical_score": tech_sc,
                "technical_label": _get_structure_label(tech_sc, "technical"),
                "market_score": mkt_sc,
                "market_label": _get_structure_label(mkt_sc, "market"),
                "setup_score": stp_sc,
                "setup_label": _get_structure_label(stp_sc, "setup"),
                "price": meta.get("price") or report.get("price"),
                "change_24h": meta.get("change_24h") or report.get("change_24h"),
                "volume": meta.get("volume") or report.get("volume"),
            }
            
            watchlist = safe_json_parse(meta.get("watchlist") or report.get("watchlist") or [])
            best_setup = safe_json_parse(meta.get("best_setup") or report.get("best_setup"))
            top_setups = safe_json_parse(meta.get("top_setups") or report.get("top_setups") or [])
            bot_snapshot = safe_json_parse(meta.get("bot_snapshot") or report.get("bot_snapshot"))
            active_strategy = safe_json_parse(meta.get("active_strategy") or report.get("active_strategy"))
            
            market_ind = safe_json_parse(meta.get("market_indicator_highlights") or report.get("market_indicator_highlights") or [])
            macro_ind = safe_json_parse(meta.get("macro_indicator_highlights") or report.get("macro_indicator_highlights") or [])
            tech_ind = safe_json_parse(meta.get("technical_indicator_highlights") or report.get("technical_indicator_highlights") or [])
        else:
            exec_summary = safe_json_parse(report.get("executive_summary") or report.get("summary") or "Status ok.")
            market_analysis = safe_json_parse(report.get("market_analysis") or report.get("market_overview") or "")
            outlook = safe_json_parse(report.get("outlook") or "")
            
            macro_sc = report.get("macro_score")
            tech_sc = report.get("technical_score")
            mkt_sc = report.get("market_score")
            stp_sc = report.get("setup_score")
            
            kpi_metrics = {
                "macro_score": macro_sc,
                "macro_label": _get_structure_label(macro_sc, "macro"),
                "technical_score": tech_sc,
                "technical_label": _get_structure_label(tech_sc, "technical"),
                "market_score": mkt_sc,
                "market_label": _get_structure_label(mkt_sc, "market"),
                "setup_score": stp_sc,
                "setup_label": _get_structure_label(stp_sc, "setup"),
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

    def _normalize_daily_preview_from_existing_report(self, report: Dict[str, Any]) -> Dict[str, Any]:
        if not report:
            return {}

        import json

        def safe_json_parse(val):
            if isinstance(val, str):
                try:
                    return json.loads(val)
                except Exception:
                    return val
            return val

        meta = safe_json_parse(report.get("meta_json")) if report.get("meta_json") else {}
        meta = meta if isinstance(meta, dict) else {}

        def first_value(*candidates):
            for value in candidates:
                if value not in (None, ""):
                    return value
            return None

        preview = {
            "executive_summary": first_value(meta.get("executive_summary"), report.get("executive_summary"), report.get("summary")),
            "market_analysis": first_value(meta.get("market_analysis"), meta.get("market_overview"), report.get("market_analysis"), report.get("market_overview")),
            "macro_context": first_value(meta.get("macro_context"), report.get("macro_context"), report.get("macro_summary")),
            "technical_analysis": first_value(meta.get("technical_analysis"), report.get("technical_analysis"), report.get("technical_summary")),
            "setup_validation": first_value(meta.get("setup_validation"), report.get("setup_validation"), report.get("setup_summary")),
            "strategy_implication": first_value(meta.get("strategy_implication"), report.get("strategy_implication"), report.get("recommended_action")),
            "bot_strategy": first_value(meta.get("bot_strategy"), report.get("bot_strategy"), report.get("bot_summary")),
            "outlook": first_value(meta.get("outlook"), report.get("outlook")),
            "watchlist": safe_json_parse(first_value(meta.get("watchlist"), report.get("watchlist"), [])) or [],
            "best_setup": safe_json_parse(first_value(meta.get("best_setup"), report.get("best_setup"))),
            "transition": safe_json_parse(first_value(meta.get("transition"), report.get("transition"))),
            "price": first_value(meta.get("price"), report.get("price")),
            "change_24h": first_value(meta.get("change_24h"), report.get("change_24h")),
            "volume": first_value(meta.get("volume"), report.get("volume")),
            "macro_score": first_value(meta.get("macro_score"), report.get("macro_score")),
            "technical_score": first_value(meta.get("technical_score"), report.get("technical_score")),
            "market_score": first_value(meta.get("market_score"), report.get("market_score")),
            "setup_score": first_value(meta.get("setup_score"), report.get("setup_score")),
            "market_indicator_highlights": safe_json_parse(first_value(meta.get("market_indicator_highlights"), report.get("market_indicator_highlights"), [])) or [],
            "macro_indicator_highlights": safe_json_parse(first_value(meta.get("macro_indicator_highlights"), report.get("macro_indicator_highlights"), [])) or [],
            "technical_indicator_highlights": safe_json_parse(first_value(meta.get("technical_indicator_highlights"), report.get("technical_indicator_highlights"), [])) or [],
            "active_strategy": safe_json_parse(first_value(meta.get("active_strategy"), report.get("active_strategy"))),
            "bot_snapshot": safe_json_parse(first_value(meta.get("bot_snapshot"), report.get("bot_snapshot"))),
        }
        return {key: value for key, value in preview.items() if value is not None}

    async def get_latest_report(self, user_id: int, table_name: str, symbol: Optional[str] = None, format_type: Optional[str] = None) -> Dict[str, Any]:
        locale = await self._get_user_locale(user_id)
        row = await self.repository.get_latest_report(user_id, table_name, symbol=symbol)
        if not row:
            if table_name == "daily_reports":
                raise ValueError("Geen dagelijks rapport gevonden")
            else:
                return {"_status": "pending"}
                
        if table_name == "daily_reports":
            from backend.infrastructure.repositories.score_repository import ScoreRepository
            score_repo = ScoreRepository(self.repository.db)
            target_symbol = symbol or "BTC"
            daily_scores = await score_repo.fetch_daily_scores(user_id, symbol=target_symbol)
            if daily_scores:
                row["macro_score"] = daily_scores.get("macro_score", row.get("macro_score"))
                row["technical_score"] = daily_scores.get("technical_score", row.get("technical_score"))
                row["market_score"] = daily_scores.get("market_score", row.get("market_score"))
                row["setup_score"] = daily_scores.get("setup_score", row.get("setup_score"))

        # Format for mobile if requested
        if format_type == "mobile":
            return await localize_report_payload(self.format_report_for_mobile(row), locale)

        if table_name != "daily_reports":
            return await localize_report_payload({"_status": "ready", **row}, locale)
        return await localize_report_payload(row, locale)

    async def get_report_by_date(self, user_id: int, table_name: str, date_str: str, format_type: Optional[str] = None) -> Dict[str, Any]:
        locale = await self._get_user_locale(user_id)
        parsed_date = self._parse_date(date_str)
        row = await self.repository.get_report_by_date(user_id, table_name, parsed_date)
        if not row:
            raise ValueError(f"Report niet gevonden voor {date_str}")

        if table_name == "daily_reports":
            from backend.infrastructure.repositories.score_repository import ScoreRepository
            score_repo = ScoreRepository(self.repository.db)
            daily_scores = await score_repo.fetch_daily_scores(user_id, symbol="BTC")
            if daily_scores:
                row["macro_score"] = daily_scores.get("macro_score", row.get("macro_score"))
                row["technical_score"] = daily_scores.get("technical_score", row.get("technical_score"))
                row["market_score"] = daily_scores.get("market_score", row.get("market_score"))
                row["setup_score"] = daily_scores.get("setup_score", row.get("setup_score"))

        # Format for mobile if requested
        if format_type == "mobile":
            return await localize_report_payload(self.format_report_for_mobile(row), locale)

        return await localize_report_payload(row, locale)

    async def get_report_history(self, user_id: int, table_name: str) -> List[str]:
        return await self.repository.get_report_history(user_id, table_name)

    # =================
    # GENERATION & PREVIEW
    # =================

    async def preview_daily_report(self, user_id: int) -> Dict[str, Any]:
        locale = await self._get_user_locale(user_id)
        cached = self._get_cached_daily_preview(user_id)
        if cached is not None:
            return await localize_report_payload(cached, locale)
        latest_report = None
        if hasattr(self.repository, "get_latest_report"):
            latest_report = await self.repository.get_latest_report(user_id, "daily_reports")
        latest_report_date = latest_report.get("report_date") if latest_report else None
        if latest_report and hasattr(latest_report_date, "isoformat") and latest_report_date == datetime.utcnow().date():
            response = {
                "status": "ok",
                "generated_at": datetime.utcnow().isoformat(),
                "user_id": user_id,
                "report": self._normalize_daily_preview_from_existing_report(latest_report),
                "source": "latest_daily_report",
            }
            self._store_cached_daily_preview(user_id, response)
            return await localize_report_payload(response, locale)
        try:
            with ai_usage_context(
                user_id=user_id,
                user_email=get_user_email_snapshot(user_id),
                purpose="daily_report_preview",
                run_kind="interactive",
                entry_point="report_service_preview",
                symbol="WATCHLIST",
            ):
                report = await asyncio.to_thread(generate_daily_report_sections, user_id=user_id)
        except TypeError:
            with ai_usage_context(
                user_id=user_id,
                user_email=get_user_email_snapshot(user_id),
                purpose="daily_report_preview",
                run_kind="interactive",
                entry_point="report_service_preview",
                symbol="WATCHLIST",
            ):
                report = await asyncio.to_thread(generate_daily_report_sections)

        response = {
            "status": "ok",
            "generated_at": datetime.utcnow().isoformat(),
            "user_id": user_id,
            "report": report,
            "source": "generated_preview",
        }
        self._store_cached_daily_preview(user_id, response)
        return await localize_report_payload(response, locale)

    async def generate_report(self, user_id: int, period: str) -> Dict[str, Any]:
        if period == "daily" and hasattr(self.repository, "get_latest_report"):
            latest_report = await self.repository.get_latest_report(user_id, "daily_reports")
            latest_report_date = latest_report.get("report_date") if latest_report else None
            generated_at = latest_report.get("generated_at") if latest_report else None
            if (
                latest_report
                and latest_report_date == datetime.utcnow().date()
                and isinstance(generated_at, datetime)
            ):
                age_seconds = int((datetime.utcnow() - generated_at.replace(tzinfo=None)).total_seconds())
                if age_seconds < max(60, DAILY_REPORT_REGEN_COOLDOWN_SECONDS):
                    return {
                        "message": "Dagrapport al recent gegenereerd; bestaand rapport wordt hergebruikt.",
                        "task_id": None,
                        "user_id": user_id,
                        "source": "existing_daily_report",
                        "report_age_seconds": age_seconds,
                    }

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
