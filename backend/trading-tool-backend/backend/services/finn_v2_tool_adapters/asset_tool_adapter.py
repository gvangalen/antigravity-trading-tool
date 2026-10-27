from __future__ import annotations

from backend.schemas.finn_v2_evidence_schema import ActiveAssetData
from backend.services.asset_catalog_service import AssetCatalogService


class AssetToolAdapter:
    def __init__(self, session):
        self.assets = AssetCatalogService(session)

    async def execute(self, *, asset: str, resolution_source: str,
                      market_id: int | None = None, quote_currency: str | None = None,
                      **_kwargs):
        payload = await self.assets.get_asset(asset)
        # A catalog default is not the user's selected crypto trading pair.
        resolved_quote = (quote_currency if market_id is not None else
                          None if str(payload.get("asset_class") or "").lower() == "crypto"
                          else payload.get("quote_currency"))
        return {
            "data": ActiveAssetData(
                symbol=payload.get("symbol") or asset,
                market_id=market_id,
                pair=f"{asset}/{quote_currency}" if market_id is not None else None,
                display_name=payload.get("display_name"),
                asset_class=payload.get("asset_class"),
                provider=payload.get("provider"),
                exchange=payload.get("exchange"),
                market_region=payload.get("market_region"),
                timezone=payload.get("timezone"),
                quote_currency=resolved_quote,
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
