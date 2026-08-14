from typing import List

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from backend.infrastructure.database import get_db
from backend.services.asset_catalog_service import AssetCatalogService
from backend.utils.auth_utils import get_current_user

router = APIRouter()


class AssetSearchItemResponse(BaseModel):
    symbol: str
    display_name: str
    asset_class: str
    exchange: str | None = None
    tradingview_symbol: str | None = None
    logo_url: str | None = None


@router.get("/assets/search", response_model=List[AssetSearchItemResponse])
async def search_assets(
    q: str = Query(default="", min_length=1),
    asset_classes: str = Query(default="crypto,stock"),
    limit: int = Query(default=8, ge=1, le=20),
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    _ = current_user
    classes = [
        value.strip().lower()
        for value in str(asset_classes or "").split(",")
        if value.strip()
    ]

    results = await AssetCatalogService(session).search_assets(
        q,
        asset_classes=classes,
        limit=limit,
    )
    return [
        AssetSearchItemResponse(
            symbol=str(asset.get("symbol") or "").upper(),
            display_name=asset.get("display_name") or str(asset.get("symbol") or "").upper(),
            asset_class=str(asset.get("asset_class") or "unknown").lower(),
            exchange=asset.get("exchange"),
            tradingview_symbol=asset.get("tradingview_symbol"),
            logo_url=asset.get("logo_url"),
        )
        for asset in results
        if asset.get("symbol")
    ]
