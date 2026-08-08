import logging
from typing import List, Optional
from fastapi import APIRouter, HTTPException, Depends, Request, Query

from sqlalchemy.ext.asyncio import AsyncSession
from backend.infrastructure.database import get_db
from backend.utils.auth_utils import get_current_user

from backend.schemas.technical_data_schema import (
    TechnicalDataResponse,
    TechnicalIndicatorConfig,
    TechnicalIndicatorRuleResponse,
    TechnicalIndicatorHistoryResponse,
    TechnicalIndicatorPreferenceResponse,
    TechnicalIndicatorPreferenceUpdate,
    TechnicalIndicatorPreferenceItem,
)
from backend.services.technical_data_service import TechnicalDataService
from backend.infrastructure.repositories.technical_data_repository import TechnicalDataRepository

logger = logging.getLogger(__name__)

router = APIRouter()
logger.info("🚀 technical_data_api.py geladen — asynchrone Clean Architecture.")


# ===============================================================
# 📄 GET — ALLE TECHNISCHE DATA
# ===============================================================
@router.get("/technical_data", response_model=List[TechnicalDataResponse])
async def get_technical_data(
    symbol: Optional[str] = Query(None),
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_db)
):
    try:
        user_id = current_user["id"]
        repo = TechnicalDataRepository(session)
        rows = await repo.get_latest_for_user(user_id, symbol=symbol)
        return [
            TechnicalDataResponse(
                indicator=r.indicator,
                waarde=float(r.value) if r.value is not None else 0.0,
                score=float(r.score) if r.score is not None else 0.0,
                advies=r.advies or "–",
                uitleg=r.uitleg or "–",
                timestamp=r.timestamp
            )
            for r in rows
        ]
    except Exception as e:
        logger.error(f"❌ Technical API error (get_technical_data): {e}")
        return []


# ===============================================================
# ➕ POST — Technische indicator toevoegen (ONBOARDING)
# ===============================================================
@router.post("/technical_data")
async def add_technical_indicator(
    request: Request,
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_db)
):
    logger.info("📐 [add] Technische indicator toevoegen via Service...")
    data = await request.json()
    user_id = current_user["id"]
    name_raw = data.get("indicator")
    symbol = data.get("symbol") or "BTC"

    if not name_raw:
        raise HTTPException(400, "❌ 'indicator' is verplicht.")

    service = TechnicalDataService(session)
    try:
        # Dit voert validation, external call, duplicate checking en scoring uit
        result = await service.add_technical_indicator(name_raw, user_id, symbol=symbol)
        # Commit manually if auto-commit not configured in router middleware properly
        await session.commit()
        return result

    except ValueError as ve:
        # Expected business logic errors
        if "al toegevoegd" in str(ve):
            raise HTTPException(409, str(ve))
        elif "niet gevonden" in str(ve):
            raise HTTPException(404, str(ve))
        else:
            raise HTTPException(500, str(ve))
    except Exception as e:
        logger.error(f"❌ [add_technical_indicator] {e}", exc_info=True)
        await session.rollback()
        raise HTTPException(status_code=500, detail=f"Fout bij toevoegen indicator: {e}")


# ===============================================================
# 📅 DAY — fallback
# ===============================================================
@router.get("/technical_data/day", response_model=List[TechnicalDataResponse])
async def get_latest_day_data(
    symbol: str = "BTC",
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_db)
):
    try:
        user_id = current_user["id"]
        repo = TechnicalDataRepository(session)
        rows = await repo.get_day_data(user_id, symbol=symbol)
        
        return [
            TechnicalDataResponse(
                indicator=r.indicator,
                waarde=float(r.value) if r.value is not None else 0.0,
                score=float(r.score) if r.score is not None else 0.0,
                advies=r.advies or "–",
                uitleg=r.uitleg or "–",
                timestamp=r.timestamp
            )
            for r in rows
        ]
    except Exception as e:
        logger.error(f"❌ Technical API error (get_latest_day_data): {e}")
        return []


# ===============================================================
# WEEK / MONTH / QUARTER
# ===============================================================
@router.get("/technical_data/week", response_model=List[TechnicalDataResponse])
async def get_technical_week_data(
    symbol: str = "BTC",
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_db)
):
    try:
        user_id = current_user["id"]
        repo = TechnicalDataRepository(session)
        rows = await repo.get_week_data(user_id, symbol=symbol)
        return [
            TechnicalDataResponse(
                indicator=r.indicator,
                waarde=float(r.value) if r.value is not None else 0.0,
                score=float(r.score) if r.score is not None else 0.0,
                advies=r.advies or "–",
                uitleg=r.uitleg or "–",
                timestamp=r.timestamp
            )
            for r in rows
        ]
    except Exception as e:
        logger.error(f"❌ Technical API error (get_technical_week_data): {e}")
        return []


@router.get("/technical_data/month", response_model=List[TechnicalDataResponse])
async def get_technical_month_data(
    symbol: str = "BTC",
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_db)
):
    try:
        user_id = current_user["id"]
        repo = TechnicalDataRepository(session)
        rows = await repo.get_month_data(user_id, symbol=symbol)
        return [
            TechnicalDataResponse(
                indicator=r.indicator,
                waarde=float(r.value) if r.value is not None else 0.0,
                score=float(r.score) if r.score is not None else 0.0,
                advies=r.advies or "–",
                uitleg=r.uitleg or "–",
                timestamp=r.timestamp
            )
            for r in rows
        ]
    except Exception as e:
        logger.error(f"❌ Technical API error (get_technical_month_data): {e}")
        return []


@router.get("/technical_data/quarter", response_model=List[TechnicalDataResponse])
async def get_technical_quarter_data(
    symbol: str = "BTC",
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_db)
):
    try:
        user_id = current_user["id"]
        repo = TechnicalDataRepository(session)
        rows = await repo.get_quarter_data(user_id, symbol=symbol)
        return [
            TechnicalDataResponse(
                indicator=r.indicator,
                waarde=float(r.value) if r.value is not None else 0.0,
                score=float(r.score) if r.score is not None else 0.0,
                advies=r.advies or "–",
                uitleg=r.uitleg or "–",
                timestamp=r.timestamp
            )
            for r in rows
        ]
    except Exception as e:
        logger.error(f"❌ Technical API error (get_technical_quarter_data): {e}")
        return []


# ===============================================================
# DELETE
# ===============================================================
@router.delete("/technical_data/{indicator}")
async def delete_technical_indicator(
    indicator: str,
    symbol: Optional[str] = Query(None),
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_db)
):
    user_id = current_user["id"]
    service = TechnicalDataService(session)
    deleted = await service.delete_indicator(indicator, user_id, symbol=symbol)
    await session.commit()

    return {
        "message": f"Indicator '{indicator}' verwijderd.",
        "deleted_rows": deleted
    }


# ===============================================================
# DROPDOWN LIST
# ===============================================================
@router.get("/technical/indicators", response_model=List[TechnicalIndicatorConfig])
async def get_all_indicators(session: AsyncSession = Depends(get_db)):
    service = TechnicalDataService(session)
    return await service.get_all_indicators()


# ===============================================================
# SCORING RULES OPHALEN
# ===============================================================
@router.get("/technical_indicator_rules/{indicator_name}", response_model=List[TechnicalIndicatorRuleResponse])
async def get_rules_for_indicator(
    indicator_name: str,
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_db)
):
    user_id = current_user["id"]
    repo = TechnicalDataRepository(session)
    rows = await repo.get_rules_for_indicator(indicator_name, user_id)
    return rows

# ===============================================================
# 📈 HISTORY OPHALEN (Sparklines)
# ===============================================================
@router.get("/technical/history/{indicator_name}", response_model=List[TechnicalIndicatorHistoryResponse])
async def get_indicator_history(
    indicator_name: str,
    symbol: str = "BTC",
    limit: int = 30,
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_db)
):
    user_id = current_user["id"]
    repo = TechnicalDataRepository(session)
    rows = await repo.get_indicator_history(indicator_name, user_id, symbol=symbol, limit=limit)
    return [
        TechnicalIndicatorHistoryResponse(
            value=float(r.value),
            timestamp=r.timestamp
        )
        for r in rows
    ]


@router.get("/technical/preferences", response_model=TechnicalIndicatorPreferenceResponse)
async def get_technical_preferences(
    symbol: Optional[str] = Query(None),
    asset_class: Optional[str] = Query(None),
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    user_id = current_user["id"]
    service = TechnicalDataService(session)
    resolved = await service.resolve_effective_preferences(
        user_id,
        symbol=symbol,
        asset_class=asset_class,
    )

    return TechnicalIndicatorPreferenceResponse(
        scope=resolved["scope"],
        symbol=resolved["symbol"],
        asset_class=resolved["asset_class"],
        indicators=[
            TechnicalIndicatorPreferenceItem(
                indicator=row.indicator,
                priority=int(row.priority or 100),
            )
            for row in resolved["rows"]
        ],
    )


@router.put("/technical/preferences", response_model=TechnicalIndicatorPreferenceResponse)
async def put_technical_preferences(
    payload: TechnicalIndicatorPreferenceUpdate,
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    user_id = current_user["id"]
    repo = TechnicalDataRepository(session)

    normalized_symbol = str(payload.symbol or "").strip().upper() or None
    asset_class = str(payload.asset_class or "").strip().lower() or None
    if normalized_symbol and not asset_class:
        asset = await AssetCatalogService(session).get_asset(normalized_symbol)
        asset_class = asset.get("asset_class")

    normalized_items = []
    for item in payload.indicators:
        indicator = str(item.indicator or "").strip().lower()
        if not indicator:
            continue
        normalized_items.append((indicator, int(item.priority or 100)))

    await repo.replace_scope_configs(
        user_id,
        normalized_items,
        symbol=normalized_symbol,
        asset_class=asset_class,
    )
    await session.commit()

    rows = await repo.list_scope_configs(
        user_id,
        symbol=normalized_symbol,
        asset_class=asset_class,
    )
    return TechnicalIndicatorPreferenceResponse(
        scope="symbol_override" if normalized_symbol else ("asset_class_override" if asset_class else "default"),
        symbol=normalized_symbol,
        asset_class=asset_class,
        indicators=[
            TechnicalIndicatorPreferenceItem(
                indicator=row.indicator,
                priority=int(row.priority or 100),
            )
            for row in rows
        ],
    )


@router.post("/technical/preferences/sync")
async def sync_technical_preferences_for_symbol(
    symbol: str = Query(...),
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    user_id = current_user["id"]
    service = TechnicalDataService(session)
    result = await service.sync_effective_indicators(user_id, symbol)
    await session.commit()
    return result


@router.post("/technical/preferences/bootstrap", response_model=TechnicalIndicatorPreferenceResponse)
async def bootstrap_technical_preferences(
    symbol: Optional[str] = Query(None),
    asset_class: Optional[str] = Query(None),
    scope: str = Query("asset_class"),
    preset: str = Query("recommended"),
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    user_id = current_user["id"]
    service = TechnicalDataService(session)

    try:
        result = await service.bootstrap_preferences(
            user_id,
            symbol=symbol,
            asset_class=asset_class,
            scope=scope,
            preset=preset,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    await session.commit()
    return TechnicalIndicatorPreferenceResponse(
        scope=result["scope"],
        symbol=result["symbol"],
        asset_class=result["asset_class"],
        indicators=[
            TechnicalIndicatorPreferenceItem(
                indicator=row.indicator,
                priority=int(row.priority or 100),
            )
            for row in result["rows"]
        ],
    )
