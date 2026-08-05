from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Iterable

from sqlalchemy.ext.asyncio import AsyncSession

from backend.infrastructure.models import MarketData
from backend.services.asset_catalog_service import AssetCatalogService
from backend.services.market_data_provider_registry import MarketDataProviderRegistry
from backend.schemas.market_provider_schema import AssetRecord, PriceSnapshotDTO

logger = logging.getLogger(__name__)


class MarketDataIngestionService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.asset_catalog_service = AssetCatalogService(session)
        self.provider_registry = MarketDataProviderRegistry()

    async def ingest_latest_snapshots(
        self,
        symbols: Iterable[str],
        *,
        commit: bool = True,
        continue_on_error: bool = True,
    ) -> dict[str, Any]:
        normalized = list(
            dict.fromkeys(
                str(symbol or "").strip().upper() for symbol in symbols if str(symbol or "").strip()
            )
        )
        if not normalized:
            return {
                "requested": [],
                "ingested": [],
                "failed": [],
                "success_count": 0,
                "failure_count": 0,
            }

        assets = await self.asset_catalog_service.get_assets(normalized)
        ingested: list[dict[str, Any]] = []
        failed: list[dict[str, Any]] = []

        for symbol in normalized:
            asset_payload = assets.get(symbol)
            if not asset_payload:
                failed.append({"symbol": symbol, "error": "asset_not_found"})
                if not continue_on_error:
                    break
                continue

            asset = AssetRecord(**asset_payload)
            try:
                snapshot = await self._fetch_snapshot(asset)
                record = self._build_market_data_row(snapshot)
                self.session.add(record)
                ingested.append(
                    {
                        "symbol": symbol,
                        "provider": snapshot.provider,
                        "provider_symbol": snapshot.provider_symbol,
                        "price": snapshot.price,
                        "observed_at": snapshot.observed_at.isoformat() if snapshot.observed_at else None,
                    }
                )
            except Exception as exc:
                logger.error("Latest snapshot ingestion failed for %s: %s", symbol, exc, exc_info=True)
                failed.append({"symbol": symbol, "error": str(exc)})
                if not continue_on_error:
                    break

        if commit:
            await self.session.commit()
        else:
            await self.session.flush()

        return {
            "requested": normalized,
            "ingested": ingested,
            "failed": failed,
            "success_count": len(ingested),
            "failure_count": len(failed),
        }

    async def ingest_default_v1_snapshots(
        self,
        *,
        commit: bool = True,
        continue_on_error: bool = True,
    ) -> dict[str, Any]:
        return await self.ingest_latest_snapshots(
            ["BTC", "SOL", "MSTR", "COIN", "SPY", "QQQ", "GLD", "VIX"],
            commit=commit,
            continue_on_error=continue_on_error,
        )

    async def _fetch_snapshot(self, asset: AssetRecord) -> PriceSnapshotDTO:
        provider = self.provider_registry.resolve_for_asset(asset)
        return await provider.fetch_latest_snapshot(asset)

    def _build_market_data_row(self, snapshot: PriceSnapshotDTO) -> MarketData:
        observed_at = snapshot.observed_at
        if observed_at is not None and observed_at.tzinfo is not None:
            observed_at = observed_at.replace(tzinfo=None)
        return MarketData(
            symbol=snapshot.symbol,
            price=snapshot.price,
            open=snapshot.open,
            high=snapshot.high,
            low=snapshot.low,
            change_24h=snapshot.change_percent,
            volume=snapshot.volume,
            timestamp=observed_at or datetime.utcnow(),
        )
