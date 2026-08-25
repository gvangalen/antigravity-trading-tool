from __future__ import annotations

from backend.infrastructure.repositories.technical_data_repository import TechnicalDataRepository
from backend.schemas.finn_v2_evidence_schema import IndicatorConfigurationData, IndicatorConfigurationItem
from backend.services.asset_catalog_service import AssetCatalogService


class IndicatorToolAdapter:
    def __init__(self, session):
        self.session = session
        self.repository = TechnicalDataRepository(session)

    @staticmethod
    def _serialize(rows):
        return [
            IndicatorConfigurationItem(
                indicator=row.indicator,
                category=row.category,
                priority=row.priority,
                enabled=row.enabled,
                symbol=row.symbol,
                asset_class=row.asset_class,
            )
            for row in rows
        ]

    async def execute(self, *, user_id: int, asset: str, **_kwargs):
        requested_symbol = str(asset or "").strip().upper()
        asset_meta = await AssetCatalogService(self.session).get_asset(asset)
        configuration = await self.repository.get_canonical_indicator_configuration(
            user_id,
            symbol=asset,
            asset_class=asset_meta.get("asset_class"),
        )
        technical = self._serialize(configuration["technical"])
        market = self._serialize(configuration["market"])
        macro = self._serialize(configuration["macro"])
        rows = [*configuration["technical"], *configuration["market"], *configuration["macro"]]
        for row in rows:
            if getattr(row, "user_id", user_id) != user_id:
                raise ValueError("indicator_owner_mismatch")
            row_symbol = str(getattr(row, "symbol", "") or "").strip().upper()
            if row_symbol and row_symbol != requested_symbol:
                raise ValueError("indicator_symbol_mismatch")
        storage_modes = configuration.get("storage_mode_by_category") or {}
        source = (
            "user_indicator_rule_overrides"
            if "legacy_rule_override" in storage_modes.values()
            else "user_indicator_configs"
        )
        return {
            "data": IndicatorConfigurationData(
                symbol=asset,
                asset_class=configuration.get("asset_class"),
                owner_user_id=user_id,
                requested_symbol=requested_symbol,
                resolved_symbol=requested_symbol,
                source_record_ids=[row.id for row in rows if getattr(row, "id", None) is not None],
                technical=technical,
                market=market,
                macro=macro,
                scope_by_category=configuration.get("scope_by_category") or {},
            ),
            "summary": {
                "title": "indicator_configuration",
                "symbol": asset,
                "asset_class": configuration.get("asset_class"),
                "technical_count": len(technical),
                "market_count": len(market),
                "macro_count": len(macro),
                "configured_count": len(technical) + len(market) + len(macro),
            },
            "as_of": None,
            "source": source,
            "schema_name": "IndicatorConfigurationData",
            "entity_type": "indicator_configuration",
            "asset": asset,
        }
