from __future__ import annotations

from backend.schemas.finn_v2_evidence_schema import ActiveAssetData
from backend.services.asset_catalog_service import AssetCatalogService


class AssetToolAdapter:
    def __init__(self, session):
        self.assets = AssetCatalogService(session)

    async def execute(self, *, asset: str, resolution_source: str, **_kwargs):
        payload = await self.assets.get_asset(asset)
        return {
            "data": ActiveAssetData(
                symbol=payload.get("symbol") or asset,
                display_name=payload.get("display_name"),
                asset_class=payload.get("asset_class"),
                provider=payload.get("provider"),
                exchange=payload.get("exchange"),
                market_region=payload.get("market_region"),
                timezone=payload.get("timezone"),
                quote_currency=payload.get("quote_currency"),
                refresh_policy=payload.get("refresh_policy"),
            ),
            "summary": {"title": "active_asset", "symbol": payload.get("symbol"), "asset_class": payload.get("asset_class")},
            "as_of": None,
            "resolution_source": resolution_source,
            "source": "asset_catalog",
            "schema_name": "ActiveAssetData",
            "entity_type": "asset",
            "entity_id": payload.get("symbol") or asset,
            "asset": payload.get("symbol") or asset,
        }
