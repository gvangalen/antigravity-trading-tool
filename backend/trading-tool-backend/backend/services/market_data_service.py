from typing import Optional, List, Dict, Any
from datetime import datetime, date
from collections import defaultdict
import asyncio
import httpx
import logging

from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import HTTPException

from backend.infrastructure.repositories.market_data_repository import MarketDataRepository
from backend.schemas.market_data_schema import (
    MarketDataResponse, MarketDataIndicatorResponse, MarketData7DResponse,
    MarketForwardReturnResponse, ForwardReturnChartResponse
)
from backend.infrastructure.models import MarketDataIndicator, MarketData7D
from backend.utils.scoring_utils import normalize_indicator_name

logger = logging.getLogger(__name__)

# =========================================================
# SYNCHRONOUS WRAPPERS FOR LEGACY COMPONENTS
# =========================================================
def sync_score_indicator(category: str, indicator: str, value: float, user_id: int) -> Dict[str, Any]:
    from backend.utils.db import get_db_connection
    from backend.utils.scoring_engine import score_indicator
    conn = get_db_connection()
    try:
        if not conn:
            return {"score": 10, "trend": "neutral", "interpretation": "Geen DB", "action": "Geen actie"}
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
    async def add_user_market_indicator(self, user_id: int, raw_name: str, value: Optional[float], symbol: str = "BTC") -> MarketDataIndicatorResponse:
        symbol = symbol.upper() if symbol else "BTC"
        indicator_name = raw_name.strip()
        if not indicator_name:
            raise HTTPException(400, "❌ Indicator mag niet leeg zijn.")

        exists = await self.repository.check_indicator_exists(indicator_name, user_id, symbol=symbol)
        if exists:
            raise HTTPException(409, f"Indicator '{indicator_name}' is al toegevoegd voor {symbol}.")

        # Bepaal value als deze leeg is
        if value is None:
            snapshot = await self.repository.get_latest_snapshot(symbol)
            if not snapshot:
                raise HTTPException(404, f"Geen globale {symbol} market_data gevonden.")
            
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

        score = scored.get("score", 10)
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
        # Binance uses symbols like BTCUSDT, SOLUSDT
        binance_symbol = f"{symbol}USDT"

        logger.info(f"📥 Sync {symbol} forward returns gestart via Binance API")
        
        from datetime import datetime, timezone
        from collections import defaultdict
        
        all_prices = []
        end_time = int(datetime.now(timezone.utc).timestamp() * 1000)
        
        async with httpx.AsyncClient(timeout=15.0) as client:
            # We want up to 11 years of data (4000 days). Binance gives max 1000 per request.
            for _ in range(4):
                url = f"https://api.binance.com/api/v3/klines?symbol={binance_symbol}&interval=1d&limit=1000&endTime={end_time}"
                res = await client.get(url)
                if res.status_code != 200:
                    logger.error(f"❌ Binance API fout voor {symbol}: {res.status_code}")
                    break
                    
                klines = res.json()
                if not klines:
                    break
                    
                chunk_prices = []
                for k in klines:
                    ts = k[0]
                    close_price = float(k[4])
                    chunk_prices.append((ts, close_price))
                    
                # Prepend because we are going backwards in time chunk by chunk
                all_prices = chunk_prices + all_prices
                
                # Next end_time is the open time of the first kline in this chunk minus 1 ms
                end_time = klines[0][0] - 1
                
                if len(klines) < 1000:
                    break
                    
        if not all_prices:
            return {"error": "Geen prijs data gevonden op Binance"}

        daily_prices = {}
        for ts, price in all_prices:
            d = datetime.fromtimestamp(ts/1000, timezone.utc).date()
            daily_prices[d] = price
            
        sorted_dates = sorted(daily_prices.keys())
        if not sorted_dates:
            return {"error": "Geen prijs data"}

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
        return {"status": f"✅ Forward Returns gegenereerd", "inserted": inserted}

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
        records = await self.repository.get_forward_returns(symbol.upper())
        return [MarketForwardReturnResponse.from_orm(r) for r in records]

    async def get_forward_returns_aggregated(self, period: str, symbol: str = "BTC") -> List[ForwardReturnChartResponse]:
        records = await self.repository.get_forward_returns_by_period(symbol.upper(), period)
        
        if period == '7d':
             data = defaultdict(lambda: [None] * 53)
             for r in records:
                 data[r.start_date.year][int(r.start_date.strftime("%U"))] = float(r.change or 0)
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
