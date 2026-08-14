from typing import Optional, List, Dict, Any
from datetime import datetime, date, timezone, timedelta
from collections import defaultdict
import asyncio
import httpx
import logging

from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import HTTPException

from backend.infrastructure.repositories.market_data_repository import MarketDataRepository
from backend.infrastructure.repositories.technical_data_repository import TechnicalDataRepository
from backend.schemas.market_data_schema import (
    MarketDataResponse, MarketDataIndicatorResponse, MarketData7DResponse,
    MarketForwardReturnResponse, ForwardReturnChartResponse
)
from backend.schemas.market_provider_schema import AssetRecord
from backend.infrastructure.models import MarketDataIndicator, MarketData7D
from backend.services.asset_catalog_service import AssetCatalogService
from backend.services.market_data_provider_registry import MarketDataProviderRegistry
from backend.utils.scoring_utils import normalize_indicator_name
from backend.utils.indicator_score_validation import require_indicator_score

logger = logging.getLogger(__name__)

_FORWARD_RETURN_SYNC_TASKS: dict[str, asyncio.Task] = {}
_FORWARD_RETURN_SYNC_TASKS_LOCK: asyncio.Lock | None = None


FORWARD_RETURN_SYMBOL_SUPPORT: dict[str, dict[str, Any]] = {
    "BTC": {"source": "binance", "minimum_history_years": 5},
    "ETH": {"source": "binance", "minimum_history_years": 4},
    "SOL": {"source": "binance", "minimum_history_years": 3},
    "XRP": {"source": "binance", "minimum_history_years": 5},
    "LINK": {"source": "binance", "minimum_history_years": 4},
    "MSTR": {"source": "twelve_data", "minimum_history_years": 5},
    "COIN": {"source": "twelve_data", "minimum_history_years": 4},
    "MARA": {"source": "twelve_data", "minimum_history_years": 5},
    "RIOT": {"source": "twelve_data", "minimum_history_years": 5},
    "CLSK": {"source": "twelve_data", "minimum_history_years": 5},
    "HUT": {"source": "twelve_data", "minimum_history_years": 5},
    "BTDR": {"source": "twelve_data", "minimum_history_years": 3},
    "WULF": {"source": "twelve_data", "minimum_history_years": 4},
    "CORZ": {"source": "twelve_data", "minimum_history_years": 2},
    "SPY": {"source": "twelve_data", "minimum_history_years": 5},
    "QQQ": {"source": "twelve_data", "minimum_history_years": 5},
    "IBIT": {"source": "twelve_data", "minimum_history_years": 1},
    "FBTC": {"source": "twelve_data", "minimum_history_years": 1},
    "GLD": {"source": "twelve_data", "minimum_history_years": 5},
    "AAPL": {"source": "twelve_data", "minimum_history_years": 5},
    "MSFT": {"source": "twelve_data", "minimum_history_years": 5},
}

# =========================================================
# SYNCHRONOUS WRAPPERS FOR LEGACY COMPONENTS
# =========================================================
def sync_score_indicator(category: str, indicator: str, value: float, user_id: int) -> Dict[str, Any]:
    from backend.utils.db import get_db_connection
    from backend.utils.scoring_engine import score_indicator
    conn = get_db_connection()
    try:
        if not conn:
            raise RuntimeError("Geen databaseverbinding voor scoring engine.")
        return score_indicator(conn=conn, category=category, indicator=indicator, value=value, user_id=user_id)
    finally:
        if conn:
            conn.close()

def sync_get_scores_for_symbol(user_id: int, symbol: str = "BTC") -> Dict[str, Any]:
    from backend.utils.scoring_utils import get_scores_for_symbol
    return get_scores_for_symbol(user_id=user_id, symbol=symbol, include_metadata=True)



class MarketDataService:
    def __init__(self, db_session: AsyncSession):
        self.session = db_session
        self.repository = MarketDataRepository(db_session)
        self.preference_repository = TechnicalDataRepository(db_session)
        self.provider_registry = MarketDataProviderRegistry()

    @staticmethod
    def _forward_return_sync_lock() -> asyncio.Lock:
        global _FORWARD_RETURN_SYNC_TASKS_LOCK
        if _FORWARD_RETURN_SYNC_TASKS_LOCK is None:
            _FORWARD_RETURN_SYNC_TASKS_LOCK = asyncio.Lock()
        return _FORWARD_RETURN_SYNC_TASKS_LOCK

    async def get_forward_return_support(self, symbol: str) -> dict[str, Any]:
        normalized_symbol = str(symbol or "").strip().upper()
        asset_meta = await AssetCatalogService(self.session).get_asset(normalized_symbol)
        config = FORWARD_RETURN_SYMBOL_SUPPORT.get(normalized_symbol)
        if not config:
            return {
                "supported": False,
                "symbol": normalized_symbol,
                "asset_class": asset_meta.get("asset_class"),
                "source": None,
                "reason": "unsupported_symbol",
            }
        return {
            "supported": True,
            "symbol": normalized_symbol,
            "asset_class": asset_meta.get("asset_class"),
            "source": config["source"],
            "minimum_history_years": int(config["minimum_history_years"]),
            "provider_symbol": asset_meta.get("provider_symbol") or normalized_symbol,
        }

    @staticmethod
    def _coverage_cutoff_date(minimum_history_years: int) -> date:
        return (datetime.now(timezone.utc) - timedelta(days=365 * int(minimum_history_years))).date()

    @staticmethod
    def _as_date(value: Any) -> date | None:
        if value is None:
            return None
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, date):
            return value
        return None

    async def _forward_returns_need_refresh(self, symbol: str, support: dict[str, Any]) -> bool:
        records = await self.repository.get_forward_returns(symbol)
        if not records:
            return True

        oldest = min((self._as_date(record.start_date) for record in records if record.start_date), default=None)
        newest = max((self._as_date(record.start_date) for record in records if record.start_date), default=None)
        if oldest is None or newest is None:
            return True

        if oldest > self._coverage_cutoff_date(support["minimum_history_years"]):
            return True

        if newest < (datetime.now(timezone.utc) - timedelta(days=45)).date():
            return True

        return False

    async def ensure_forward_returns_ready(self, symbol: str) -> dict[str, Any]:
        normalized_symbol = str(symbol or "").strip().upper()
        support = await self.get_forward_return_support(normalized_symbol)
        if not support.get("supported"):
            return support

        if await self._forward_returns_need_refresh(normalized_symbol, support):
            logger.info("🔁 Forward returns refresh nodig voor %s", normalized_symbol)
            await self._ensure_single_forward_return_sync(normalized_symbol)

        return support

    async def _ensure_single_forward_return_sync(self, symbol: str) -> dict[str, Any]:
        normalized_symbol = str(symbol or "").strip().upper()

        async with self._forward_return_sync_lock():
            existing_task = _FORWARD_RETURN_SYNC_TASKS.get(normalized_symbol)
            if existing_task is None or existing_task.done():
                existing_task = asyncio.create_task(self.sync_symbol_forward_returns(normalized_symbol))
                _FORWARD_RETURN_SYNC_TASKS[normalized_symbol] = existing_task

        try:
            return await existing_task
        finally:
            if existing_task.done():
                async with self._forward_return_sync_lock():
                    if _FORWARD_RETURN_SYNC_TASKS.get(normalized_symbol) is existing_task:
                        _FORWARD_RETURN_SYNC_TASKS.pop(normalized_symbol, None)

    async def sync_supported_forward_returns(
        self,
        *,
        symbols: list[str] | None = None,
        asset_class: str | None = None,
    ) -> dict[str, Any]:
        requested = [str(symbol or "").strip().upper() for symbol in (symbols or []) if str(symbol or "").strip()]
        if requested:
            targets = [symbol for symbol in requested if symbol in FORWARD_RETURN_SYMBOL_SUPPORT]
        else:
            targets = list(FORWARD_RETURN_SYMBOL_SUPPORT.keys())
            if asset_class:
                normalized_class = str(asset_class or "").strip().lower()
                catalog = await AssetCatalogService(self.session).get_assets(targets)
                targets = [
                    symbol for symbol in targets
                    if str(catalog.get(symbol, {}).get("asset_class") or "").strip().lower() == normalized_class
                ]

        results: dict[str, Any] = {"requested": targets, "synced": [], "failed": []}
        for symbol in targets:
            try:
                payload = await self.sync_symbol_forward_returns(symbol)
                results["synced"].append({"symbol": symbol, "payload": payload})
            except Exception as exc:
                logger.error("❌ Forward returns sync mislukt voor %s: %s", symbol, exc, exc_info=True)
                await self.session.rollback()
                results["failed"].append({"symbol": symbol, "error": str(exc)})
        return results

    async def _load_binance_forward_prices(self, asset: AssetRecord) -> dict[date, float]:
        all_prices: list[tuple[int, float]] = []
        raw_provider_symbol = str(asset.provider_symbol or "").strip().upper()
        if raw_provider_symbol.endswith(("USDT", "USDC", "BUSD", "FDUSD", "EUR", "USD")):
            provider_symbol = raw_provider_symbol
        else:
            quote_currency = str(asset.quote_currency or "USDT").strip().upper() or "USDT"
            provider_symbol = f"{asset.symbol.upper()}{quote_currency}"
        end_time: int | None = None

        async with httpx.AsyncClient(timeout=15.0) as client:
            for _ in range(4):
                params: dict[str, Any] = {
                    "symbol": provider_symbol,
                    "interval": "1d",
                    "limit": 1000,
                }
                if end_time is not None:
                    params["endTime"] = end_time

                response = await client.get("https://api.binance.com/api/v3/klines", params=params)
                response.raise_for_status()
                rows = response.json()
                if not rows:
                    break

                chunk = [(int(row[0]), float(row[4])) for row in rows]
                all_prices = chunk + all_prices
                end_time = int(rows[0][0]) - 1

                if len(rows) < 1000:
                    break

        return {
            datetime.fromtimestamp(ts / 1000, timezone.utc).date(): price
            for ts, price in all_prices
        }

    async def _load_twelve_data_forward_prices(self, asset: AssetRecord) -> dict[date, float]:
        provider = self.provider_registry.get_provider("twelve_data")
        candles = await provider.fetch_candles(asset, "1day", limit=5000)
        return {
            candle.period_start.date(): float(candle.close)
            for candle in candles
            if candle.period_start and candle.close is not None
        }

    async def _resolve_asset_scope(
        self,
        symbol: Optional[str] = None,
        asset_class: Optional[str] = None,
    ) -> tuple[Optional[str], Optional[str]]:
        normalized_symbol = str(symbol or "").strip().upper() or None
        normalized_asset_class = str(asset_class or "").strip().lower() or None
        if normalized_symbol and not normalized_asset_class:
            asset = await AssetCatalogService(self.session).get_asset(normalized_symbol)
            normalized_asset_class = str(asset.get("asset_class") or "").strip().lower() or None
        return normalized_symbol, normalized_asset_class

    async def resolve_effective_preferences(
        self,
        user_id: int,
        *,
        symbol: Optional[str] = None,
        asset_class: Optional[str] = None,
    ) -> Dict[str, Any]:
        normalized_symbol, normalized_asset_class = await self._resolve_asset_scope(symbol=symbol, asset_class=asset_class)

        if normalized_symbol:
            symbol_rows = await self.preference_repository.list_scope_configs(
                user_id,
                category="market",
                symbol=normalized_symbol,
                asset_class=normalized_asset_class,
            )
            if symbol_rows:
                return {
                    "scope": "symbol_override",
                    "symbol": normalized_symbol,
                    "asset_class": normalized_asset_class,
                    "rows": symbol_rows,
                }

        if normalized_asset_class:
            class_rows = await self.preference_repository.list_scope_configs(
                user_id,
                category="market",
                asset_class=normalized_asset_class,
            )
            if class_rows:
                return {
                    "scope": "asset_class_override",
                    "symbol": normalized_symbol,
                    "asset_class": normalized_asset_class,
                    "rows": class_rows,
                }

        return {
            "scope": "empty",
            "symbol": normalized_symbol,
            "asset_class": normalized_asset_class,
            "rows": [],
        }

    async def _build_scope_items(self, indicator_names: List[str]) -> List[tuple[str, int]]:
        items: List[tuple[str, int]] = []
        seen: set[str] = set()
        for priority, indicator_name in enumerate(indicator_names, start=1):
            normalized_name = normalize_indicator_name(indicator_name)
            if normalized_name in seen:
                continue
            cfg = await self.preference_repository.get_indicator_config(normalized_name, category="market")
            if not cfg or cfg.category != "market":
                logger.warning("⚠️ Market indicator '%s' ontbreekt of heeft verkeerde category.", normalized_name)
                continue
            items.append((normalized_name, priority))
            seen.add(normalized_name)
        return items

    async def bootstrap_preferences(
        self,
        user_id: int,
        *,
        symbol: Optional[str] = None,
        asset_class: Optional[str] = None,
        scope: str = "asset_class",
        preset: str = "recommended",
    ) -> Dict[str, Any]:
        normalized_symbol, normalized_asset_class = await self._resolve_asset_scope(symbol=symbol, asset_class=asset_class)
        normalized_scope = str(scope or "asset_class").strip().lower()
        normalized_preset = str(preset or "recommended").strip().lower()
        if normalized_preset != "recommended":
            raise ValueError(f"Onbekende preset '{preset}'.")

        if normalized_scope == "symbol":
            if not normalized_symbol:
                raise ValueError("Een symbool is verplicht voor scope 'symbol'.")
            target_symbol = normalized_symbol
            target_asset_class = normalized_asset_class
        elif normalized_scope == "asset_class":
            if not normalized_asset_class:
                raise ValueError("Een asset_class of herleidbaar symbool is verplicht voor scope 'asset_class'.")
            target_symbol = None
            target_asset_class = normalized_asset_class
        elif normalized_scope == "default":
            target_symbol = None
            target_asset_class = None
        else:
            raise ValueError("Scope moet 'default', 'asset_class' of 'symbol' zijn.")

        rows = await self.preference_repository.replace_scope_configs(
            user_id,
            [],
            category="market",
            symbol=target_symbol,
            asset_class=target_asset_class,
        )
        return {
            "scope": "symbol_override" if target_symbol else ("asset_class_override" if target_asset_class else "default"),
            "symbol": target_symbol,
            "asset_class": target_asset_class,
            "rows": rows,
        }

    async def _reset_symbol_indicator_rows(self, user_id: int, symbol: str) -> None:
        normalized_symbol = str(symbol or "BTC").strip().upper()
        existing_rows = await self.repository.get_active_day_indicators(user_id, normalized_symbol)
        for row in existing_rows:
            indicator_name = str(getattr(row, "name", "") or "").strip()
            if not indicator_name:
                continue
            await self.repository.delete_user_market_indicator(indicator_name, user_id, normalized_symbol)

    async def sync_effective_indicators(
        self,
        user_id: int,
        symbol: str,
        *,
        reset_existing: bool = False,
    ) -> Dict[str, Any]:
        normalized_symbol = str(symbol or "BTC").strip().upper()
        resolved = await self.resolve_effective_preferences(user_id, symbol=normalized_symbol)
        indicator_names = [normalize_indicator_name(row.indicator) for row in resolved["rows"]]
        results: Dict[str, Any] = {
            "symbol": normalized_symbol,
            "asset_class": resolved["asset_class"],
            "scope": resolved["scope"],
            "requested_indicators": indicator_names,
            "synced": [],
            "failed": [],
        }
        if reset_existing:
            await self._reset_symbol_indicator_rows(user_id, normalized_symbol)
        for indicator_name in indicator_names:
            try:
                payload = await self.add_user_market_indicator(
                    user_id,
                    indicator_name,
                    value=None,
                    symbol=normalized_symbol,
                    persist_preference=False,
                )
                results["synced"].append({"indicator": indicator_name, "payload": payload.dict()})
            except HTTPException as exc:
                if exc.status_code == 409:
                    results["synced"].append({"indicator": indicator_name, "payload": {"message": str(exc.detail), "duplicate": True}})
                else:
                    results["failed"].append({"indicator": indicator_name, "error": str(exc.detail)})
            except Exception as exc:
                results["failed"].append({"indicator": indicator_name, "error": str(exc)})
        return results

    async def sync_live_price(self, symbol: str) -> dict:
        """Fetches the latest normalized market snapshot and updates market_data."""
        symbol = symbol.upper()
        asset_meta = await AssetCatalogService(self.session).get_asset(symbol)
        asset = AssetRecord(**asset_meta)

        try:
            provider = self.provider_registry.resolve_for_asset(asset)
            snapshot = await provider.fetch_latest_snapshot(asset)
        except Exception as exc:
            logger.error(
                "❌ Kon live prijs voor %s niet ophalen via provider %s: %s",
                symbol,
                asset.primary_provider or asset.provider,
                exc,
            )
            return {"error": "API fout"}

        from backend.infrastructure.models import MarketData
        from datetime import datetime

        new_data = MarketData(
            symbol=symbol,
            price=snapshot.price,
            open=snapshot.open,
            high=snapshot.high,
            low=snapshot.low,
            change_24h=snapshot.change_percent,
            volume=snapshot.volume,
            timestamp=snapshot.observed_at.replace(tzinfo=None) if snapshot.observed_at else datetime.utcnow()
        )
        self.session.add(new_data)
        await self.session.commit()
        return {
            "status": "✅ Live price synced",
            "price": snapshot.price,
            "provider": snapshot.provider,
            "provider_symbol": snapshot.provider_symbol,
        }

    async def get_latest_market_snapshot(self, symbol: str) -> MarketDataResponse:
        normalized_symbol = str(symbol or "").strip().upper()
        if not normalized_symbol:
            raise HTTPException(400, "Symbool is verplicht.")

        snapshot = await self.repository.get_latest_snapshot(normalized_symbol)
        if snapshot:
            return MarketDataResponse.from_orm(snapshot)

        asset_meta = await AssetCatalogService(self.session).get_asset(normalized_symbol)
        asset = AssetRecord(**asset_meta)

        try:
            provider = self.provider_registry.resolve_for_asset(asset)
            live_snapshot = await provider.fetch_latest_snapshot(asset)
        except Exception as exc:
            logger.error(
                "❌ Kon live fallback snapshot voor %s niet ophalen via provider %s: %s",
                normalized_symbol,
                asset.primary_provider or asset.provider,
                exc,
                exc_info=True,
            )
            raise HTTPException(404, f"Geen {normalized_symbol} data gevonden") from exc

        observed_at = live_snapshot.observed_at or datetime.now(timezone.utc)
        return MarketDataResponse(
            id=0,
            symbol=normalized_symbol,
            price=live_snapshot.price,
            open=live_snapshot.open,
            high=live_snapshot.high,
            low=live_snapshot.low,
            change_24h=live_snapshot.change_percent,
            volume=live_snapshot.volume,
            timestamp=observed_at,
        )

    # =========================================================
    # CORE: List / Latest Datasets
    # =========================================================
    async def get_latest_btc_price(self) -> Optional[MarketDataResponse]:
        snapshot = await self.repository.get_latest_snapshot("BTC")
        if not snapshot:
            return None
        return MarketDataResponse.from_orm(snapshot)

    async def get_market_data_list(self, since_minutes: int) -> List[MarketDataResponse]:
        from datetime import timedelta
        time_threshold = datetime.utcnow() - timedelta(minutes=since_minutes)
        records = await self.repository.get_recent_market_data(time_threshold)
        return [MarketDataResponse.from_orm(record) for record in records]

    # =========================================================
    # USER INDICATORS: CRUD
    # =========================================================
    async def add_user_market_indicator(
        self,
        user_id: int,
        raw_name: str,
        value: Optional[float],
        symbol: str = "BTC",
        *,
        persist_preference: bool = True,
    ) -> MarketDataIndicatorResponse:
        symbol = symbol.upper() if symbol else "BTC"
        indicator_name = raw_name.strip()
        if not indicator_name:
            raise HTTPException(400, "❌ Indicator mag niet leeg zijn.")

        asset_scope = await AssetCatalogService(self.session).get_asset(symbol)
        if persist_preference:
            await self.preference_repository.ensure_user_config(
                user_id,
                normalize_indicator_name(indicator_name),
                category="market",
                symbol=symbol,
                asset_class=asset_scope.get("asset_class"),
            )

        exists = await self.repository.check_indicator_exists(indicator_name, user_id, symbol=symbol)
        if exists:
            raise HTTPException(409, f"Indicator '{indicator_name}' is al toegevoegd voor {symbol}.")

        # Bepaal value als deze leeg is
        if value is None:
            snapshot = await self.repository.get_latest_snapshot(symbol)
            if not snapshot:
                asset_meta = await AssetCatalogService(self.session).get_asset(symbol)
                asset = AssetRecord(**asset_meta)
                provider = self.provider_registry.resolve_for_asset(asset)
                live_snapshot = await provider.fetch_latest_snapshot(asset)
                value_by_indicator = {
                    "price": live_snapshot.price,
                    "change_24h": live_snapshot.change_percent,
                    "volume": live_snapshot.volume,
                }
                lname = indicator_name.lower()
                if "price" in lname:
                    value = value_by_indicator["price"]
                elif "change" in lname:
                    value = value_by_indicator["change_24h"]
                elif "volume" in lname:
                    value = value_by_indicator["volume"]
                else:
                    raise HTTPException(
                        400,
                        "❌ Geen 'value' meegegeven en indicator kan niet automatisch "
                        f"worden gemapt voor {symbol}.",
                    )
                if value is None:
                    raise HTTPException(404, f"Geen live {symbol} market_data gevonden.")
            else:
                lname = indicator_name.lower()
                if "price" in lname:
                    value = snapshot.price
                elif "change" in lname:
                    value = snapshot.change_24h
                elif "volume" in lname:
                    value = snapshot.volume
                else:
                    raise HTTPException(
                        400,
                        "❌ Geen 'value' meegegeven en indicator kan niet automatisch "
                        f"worden gemapt voor {symbol}.",
                    )

        try:
            value = float(value)
        except Exception:
            raise HTTPException(400, "❌ 'value' moet numeriek zijn.")

        # Bereken score asynchroon in thread
        normalized = normalize_indicator_name(indicator_name)
        scored = await asyncio.to_thread(sync_score_indicator, "market", normalized, value, int(user_id))

        score = require_indicator_score(scored, indicator_name)
        trend = scored.get("trend") or "neutral"
        interpretation = scored.get("interpretation") or "Geen interpretatie beschikbaar"
        action = scored.get("action") or "Geen actie"

        # Opslaan
        new_record = MarketDataIndicator(
            name=indicator_name,
            value=value,
            trend=trend,
            interpretation=interpretation,
            action=action,
            score=score,
            user_id=user_id,
            symbol=symbol,
            timestamp=datetime.utcnow()
        )
        saved_record = await self.repository.add_market_data_indicator(new_record)
        await self.session.commit()
        await self.session.refresh(saved_record)

        # Onboarding afronden
        from backend.services.onboarding_service import mark_step_completed
        await mark_step_completed(int(user_id), "market", self.session)

        return MarketDataIndicatorResponse.from_orm(saved_record)

    async def list_user_market_indicators(self, user_id: int, symbol: str = "BTC", limit: int = 200) -> List[MarketDataIndicatorResponse]:
        symbol = symbol.upper() if symbol else "BTC"
        records = await self.repository.get_user_market_indicators(user_id, symbol=symbol, limit=limit)
        return [MarketDataIndicatorResponse.from_orm(r) for r in records]

    async def delete_user_market_indicator(self, name: str, user_id: int, symbol: str = "BTC") -> dict:
        symbol = symbol.upper() if symbol else "BTC"
        asset_scope = await AssetCatalogService(self.session).get_asset(symbol)
        await self.preference_repository.remove_user_config(
            user_id,
            normalize_indicator_name(name),
            category="market",
            symbol=symbol,
            asset_class=asset_scope.get("asset_class"),
        )
        deleted = await self.repository.delete_user_market_indicator(name, user_id, symbol=symbol)
        if not deleted:
            raise HTTPException(404, f"Indicator '{name}' niet gevonden voor {symbol}.")
        await self.session.commit()
        return {"message": f"Indicator '{name}' verwijderd voor {symbol}.", "rows_deleted": 1}

    async def get_market_day_data(self, user_id: int, symbol: str = "BTC") -> List[dict]:
        symbol = symbol.upper() if symbol else "BTC"
        records = await self.repository.get_active_day_indicators(user_id, symbol=symbol)
        # Note: In standard response we return dict via Pydantic or manual
        return [MarketDataIndicatorResponse.from_orm(r).dict() for r in records]

    async def get_market_period_data(
        self,
        user_id: int,
        symbol: str = "BTC",
        days: int = 7,
    ) -> List[dict]:
        symbol = symbol.upper() if symbol else "BTC"
        records = await self.repository.get_period_indicators(
            user_id,
            symbol=symbol,
            days=days,
        )
        return [MarketDataIndicatorResponse.from_orm(record).dict() for record in records]

    # =========================================================
    # GLOBAL: Indicators & Rules
    # =========================================================
    async def get_global_indicators(self) -> List[dict]:
        records = await self.repository.get_global_indicators('market')
        return [{"name": r.name, "display_name": r.display_name} for r in records]

    async def get_indicator_rules(self, name: str, user_id: int) -> List[dict]:
        records = await self.repository.get_indicator_rules(name, user_id)
        return [{
            "range_min": r.range_min,
            "range_max": r.range_max,
            "score": r.score,
            "trend": r.trend,
            "interpretation": r.interpretation,
            "action": r.action
        } for r in records]

    # =========================================================
    # 7D Data Fill & Fetch
    # =========================================================
    async def sync_symbol_7day_data(self, symbol: str, overwrite: bool = False) -> dict:
        symbol = symbol.upper()
        mapping = {
            "BTC": "bitcoin",
            "ETH": "ethereum",
            "SOL": "solana"
        }
        coingecko_id = mapping.get(symbol)
        if not coingecko_id:
            return {"error": f"Symbol {symbol} niet ondersteund voor sync"}

        logger.info(f"📥 Sync {symbol} 7d market data gestart (CG ID: {coingecko_id}, overwrite={overwrite})")
        # Use days=14 to get 4-hourly data, which we will aggregate to true daily OHLC
        url_ohlc = f"https://api.coingecko.com/api/v3/coins/{coingecko_id}/ohlc?vs_currency=usd&days=14"
        url_volume = f"https://api.coingecko.com/api/v3/coins/{coingecko_id}/market_chart?vs_currency=usd&days=14"
        
        async with httpx.AsyncClient(timeout=15.0) as client:
            res_ohlc = await client.get(url_ohlc)
            res_vol = await client.get(url_volume)

            if res_ohlc.status_code != 200 or res_vol.status_code != 200:
                logger.error(f"❌ CoinGecko API fout voor {symbol}: OHLC={res_ohlc.status_code}, VOL={res_vol.status_code}")
                return {"error": f"CoinGecko API fout: {res_ohlc.status_code}"}

            ohlc_data = res_ohlc.json()
            volume_data = res_vol.json().get("total_volumes", [])
            
        if not isinstance(ohlc_data, list):
            logger.error(f"❌ Ongeldige OHLC data van CoinGecko voor {symbol}: {ohlc_data}")
            return {"error": "Ongeldige data bron"}

        from datetime import timezone
        volume_by_date = {}
        for ts, vol in volume_data:
            d = datetime.fromtimestamp(ts / 1000, timezone.utc).date()
            if d not in volume_by_date:
                volume_by_date[d] = []
            volume_by_date[d].append(vol)
            
        avg_volume_by_date = {
            d: sum(v)/len(v) for d, v in volume_by_date.items()
        }

        # Aggregate 4-hourly to daily
        daily_ohlc = {}
        for entry in ohlc_data:
            ts, open_p, high_p, low_p, close_p = entry
            d = datetime.fromtimestamp(ts / 1000, timezone.utc).date()
            if d not in daily_ohlc:
                daily_ohlc[d] = {"open": open_p, "high": high_p, "low": low_p, "close": close_p}
            else:
                daily_ohlc[d]["high"] = max(daily_ohlc[d]["high"], high_p)
                daily_ohlc[d]["low"] = min(daily_ohlc[d]["low"], low_p)
                daily_ohlc[d]["close"] = close_p # last close of the day
                
        inserted = 0
        updated = 0
        for d, data in daily_ohlc.items():
            open_p = data["open"]
            high_p = data["high"]
            low_p = data["low"]
            close_p = data["close"]
            change = round((close_p - open_p) / open_p * 100, 2) if open_p else 0
            volume = avg_volume_by_date.get(d)

            existing = await self.repository.get_7d_record(symbol, d)
            if not existing:
                new_7d = MarketData7D(
                    symbol=symbol,
                    date=d,
                    open=open_p,
                    high=high_p,
                    low=low_p,
                    close=close_p,
                    change=change,
                    volume=volume,
                    created_at=datetime.utcnow()
                )
                await self.repository.add_market_data_7d(new_7d)
                inserted += 1
            elif overwrite:
                existing.open = open_p
                existing.high = high_p
                existing.low = low_p
                existing.close = close_p
                existing.change = change
                existing.volume = volume or existing.volume
                existing.created_at = datetime.utcnow()
                updated += 1

        await self.session.commit()
        return {
            "status": f"✅ Sync {symbol} 7D voltooid", 
            "inserted": inserted, 
            "updated": updated
        }

    async def sync_symbol_forward_returns(self, symbol: str) -> dict:
        symbol = symbol.upper()
        support = await self.get_forward_return_support(symbol)
        if not support.get("supported"):
            return {
                "status": "unsupported",
                "symbol": symbol,
                "reason": support.get("reason") or "unsupported_symbol",
            }

        asset_meta = await AssetCatalogService(self.session).get_asset(symbol)
        asset = AssetRecord(**asset_meta)

        logger.info(
            "📥 Sync %s forward returns gestart via %s",
            symbol,
            support["source"],
        )

        if support["source"] == "binance":
            daily_prices = await self._load_binance_forward_prices(asset)
        elif support["source"] == "twelve_data":
            daily_prices = await self._load_twelve_data_forward_prices(asset)
        else:
            raise ValueError(f"Onbekende forward return source voor {symbol}: {support['source']}")

        sorted_dates = sorted(daily_prices.keys())
        if not sorted_dates:
            return {
                "status": "empty",
                "symbol": symbol,
                "source": support["source"],
                "reason": "no_price_history",
            }

        groups = {
            "7d": defaultdict(list),
            "30d": defaultdict(list),
            "90d": defaultdict(list),
            "365d": defaultdict(list)
        }
        
        for d in sorted_dates:
            p = daily_prices[d]
            iso_year, iso_week, _ = d.isocalendar()
            quarter = (d.month - 1) // 3 + 1
            
            groups["7d"][(iso_year, iso_week)].append((d, p))
            groups["30d"][(d.year, d.month)].append((d, p))
            groups["90d"][(d.year, quarter)].append((d, p))
            groups["365d"][(d.year, 1)].append((d, p))
            
        from backend.infrastructure.models import MarketForwardReturn
        
        # Oude data wissen
        from sqlalchemy import delete
        await self.session.execute(
            delete(MarketForwardReturn).where(MarketForwardReturn.symbol == symbol)
        )
        
        inserted = 0
        for period, group_data in groups.items():
            for key, items in group_data.items():
                items.sort(key=lambda x: x[0])
                start_d, start_p = items[0]
                end_d, end_p = items[-1]
                change = (end_p - start_p) / start_p * 100 if start_p > 0 else 0
                
                # Start date as datetime for DB
                start_dt = datetime(start_d.year, start_d.month, start_d.day)
                end_dt = datetime(end_d.year, end_d.month, end_d.day)
                
                new_ret = MarketForwardReturn(
                    symbol=symbol,
                    period=period,
                    start_date=start_dt,
                    end_date=end_dt,
                    change=round(change, 2),
                    avg_daily=round(change / max((end_d - start_d).days, 1), 3),
                    created_at=datetime.utcnow()
                )
                self.session.add(new_ret)
                inserted += 1

        await self.session.commit()
        return {
            "status": "✅ Forward Returns gegenereerd",
            "symbol": symbol,
            "source": support["source"],
            "inserted": inserted,
            "history_start": sorted_dates[0].isoformat(),
            "history_end": sorted_dates[-1].isoformat(),
        }

    async def fill_btc_7day_data(self, fallback_endpoints: dict = None, overwrite: bool = False) -> dict:
        """Legacy wrapper for BTC."""
        return await self.sync_symbol_7day_data("BTC", overwrite)

    async def get_market_data_7d(self, symbol: str = "BTC") -> List[MarketData7DResponse]:
        records = await self.repository.get_market_data_7d(symbol.upper())
        resp = [MarketData7DResponse.from_orm(r) for r in records]
        resp.reverse()
        return resp

    # =========================================================
    # Forward Returns
    # =========================================================
    async def get_market_forward_returns(self, symbol: str = "BTC") -> List[MarketForwardReturnResponse]:
        symbol = symbol.upper()
        support = await self.ensure_forward_returns_ready(symbol)
        if not support.get("supported"):
            return []
        records = await self.repository.get_forward_returns(symbol)
        return [MarketForwardReturnResponse.from_orm(r) for r in records]

    async def get_forward_returns_aggregated(self, period: str, symbol: str = "BTC") -> List[ForwardReturnChartResponse]:
        symbol = symbol.upper()
        support = await self.ensure_forward_returns_ready(symbol)
        if not support.get("supported"):
            return []

        records = await self.repository.get_forward_returns_by_period(symbol, period)
        
        if period == '7d':
             data = defaultdict(lambda: [None] * 53)
             for r in records:
                 week_index = max(min(r.start_date.isocalendar().week - 1, 52), 0)
                 data[r.start_date.year][week_index] = float(r.change or 0)
             return [ForwardReturnChartResponse(year=y, values=v) for y, v in sorted(data.items())]

        elif period == '30d':
             data = defaultdict(lambda: [None] * 12)
             for r in records:
                 data[r.start_date.year][r.start_date.month - 1] = float(r.change or 0)
             return [ForwardReturnChartResponse(year=y, values=v) for y, v in sorted(data.items())]

        elif period == '90d':
             data = defaultdict(lambda: [None] * 4)
             for r in records:
                 data[r.start_date.year][(r.start_date.month - 1) // 3] = float(r.change or 0)
             return [ForwardReturnChartResponse(year=y, values=v) for y, v in sorted(data.items())]

        elif period == '365d':
             data = defaultdict(lambda: [None])
             for r in records:
                 data[r.start_date.year][0] = float(r.change or 0)
             return [ForwardReturnChartResponse(year=y, values=v) for y, v in sorted(data.items())]

        return []  # default / fallback

    # =========================================================
    # Interpreted Data
    # =========================================================
    async def get_interpreted_data(self, user_id: int, symbol: str = "BTC") -> dict:
        symbol = symbol.upper()
        snapshot = await self.repository.get_latest_snapshot(symbol)
        if not snapshot:
            raise HTTPException(404, f"Geen {symbol} data gevonden.")

        scores = await asyncio.to_thread(sync_get_scores_for_symbol, int(user_id), symbol)

        return {
            "symbol": snapshot.symbol,
            "timestamp": snapshot.timestamp.isoformat(),
            "price": float(snapshot.price or 0.0),
            "change_24h": float(snapshot.change_24h or 0.0),
            "volume": float(snapshot.volume or 0.0),
            "score": scores.get("market_score", 10) or 10,
            "top_contributors": scores.get("market_top_contributors", []),
            "interpretation": scores.get("market_interpretation", "Geen interpretatie"),
            "action": f"Market-score voor {symbol} is globaal, advies is informatief.",
        }
