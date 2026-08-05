# FINN Market Data Platform Architecture v1

Last updated: 2026-08-05

## Purpose

This document defines the most professional V1 architecture for FINN market data inside the current repo.

The goal is not to wire one more provider into existing service code.
The goal is to establish a durable market data subsystem that:

- supports crypto and securities under one internal contract
- keeps provider logic outside business services
- stores normalized data inside FINN infrastructure
- enforces freshness and commercial usage boundaries
- lets frontend and AI flows read only FINN-owned data

## Architecture Position

The correct architectural frame is:

- FINN owns the internal market data model
- providers are adapters behind that model
- ingestion runs asynchronously on schedules
- application read paths never depend on third-party API calls at request time

This means:

- `Binance`, `Bybit`, and later `Coinbase` are crypto data sources
- `Twelve Data` is the first securities data source
- `SEC EDGAR` is a separate fundamentals and filings source
- scraping is not part of the core market data path

## Current Repo Reading

The current backend already contains useful foundations:

- `asset_catalog` now exists as a central asset metadata table
- `market_data` already stores symbol-scoped snapshots
- `market_data_7d` already stores historical daily market records
- symbol-scoped reads and indexes have been improved recently

The current structural gap is that provider logic is still embedded in application services:

- [backend/trading-tool-backend/backend/services/market_data_service.py](/Users/gvangalen/Documents/antigravity-trading-tool/backend/trading-tool-backend/backend/services/market_data_service.py:1)
- [backend/trading-tool-backend/backend/services/exchange_service.py](/Users/gvangalen/Documents/antigravity-trading-tool/backend/trading-tool-backend/backend/services/exchange_service.py:1)

This is acceptable for a crypto-first product bootstrap.
It is not the desired end state for a multi-asset FINN platform.

## Design Principles

### 1. Domain-first, provider-second

Internal models must reflect FINN concepts, not vendor response shapes.

### 2. Asset master before provider expansion

A stable `asset_catalog` is mandatory before broadening coverage.

### 3. Read from owned storage only

Frontend, AI, dashboards, reports, and watchlists read from FINN database and cache layers only.

### 4. Commercial rights are architecture, not paperwork

Provider source, license class, and display constraints must be represented in the system.

### 5. Freshness is explicit

Every dataset needs a target refresh policy and stale-data behavior.

### 6. Provider replacement must be cheap

Replacing `Twelve Data` with another securities provider should not require frontend or business-service rewrites.

## Target Logical Architecture

```text
                        +----------------------+
                        |    Asset Catalog     |
                        | asset_id + metadata  |
                        +----------+-----------+
                                   |
                                   v
 +------------------+    +-------------------------+    +----------------------+
 | Binance Adapter  |    | Twelve Data Adapter     |    | SEC EDGAR Adapter    |
 | Bybit Adapter    |--->| Provider Interface      |--->| Fundamentals/Filings |
 | Coinbase later   |    | Normalized DTO outputs  |    | later phase          |
 +------------------+    +-------------------------+    +----------------------+
                                   |
                                   v
                        +--------------------------+
                        |  Ingestion Orchestrators |
                        | snapshots / candles /    |
                        | fundamentals / filings   |
                        +------------+-------------+
                                     |
                                     v
              +----------------------+----------------------+
              |                                             |
              v                                             v
 +-----------------------------+              +-----------------------------+
 | PostgreSQL normalized store |              | Redis latest/cache layer    |
 | asset catalog               |              | optional V1 acceleration    |
 | latest snapshots            |              |                             |
 | ohlcv candles               |              +-----------------------------+
 | sync runs / quality         |
 | rights / freshness          |
 +---------------+-------------+
                 |
                 v
    +-------------------------------------------+
    | FINN APIs / scoring / AI / dashboard / UI |
    +-------------------------------------------+
```

## Canonical Internal Models

These are the core V1 domain objects.
They do not all need their own table immediately, but they should exist as internal backend types.

### Asset

Represents one tradable or reference instrument.

Required fields:

- `asset_id`
- `symbol`
- `display_name`
- `asset_class`
- `status`
- `base_currency`
- `quote_currency`
- `exchange`
- `market_region`
- `timezone`

### AssetIdentifier

Maps one FINN asset to provider-specific identifiers.

Required fields:

- `asset_id`
- `provider`
- `provider_symbol`
- `provider_market`
- `identifier_type`
- `is_primary`

### PriceSnapshot

Represents the latest normalized market state for one asset.

Required fields:

- `asset_id`
- `symbol`
- `price`
- `open`
- `high`
- `low`
- `previous_close`
- `change_absolute`
- `change_percent`
- `volume`
- `source_provider`
- `observed_at`
- `ingested_at`
- `is_delayed`

### OHLCVCandle

Represents normalized historical candles across all asset classes.

Required fields:

- `asset_id`
- `symbol`
- `timeframe`
- `open`
- `high`
- `low`
- `close`
- `volume`
- `period_start`
- `period_end`
- `source_provider`
- `is_final`

### FundamentalSnapshot

Reserved for a later phase.
Used for structured company fundamentals.

### FilingEvent

Reserved for a later phase.
Used for SEC filings and filing-derived metadata.

### ProviderSyncRun

Represents one ingestion execution unit.

Required fields:

- `provider`
- `job_type`
- `started_at`
- `finished_at`
- `status`
- `asset_count`
- `success_count`
- `failure_count`
- `error_summary`

### DataFreshness

Tracks freshness expectations and stale status.

Required fields:

- `dataset_type`
- `asset_id`
- `target_interval_seconds`
- `last_success_at`
- `stale_after_seconds`
- `status`

## Asset Master Strategy

The existing `asset_catalog` is the correct starting point, but it should evolve from a symbol list into an asset master.

Current foundation:

- [backend/trading-tool-backend/backend/services/asset_catalog_service.py](/Users/gvangalen/Documents/antigravity-trading-tool/backend/trading-tool-backend/backend/services/asset_catalog_service.py:1)
- [backend/trading-tool-backend/backend/scripts/migrations/2026_08_05_asset_catalog.py](/Users/gvangalen/Documents/antigravity-trading-tool/backend/trading-tool-backend/backend/scripts/migrations/2026_08_05_asset_catalog.py:1)

### V1 asset catalog extensions

Add these fields over time:

- `asset_id`
- `exchange`
- `market_region`
- `timezone`
- `base_currency`
- `quote_currency`
- `primary_provider`
- `fallback_provider`
- `provider_symbol`
- `provider_metadata`
- `entitlement_tier`
- `is_delayed`
- `refresh_policy`

### Key rule

Business services should gradually move from `symbol` as the only identity key toward:

- `asset_id` as canonical identity
- `symbol` as presentation and routing shorthand

V1 may still expose `symbol` heavily at API level.
The backend should still prepare for `asset_id` internally.

## Provider Adapter Layer

Provider-specific logic should move behind one shared interface.

### Target interface

Recommended internal classes:

- `MarketDataProvider`
- `CryptoMarketDataProvider`
- `SecuritiesMarketDataProvider`

Recommended adapter implementations:

- `BinanceMarketDataAdapter`
- `BybitMarketDataAdapter`
- `TwelveDataMarketDataAdapter`
- `SecEdgarAdapter` later

### Minimum interface methods

```python
class MarketDataProvider(Protocol):
    async def fetch_latest_snapshot(self, asset: AssetRecord) -> PriceSnapshotDTO: ...
    async def fetch_candles(
        self,
        asset: AssetRecord,
        timeframe: str,
        start_at: datetime | None = None,
        end_at: datetime | None = None,
        limit: int | None = None,
    ) -> list[OHLCVCandleDTO]: ...
```

Optional later methods:

- `fetch_order_book`
- `fetch_trades`
- `fetch_open_interest`
- `fetch_fundamentals`
- `fetch_filings`

### Provider selection

Selection should be routing-based, not hardcoded if-statements in market services.

Example routing rules:

- `asset_class = crypto` and `primary_provider = binance` -> `BinanceMarketDataAdapter`
- `asset_class in (stock, etf, index, commodity)` and `primary_provider = twelve_data` -> `TwelveDataMarketDataAdapter`

## Ingestion Architecture

Market data ingestion should be separated by job type, not by page.

### V1 ingestion jobs

#### `sync_latest_snapshots`

Purpose:

- update latest price state for all active V1 assets

Cadence:

- crypto every 1 to 5 minutes
- securities every 5 to 15 minutes during relevant sessions

#### `sync_intraday_candles`

Purpose:

- maintain intraday chart data for active assets and key timeframes

Cadence:

- asset and timeframe dependent

#### `sync_daily_candles`

Purpose:

- maintain end-of-day normalized candles

Cadence:

- daily after close for securities
- daily UTC rollover for crypto

#### `sync_asset_reference_data`

Purpose:

- refresh asset metadata, symbols, exchange mapping, and provider coverage

Cadence:

- daily or manual

### V2 ingestion jobs

- `sync_fundamental_snapshots`
- `sync_sec_filings`
- `sync_corporate_actions`

## Storage Design

The current `market_data` and `market_data_7d` tables are usable stepping stones, but they are not the ideal end state.

### V1 acceptable storage pattern

Use:

- `asset_catalog`
- `market_data` for latest snapshots
- `market_data_7d` for daily normalized candles

This minimizes rewrite cost and gets multi-asset support into production faster.

### Preferred next storage pattern

Introduce dedicated normalized tables:

- `market_price_snapshots`
- `market_ohlcv_candles`
- `provider_sync_runs`
- `provider_asset_status`
- `data_rights_policies`

### Recommended table intent

#### `market_price_snapshots`

One row per observed latest snapshot event.

#### `market_ohlcv_candles`

One row per `asset_id + timeframe + period_start`.

#### `provider_sync_runs`

Operational observability for ingestion jobs.

#### `provider_asset_status`

Per asset/provider sync health and latest success status.

#### `data_rights_policies`

Commercial usage controls per provider and dataset.

## Rights And Entitlements

This is part of the professional architecture and should not be deferred conceptually, even if the first implementation is light.

Track at least:

- `provider`
- `dataset_type`
- `license_type`
- `display_allowed`
- `redistribution_allowed`
- `commercial_usage_allowed`
- `is_realtime`
- `requires_attribution`

### Why this matters

Without this layer, FINN can become technically correct but commercially unsafe.

## Freshness And Stale Data Policy

Each dataset needs an explicit freshness target.

### V1 target classes

#### Crypto live snapshot

- target interval: 60 to 300 seconds
- stale after: 10 minutes

#### Securities snapshot

- target interval: 300 to 900 seconds
- stale after: 30 minutes during market session

#### Daily candles

- target interval: once per daily cycle
- stale after: next expected close plus tolerance

### Read-path rule

API consumers should receive freshness metadata.

Minimum fields:

- `observed_at`
- `ingested_at`
- `is_stale`
- `source_provider`

## Concrete Repo Layout

Recommended backend additions:

### New services

- `backend/trading-tool-backend/backend/services/market_data_provider_registry.py`
- `backend/trading-tool-backend/backend/services/providers/binance_market_data_adapter.py`
- `backend/trading-tool-backend/backend/services/providers/bybit_market_data_adapter.py`
- `backend/trading-tool-backend/backend/services/providers/twelve_data_market_data_adapter.py`
- `backend/trading-tool-backend/backend/services/market_data_ingestion_service.py`
- `backend/trading-tool-backend/backend/services/asset_master_service.py`

### New repositories

- `backend/trading-tool-backend/backend/infrastructure/repositories/asset_catalog_repository.py`
- `backend/trading-tool-backend/backend/infrastructure/repositories/provider_sync_repository.py`
- `backend/trading-tool-backend/backend/infrastructure/repositories/ohlcv_repository.py`

### New schemas or DTOs

- `backend/trading-tool-backend/backend/schemas/market_provider_schema.py`
- `backend/trading-tool-backend/backend/schemas/asset_master_schema.py`

### Existing files to refactor

- [backend/trading-tool-backend/backend/services/market_data_service.py](/Users/gvangalen/Documents/antigravity-trading-tool/backend/trading-tool-backend/backend/services/market_data_service.py:1)
- [backend/trading-tool-backend/backend/services/exchange_service.py](/Users/gvangalen/Documents/antigravity-trading-tool/backend/trading-tool-backend/backend/services/exchange_service.py:1)
- [backend/trading-tool-backend/backend/services/asset_catalog_service.py](/Users/gvangalen/Documents/antigravity-trading-tool/backend/trading-tool-backend/backend/services/asset_catalog_service.py:1)
- [backend/trading-tool-backend/backend/infrastructure/repositories/market_data_repository.py](/Users/gvangalen/Documents/antigravity-trading-tool/backend/trading-tool-backend/backend/infrastructure/repositories/market_data_repository.py:1)
- [backend/trading-tool-backend/backend/infrastructure/models.py](/Users/gvangalen/Documents/antigravity-trading-tool/backend/trading-tool-backend/backend/infrastructure/models.py:144)

## V1 Asset Universe

Keep V1 intentionally small and curated.

### Crypto

- `BTC`
- `ETH`
- `SOL`
- `XRP`
- `LINK`

### Crypto-adjacent equities

- `MSTR`
- `COIN`
- `MARA`
- `RIOT`
- `CLSK`
- `HUT`
- `BTDR`
- `WULF`
- `CORZ`

### ETFs and macro proxies

- `SPY`
- `QQQ`
- `IBIT`
- `FBTC`
- `GLD`
- `SPX`
- `NDX`
- `VIX`
- `DXY`

## Implementation Sequence

This is the recommended execution order for the current repo.

### Phase 1 - Asset master hardening

Goal:

- make `asset_catalog` the central routing source for market assets

Changes:

- add provider-routing metadata to `asset_catalog`
- add V1 asset universe
- introduce repository-backed reads instead of service-only fallbacks

Acceptance:

- each V1 asset resolves to one primary provider and one provider symbol

### Phase 2 - Provider interface and adapter extraction

Goal:

- remove direct provider logic from `MarketDataService`

Changes:

- define provider interface
- extract existing crypto fetch logic into `BinanceMarketDataAdapter`
- add `TwelveDataMarketDataAdapter`
- add registry-based provider resolution

Acceptance:

- `MarketDataService` orchestrates reads instead of talking provider APIs directly

### Phase 3 - Normalized ingestion jobs

Goal:

- stop coupling asset page reads to live provider fetches

Changes:

- add scheduled snapshot sync job
- add scheduled daily candle sync job
- persist normalized outputs into FINN storage
- add sync-run logging

Acceptance:

- API latest reads succeed without third-party calls at request time

### Phase 4 - Read model and freshness metadata

Goal:

- expose provider-neutral market data to frontend and AI layers

Changes:

- extend read responses with freshness metadata
- ensure dashboard and asset pages read only normalized tables
- add stale-data logic

Acceptance:

- asset endpoints work consistently for `BTC`, `MSTR`, `SPY`, and `VIX`

### Phase 5 - Operational controls

Goal:

- make ingestion supportable in production

Changes:

- add sync health records
- add alerts for stale or missing data
- track rights and delay flags

Acceptance:

- operators can identify provider failures and stale symbols quickly

### Phase 6 - Fundamentals and filings

Goal:

- add securities context without destabilizing V1 market data

Changes:

- add `SecEdgarAdapter`
- ingest latest filings
- ingest basic structured fundamentals

Acceptance:

- crypto-adjacent equities can show filings and lightweight fundamentals without changing price architecture

## Explicit Non-Goals For Initial Execution

Do not include these in the first build sprint:

- scraping for primary price data
- full-market symbol coverage
- advanced order book ingestion for all assets
- multi-provider price reconciliation
- fundamentals and price ingestion in one delivery batch
- frontend-driven direct provider fetches

## First Technical Task

The first correct implementation task is:

Build a provider-agnostic market data layer by introducing a `MarketDataProvider` interface, routing assets through `asset_catalog`, extracting current crypto fetch logic into a `BinanceMarketDataAdapter`, and adding a `TwelveDataMarketDataAdapter` that normalizes stock, ETF, and index snapshots and candles into the same internal model.

This is the narrowest step that preserves professional architecture while still moving V1 forward.

## Definition Of Done For Market Data V1

V1 is complete when:

- crypto and securities are ingested through provider adapters
- latest market reads come from FINN storage, not live vendor calls
- `BTC`, `SOL`, `MSTR`, `COIN`, `SPY`, `QQQ`, `GLD`, and `VIX` work through the same backend contract
- `asset_catalog` is the routing source of truth
- freshness metadata is exposed to consumers
- provider source is traceable per record
- rights and delay constraints are represented in backend metadata

## Recommended Immediate Follow-up

After this document, the next implementation slice should be:

1. extend `asset_catalog`
2. add provider interface and registry
3. extract Binance adapter
4. add Twelve Data adapter
5. switch `MarketDataService` to provider-orchestrator mode

That sequence keeps the codebase moving toward the intended architecture without a disruptive rewrite.
