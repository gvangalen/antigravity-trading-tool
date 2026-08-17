from __future__ import annotations

from backend.services.asset_catalog_service import AssetCatalogService


class AssetToolAdapter:
    def __init__(self, session):
        self.assets = AssetCatalogService(session)

    async def execute(self, *, asset: str, resolution_source: str, **_kwargs):
        payload = await self.assets.get_asset(asset)
        return {
            "data": payload,
            "summary": {"title": "active_asset", "symbol": payload.get("symbol"), "asset_class": payload.get("asset_class")},
            "as_of": None,
            "resolution_source": resolution_source,
        }

