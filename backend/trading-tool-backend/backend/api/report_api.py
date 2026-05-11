import logging
from typing import Optional
from fastapi import APIRouter, HTTPException, Query, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from backend.infrastructure.database import get_db
from backend.utils.auth_utils import get_current_user
from backend.infrastructure.repositories.report_repository import ReportRepository
from backend.services.report_service import ReportService

router = APIRouter()
logger = logging.getLogger(__name__)

async def get_report_service(db: AsyncSession = Depends(get_db)):
    repo = ReportRepository(db)
    return ReportService(repo)

# ======================================================
# 🟢 DAILY REPORTS
# ======================================================
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
        raise HTTPException(status_code=404, detail=str(e))

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
        raise HTTPException(status_code=404 if "gevonden" in str(e).lower() else 400, detail=str(e))

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
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/report/daily/generate")
async def generate_daily(
    current_user: dict = Depends(get_current_user),
    service: ReportService = Depends(get_report_service)
):
    try:
        return await service.generate_report(current_user["id"], "daily")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/report/daily/export/pdf")
async def export_daily_pdf(
    date: str = Query(...),
    current_user: dict = Depends(get_current_user),
    service: ReportService = Depends(get_report_service)
):
    try:
        return await service.export_pdf(current_user["id"], "daily_reports", "daily", date)
    except ValueError as e:
        raise HTTPException(status_code=404 if "gevonden" in str(e).lower() else 400, detail=str(e))


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
        raise HTTPException(status_code=500, detail=str(e))

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
        raise HTTPException(status_code=404 if "gevonden" in str(e).lower() else 400, detail=str(e))

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
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/report/weekly/export/pdf")
async def export_weekly_pdf(
    date: str = Query(...),
    current_user: dict = Depends(get_current_user),
    service: ReportService = Depends(get_report_service)
):
    try:
        return await service.export_pdf(current_user["id"], "weekly_reports", "weekly", date)
    except ValueError as e:
        raise HTTPException(status_code=404 if "gevonden" in str(e).lower() else 400, detail=str(e))


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
        raise HTTPException(status_code=500, detail=str(e))

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
        raise HTTPException(status_code=404 if "gevonden" in str(e).lower() else 400, detail=str(e))

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
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/report/monthly/export/pdf")
async def export_monthly_pdf(
    date: str = Query(...),
    current_user: dict = Depends(get_current_user),
    service: ReportService = Depends(get_report_service)
):
    try:
        return await service.export_pdf(current_user["id"], "monthly_reports", "monthly", date)
    except ValueError as e:
        raise HTTPException(status_code=404 if "gevonden" in str(e).lower() else 400, detail=str(e))


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
        raise HTTPException(status_code=500, detail=str(e))

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
        raise HTTPException(status_code=404 if "gevonden" in str(e).lower() else 400, detail=str(e))

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
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/report/quarterly/export/pdf")
async def export_quarterly_pdf(
    date: str = Query(...),
    current_user: dict = Depends(get_current_user),
    service: ReportService = Depends(get_report_service)
):
    try:
        return await service.export_pdf(current_user["id"], "quarterly_reports", "quarterly", date)
    except ValueError as e:
        raise HTTPException(status_code=404 if "gevonden" in str(e).lower() else 400, detail=str(e))

