import logging
from typing import Optional
from celery.result import AsyncResult
from fastapi import APIRouter, HTTPException, Query, Depends, Header
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from backend.infrastructure.database import get_db
from backend.utils.auth_utils import get_current_user, decode_token
from backend.celery_task.celery_app import celery_app
from backend.infrastructure.repositories.report_repository import ReportRepository
from backend.services.report_service import ReportService
from backend.services.daily_report_trader_status_service import current_daily_trader_status

router = APIRouter()
logger = logging.getLogger(__name__)


class ReportGenerationStatusRequest(BaseModel):
    status_token: str

async def get_report_service(
    db: AsyncSession = Depends(get_db),
    request_locale: Optional[str] = Header(None, alias="X-Locale"),
):
    repo = ReportRepository(db)
    return ReportService(repo, request_locale=request_locale)


def _report_value_error(exc: ValueError) -> HTTPException:
    message = str(exc).lower()
    if "gevonden" in message:
        return HTTPException(status_code=404, detail="Rapport niet gevonden.")
    return HTTPException(status_code=400, detail="Ongeldige rapportaanvraag.")


def _report_internal_error(message: str = "Rapportverwerking mislukt.") -> HTTPException:
    return HTTPException(status_code=500, detail=message)

# ======================================================
# 🟢 DAILY REPORTS
# ======================================================
@router.get("/report/daily/trader-status")
async def get_daily_trader_status(
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Current owner-bound state, deliberately separate from the dated report."""
    return await current_daily_trader_status(db, current_user["id"])

@router.get("/report/daily/latest")
async def get_daily_latest(
    symbol: str = Query("BTC"),
    format: Optional[str] = Query(None),
    current_user: dict = Depends(get_current_user),
    service: ReportService = Depends(get_report_service)
):
    try:
        return await service.get_latest_report(current_user["id"], "daily_reports", symbol=symbol, format_type=format)
    except ValueError as e:
        raise _report_value_error(e)

@router.get("/report/daily/by-date")
async def get_daily_by_date(
    date: str = Query(...),
    format: Optional[str] = Query(None),
    current_user: dict = Depends(get_current_user),
    service: ReportService = Depends(get_report_service)
):
    try:
        return await service.get_report_by_date(current_user["id"], "daily_reports", date, format_type=format)
    except ValueError as e:
        raise _report_value_error(e)

@router.get("/report/daily/history")
async def get_daily_report_history(
    current_user: dict = Depends(get_current_user),
    service: ReportService = Depends(get_report_service)
):
    return await service.get_report_history(current_user["id"], "daily_reports")

@router.post("/report/daily/preview")
async def preview_daily_report(
    current_user: dict = Depends(get_current_user),
    service: ReportService = Depends(get_report_service)
):
    try:
        return await service.preview_daily_report(current_user["id"])
    except Exception as e:
        logger.error("❌ preview_daily_report failed: %s", e, exc_info=True)
        raise _report_internal_error()

@router.post("/report/daily/generate")
async def generate_daily(
    current_user: dict = Depends(get_current_user),
    service: ReportService = Depends(get_report_service)
):
    try:
        return await service.generate_report(current_user["id"], "daily", manual_refresh=True)
    except Exception as e:
        logger.error("❌ generate_daily failed: %s", e, exc_info=True)
        raise _report_internal_error()


@router.post("/report/daily/generation-status")
async def get_daily_generation_status(
    request: ReportGenerationStatusRequest,
    current_user: dict = Depends(get_current_user),
):
    """Owner-bound task status; never expose raw Celery errors or task results."""
    try:
        claims = decode_token(request.status_token)
    except ValueError:
        raise HTTPException(status_code=404, detail="Rapporttaak niet gevonden.")
    if (
        claims.get("type") != "report_generation"
        or claims.get("period") != "daily"
        or claims.get("sub") != str(current_user["id"])
        or not isinstance(claims.get("task_id"), str)
    ):
        raise HTTPException(status_code=404, detail="Rapporttaak niet gevonden.")

    result = AsyncResult(claims["task_id"], app=celery_app)
    state = result.state
    response = {"state": state}
    if state == "FAILURE":
        response["error_code"] = (
            "ai_rate_limited"
            if "daily_report_ai_rate_limited" in str(result.result)
            else "generation_failed"
        )
    elif state == "REVOKED":
        response["error_code"] = "generation_failed"
    return response

@router.get("/report/daily/export/pdf")
async def export_daily_pdf(
    date: str = Query(...),
    current_user: dict = Depends(get_current_user),
    service: ReportService = Depends(get_report_service)
):
    try:
        return await service.export_pdf(current_user["id"], "daily_reports", "daily", date)
    except ValueError as e:
        raise _report_value_error(e)


# ======================================================
# 📆 WEEKLY REPORTS
# ======================================================
@router.get("/report/weekly/latest")
async def get_weekly_latest(
    format: Optional[str] = Query(None),
    current_user: dict = Depends(get_current_user),
    service: ReportService = Depends(get_report_service)
):
    try:
        return await service.get_latest_report(current_user["id"], "weekly_reports", format_type=format)
    except Exception as e:
        logger.error("❌ get_weekly_latest failed: %s", e, exc_info=True)
        raise _report_internal_error()

@router.get("/report/weekly/by-date")
async def get_weekly_by_date(
    date: str = Query(...),
    format: Optional[str] = Query(None),
    current_user: dict = Depends(get_current_user),
    service: ReportService = Depends(get_report_service)
):
    try:
        return await service.get_report_by_date(current_user["id"], "weekly_reports", date, format_type=format)
    except ValueError as e:
        raise _report_value_error(e)

@router.get("/report/weekly/history")
async def get_weekly_report_history(
    current_user: dict = Depends(get_current_user),
    service: ReportService = Depends(get_report_service)
):
    return await service.get_report_history(current_user["id"], "weekly_reports")

@router.post("/report/weekly/generate")
async def generate_weekly(
    current_user: dict = Depends(get_current_user),
    service: ReportService = Depends(get_report_service)
):
    try:
        return await service.generate_report(current_user["id"], "weekly")
    except Exception as e:
        logger.error("❌ generate_weekly failed: %s", e, exc_info=True)
        raise _report_internal_error()

@router.get("/report/weekly/export/pdf")
async def export_weekly_pdf(
    date: str = Query(...),
    current_user: dict = Depends(get_current_user),
    service: ReportService = Depends(get_report_service)
):
    try:
        return await service.export_pdf(current_user["id"], "weekly_reports", "weekly", date)
    except ValueError as e:
        raise _report_value_error(e)


# ======================================================
# 📅 MONTHLY REPORTS
# ======================================================
@router.get("/report/monthly/latest")
async def get_monthly_latest(
    format: Optional[str] = Query(None),
    current_user: dict = Depends(get_current_user),
    service: ReportService = Depends(get_report_service)
):
    try:
        return await service.get_latest_report(current_user["id"], "monthly_reports", format_type=format)
    except Exception as e:
        logger.error("❌ get_monthly_latest failed: %s", e, exc_info=True)
        raise _report_internal_error()

@router.get("/report/monthly/by-date")
async def get_monthly_by_date(
    date: str = Query(...),
    format: Optional[str] = Query(None),
    current_user: dict = Depends(get_current_user),
    service: ReportService = Depends(get_report_service)
):
    try:
        return await service.get_report_by_date(current_user["id"], "monthly_reports", date, format_type=format)
    except ValueError as e:
        raise _report_value_error(e)

@router.get("/report/monthly/history")
async def get_monthly_report_history(
    current_user: dict = Depends(get_current_user),
    service: ReportService = Depends(get_report_service)
):
    return await service.get_report_history(current_user["id"], "monthly_reports")

@router.post("/report/monthly/generate")
async def generate_monthly(
    current_user: dict = Depends(get_current_user),
    service: ReportService = Depends(get_report_service)
):
    try:
        return await service.generate_report(current_user["id"], "monthly")
    except Exception as e:
        logger.error("❌ generate_monthly failed: %s", e, exc_info=True)
        raise _report_internal_error()

@router.get("/report/monthly/export/pdf")
async def export_monthly_pdf(
    date: str = Query(...),
    current_user: dict = Depends(get_current_user),
    service: ReportService = Depends(get_report_service)
):
    try:
        return await service.export_pdf(current_user["id"], "monthly_reports", "monthly", date)
    except ValueError as e:
        raise _report_value_error(e)


# ======================================================
# 📊 QUARTERLY REPORTS
# ======================================================
@router.get("/report/quarterly/latest")
async def get_quarterly_latest(
    format: Optional[str] = Query(None),
    current_user: dict = Depends(get_current_user),
    service: ReportService = Depends(get_report_service)
):
    try:
        return await service.get_latest_report(current_user["id"], "quarterly_reports", format_type=format)
    except Exception as e:
        logger.error("❌ get_quarterly_latest failed: %s", e, exc_info=True)
        raise _report_internal_error()

@router.get("/report/quarterly/by-date")
async def get_quarterly_by_date(
    date: str = Query(...),
    format: Optional[str] = Query(None),
    current_user: dict = Depends(get_current_user),
    service: ReportService = Depends(get_report_service)
):
    try:
        return await service.get_report_by_date(current_user["id"], "quarterly_reports", date, format_type=format)
    except ValueError as e:
        raise _report_value_error(e)

@router.get("/report/quarterly/history")
async def get_quarterly_report_history(
    current_user: dict = Depends(get_current_user),
    service: ReportService = Depends(get_report_service)
):
    return await service.get_report_history(current_user["id"], "quarterly_reports")

@router.post("/report/quarterly/generate")
async def generate_quarterly(
    current_user: dict = Depends(get_current_user),
    service: ReportService = Depends(get_report_service)
):
    try:
        return await service.generate_report(current_user["id"], "quarterly")
    except Exception as e:
        logger.error("❌ generate_quarterly failed: %s", e, exc_info=True)
        raise _report_internal_error()

@router.get("/report/quarterly/export/pdf")
async def export_quarterly_pdf(
    date: str = Query(...),
    current_user: dict = Depends(get_current_user),
    service: ReportService = Depends(get_report_service)
):
    try:
        return await service.export_pdf(current_user["id"], "quarterly_reports", "quarterly", date)
    except ValueError as e:
        raise _report_value_error(e)
