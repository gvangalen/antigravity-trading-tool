from __future__ import annotations

import logging
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any, Iterable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.infrastructure.database import async_session_factory
from backend.infrastructure.models import MarketData
from backend.services.asset_catalog_service import AssetCatalogService
from backend.services.market_data_provider_registry import MarketDataProviderRegistry
from backend.schemas.market_provider_schema import AssetRecord, PriceSnapshotDTO
from backend.services.trading_market_service import TradingMarket

logger = logging.getLogger(__name__)


class MarketDataIngestionService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.asset_catalog_service = AssetCatalogService(session)
        self.provider_registry = MarketDataProviderRegistry()

    async def ingest_exact_market_snapshot(
        self, market: TradingMarket, *, commit: bool = True,
    ) -> dict[str, Any]:
        """Fetch one verified pair without the base asset's default quote or FX.

        The legacy symbol-wide ingester remains separate until its score and
        bot consumers have switched to ``market_id``. A provider response for
        another pair is rejected before any row is written.
        """
        asset_payload = await self.asset_catalog_service.get_asset(market.asset_symbol)
        if not asset_payload or str(asset_payload.get("asset_class") or "").lower() != "crypto":
            raise ValueError("market_asset_not_found")
        asset = AssetRecord(**{
            **asset_payload,
            "provider": market.provider,
            "primary_provider": market.provider,
            "fallback_provider": None,
            "provider_symbol": market.provider_symbol,
            "exchange": market.venue,
            "quote_currency": market.quote_currency,
        })
        snapshot = await self._fetch_snapshot(asset)
        if str(snapshot.provider_symbol or "").upper() != market.provider_symbol:
            raise ValueError("market_provider_symbol_mismatch")
        if str(snapshot.symbol or "").upper() != market.asset_symbol:
            raise ValueError("market_base_symbol_mismatch")
        if str(snapshot.provider or "").lower() != market.provider.lower():
            raise ValueError("market_provider_mismatch")
        record = self._build_market_data_row(snapshot)
        record.market_id = market.id
        self.session.add(record)
        if commit:
            await self.session.commit()
        else:
            await self.session.flush()
        return {
            "market_id": market.id,
            "pair": market.pair,
            "provider_symbol": market.provider_symbol,
            "price": snapshot.price,
            "quote_currency": market.quote_currency,
            "observed_at": snapshot.observed_at.isoformat() if snapshot.observed_at else None,
        }

    async def ingest_latest_snapshots(
        self,
        symbols: Iterable[str],
        *,
        commit: bool = True,
        continue_on_error: bool = True,
        release_catalog_read_transaction: bool = False,
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
        if release_catalog_read_transaction:
            # Scheduled ingestion may wait on several external providers. End
            # the catalog SELECT transaction before those network requests;
            # this option is for callers with no pending session writes.
            await self.session.rollback()
        ingested: list[dict[str, Any]] = []
        skipped: list[str] = []
        failed: list[dict[str, Any]] = []
        pending_records: list[MarketData] = []

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
                # Only the scheduled caller releases its catalog transaction
                # before provider I/O.  Interactive callers may already hold
                # an owner write in a pool of size one; they must not open a
                # second read connection or wait on a recovery provider call.
                if release_catalog_read_transaction:
                    snapshot, is_final_candle = await self._reconcile_conflicting_quote(asset, snapshot)
                else:
                    is_final_candle = False
                    if await self._interactive_quote_conflict(snapshot):
                        skipped.append(symbol)
                        continue
                if snapshot is None:
                    skipped.append(symbol)
                    continue
                record = self._build_market_data_row(snapshot)
                record.is_final_candle = is_final_candle
                pending_records.append(record)
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

        for record in pending_records:
            self.session.add(record)
        if commit:
            await self.session.commit()
        else:
            await self.session.flush()

        return {
            "requested": normalized,
            "ingested": ingested,
            "skipped": skipped,
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
            ["BTC", "SOL", "AAPL", "MSFT", "MSTR", "COIN", "SPY", "QQQ", "GLD", "VIX"],
            commit=commit,
            continue_on_error=continue_on_error,
        )

    async def _fetch_snapshot(self, asset: AssetRecord) -> PriceSnapshotDTO:
        provider = self.provider_registry.resolve_for_asset(asset)
        snapshot = await provider.fetch_latest_snapshot(asset)
        if str(snapshot.currency or "").upper() != str(asset.quote_currency or "").upper():
            raise ValueError("market_quote_currency_mismatch")
        return snapshot

    async def _reconcile_conflicting_quote(
        self, asset: AssetRecord, snapshot: PriceSnapshotDTO,
    ) -> tuple[PriceSnapshotDTO | None, bool]:
        """Replace a mutable Twelve Data quote only with its finalized candle.

        This runs for legacy equity quotes.  Exact crypto pairs use a separate
        ingester and do not request Twelve Data candles.
        """
        if snapshot.provider != "twelve_data" or snapshot.observed_at is None:
            return snapshot, False
        observed = snapshot.observed_at.replace(tzinfo=None)
        rows = await self._source_rows_at(snapshot.symbol, observed)
        if len(rows) >= 4096:
            raise ValueError("market_quote_source_conflict_overflow")
        facts = {(str(row.symbol or "").upper(), Decimal(str(row.price)),
                  str(row.quote_currency or "").upper(),
                  str(row.price_provider or "").lower()) for row in rows}
        current = (str(snapshot.symbol).upper(), Decimal(str(snapshot.price)),
                   str(snapshot.currency or "").upper(), str(snapshot.provider).lower())
        if len(facts | {current}) == 1:
            return snapshot, False
        minute_end = snapshot.observed_at.replace(second=0, microsecond=0) + timedelta(minutes=1)
        existing_final = await self._source_rows_at(
            snapshot.symbol, minute_end.replace(tzinfo=None), final_only=True,
        )
        if existing_final:
            final_facts = {(str(row.symbol or "").upper(), Decimal(str(row.price)),
                            str(row.quote_currency or "").upper(),
                            str(row.price_provider or "").lower()) for row in existing_final}
            if (len(existing_final) >= 4096 or len(final_facts) != 1
                    or next(iter(final_facts))[0] != str(snapshot.symbol).upper()
                    or next(iter(final_facts))[2] != str(asset.quote_currency or "").upper()
                    or next(iter(final_facts))[3] != "twelve_data"):
                raise ValueError("market_final_candle_identity_mismatch")
            return None, True
        provider = self.provider_registry.resolve_for_asset(asset)
        if not hasattr(provider, "fetch_final_minute_snapshot"):
            raise ValueError("market_quote_source_conflict_unresolved")
        final = await provider.fetch_final_minute_snapshot(asset, snapshot)
        if (str(final.symbol).upper() != str(asset.symbol).upper()
                or str(final.currency or "").upper() != str(asset.quote_currency or "").upper()
                or final.observed_at is None or final.observed_at <= snapshot.observed_at):
            raise ValueError("market_final_candle_identity_mismatch")
        return final, True

    async def _interactive_quote_conflict(self, snapshot: PriceSnapshotDTO) -> bool:
        """Do not grow a known conflict in an owner transaction or small pool."""
        if snapshot.provider != "twelve_data" or snapshot.observed_at is None:
            return False
        result = await self.session.execute(
            select(MarketData).where(
                MarketData.symbol == snapshot.symbol, MarketData.market_id.is_(None),
                MarketData.source_observed_at == snapshot.observed_at.replace(tzinfo=None),
            ).limit(4096)
        )
        rows = result.scalars().all()
        if len(rows) >= 4096:
            return True
        try:
            facts = {(str(row.symbol or "").upper(), Decimal(str(row.price)),
                      str(row.quote_currency or "").upper(),
                      str(row.price_provider or "").lower()) for row in rows}
            current = (str(snapshot.symbol).upper(), Decimal(str(snapshot.price)),
                       str(snapshot.currency or "").upper(), str(snapshot.provider).lower())
        except (InvalidOperation, TypeError, ValueError):
            return True
        return len(facts | {current}) != 1

    @staticmethod
    async def _source_rows_at(
        symbol: str, observed_at: datetime, *, final_only: bool = False,
    ) -> list[MarketData]:
        """Complete the read transaction before awaiting a provider request."""
        stmt = select(MarketData).where(
            MarketData.symbol == symbol, MarketData.market_id.is_(None),
            MarketData.source_observed_at == observed_at,
        )
        if final_only:
            stmt = stmt.where(MarketData.is_final_candle.is_(True))
        async with async_session_factory() as read_session:
            result = await read_session.execute(stmt.limit(4096))
            return result.scalars().all()

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
            source_observed_at=observed_at,
            quote_currency=str(snapshot.currency).upper() if snapshot.currency else None,
            price_provider=snapshot.provider,
        )
