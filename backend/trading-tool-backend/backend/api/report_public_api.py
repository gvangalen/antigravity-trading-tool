from fastapi import APIRouter, HTTPException, Query, Depends
import logging
from sqlalchemy.ext.asyncio import AsyncSession

from backend.infrastructure.database import get_db
from backend.infrastructure.repositories.report_repository import ReportRepository
from backend.services.report_service import ReportService

router = APIRouter()
logger = logging.getLogger(__name__)

def get_report_service(db: AsyncSession = Depends(get_db)):
    repo = ReportRepository(db)
    return ReportService(repo)

@router.get("/public/report")
async def get_public_report(
    token: str = Query(...),
    service: ReportService = Depends(get_report_service)
):
    """
    Public endpoint voor print & share.
    Wordt gebruikt door:
    - Playwright PDF rendering
    - Print view
    - Public sharing links
    """
    logger.info("🔓 Public report request | token=%s", token[:12])
    
    try:
        return await service.get_public_report(token)
    except KeyError:
        logger.warning("❌ Snapshot not found")
        raise HTTPException(status_code=404, detail="Snapshot not found")
    except PermissionError as e:
        logger.warning(f"⛔ Snapshot link issue: {e}")
        if str(e) == "Link expired":
            raise HTTPException(status_code=410, detail="Link expired")
        elif str(e) == "Report not ready":
            raise HTTPException(status_code=425, detail="Report not ready")
        raise HTTPException(status_code=403, detail=str(e))
    except ValueError as e:
        logger.warning("⏳ Snapshot not ready yet")
        raise HTTPException(status_code=425, detail="Report not ready")
    except Exception as e:
        logger.exception("❌ Public report crash")
        raise HTTPException(status_code=500, detail="Server error")
