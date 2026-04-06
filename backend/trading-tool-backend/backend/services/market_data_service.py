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

def sync_get_scores_for_symbol(user_id: int) -> Dict[str, Any]:
    from backend.utils.scoring_utils import get_scores_for_symbol
    return get_scores_for_symbol(user_id=user_id, include_metadata=True)



class MarketDataService:
    def __init__(self, db_session: AsyncSession):
        self.session = db_session
        self.repository = MarketDataRepository(db_session)

    # =========================================================
    # CORE: List / Latest Datasets
    # =========================================================
    async def get_latest_btc_price(self) -> Optional[MarketDataResponse]:
        snapshot = await self.repository.get_latest_btc_snapshot()
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
    async def add_user_market_indicator(self, user_id: int, raw_name: str, value: Optional[float]) -> MarketDataIndicatorResponse:
        indicator_name = raw_name.strip()
        if not indicator_name:
            raise HTTPException(400, "❌ Indicator mag niet leeg zijn.")

        exists = await self.repository.check_indicator_exists(indicator_name, user_id)
        if exists:
            raise HTTPException(409, f"Indicator '{indicator_name}' is al toegevoegd.")

        # Bepaal value als deze leeg is
        if value is None:
            snapshot = await self.repository.get_latest_btc_snapshot()
            if not snapshot:
                raise HTTPException(404, "Geen globale BTC market_data gevonden.")
            
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
                    "worden gemapt op price/change_24h/volume.",
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
            timestamp=datetime.utcnow()
        )
        saved_record = await self.repository.add_market_data_indicator(new_record)
        await self.session.commit()
        await self.session.refresh(saved_record)

        # Onboarding afronden
        from backend.services.onboarding_service import mark_step_completed
        await mark_step_completed(int(user_id), "market", self.session)

        return MarketDataIndicatorResponse.from_orm(saved_record)

    async def list_user_market_indicators(self, user_id: int, limit: int) -> List[MarketDataIndicatorResponse]:
        records = await self.repository.get_user_market_indicators(user_id, limit)
        return [MarketDataIndicatorResponse.from_orm(r) for r in records]

    async def delete_user_market_indicator(self, name: str, user_id: int) -> dict:
        deleted = await self.repository.delete_user_market_indicator(name, user_id)
        if not deleted:
            raise HTTPException(404, f"Indicator '{name}' niet gevonden voor deze gebruiker.")
        await self.session.commit()
        return {"message": f"Indicator '{name}' verwijderd.", "rows_deleted": 1}

    async def get_market_day_data(self, user_id: int) -> List[dict]:
        records = await self.repository.get_active_day_indicators(user_id)
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
    async def fill_btc_7day_data(self, fallback_endpoints: dict) -> dict:
        logger.info("📥 Handmatig ophalen BTC 7d market data gestart")
        coingecko_id = "bitcoin"
        url_ohlc = f"https://api.coingecko.com/api/v3/coins/{coingecko_id}/ohlc?vs_currency=usd&days=7"
        url_volume = fallback_endpoints.get(
            "btc_volume",
            f"https://api.coingecko.com/api/v3/coins/{coingecko_id}/market_chart?vs_currency=usd&days=7"
        )
        
        async with httpx.AsyncClient(timeout=10.0) as client:
            res_ohlc = await client.get(url_ohlc)
            res_vol = await client.get(url_volume)

            ohlc_data = res_ohlc.json()
            volume_data = res_vol.json().get("total_volumes", [])

        volume_by_date = {
            datetime.utcfromtimestamp(ts / 1000).date(): vol
            for ts, vol in volume_data
        }

        inserted = 0
        for entry in ohlc_data:
            ts, open_p, high_p, low_p, close_p = entry
            d = datetime.utcfromtimestamp(ts / 1000).date()
            change = round((close_p - open_p) / open_p * 100, 2)
            volume = volume_by_date.get(d)

            exists = await self.repository.check_7d_data_exists("BTC", d)
            if not exists:
                new_7d = MarketData7D(
                    symbol="BTC",
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

        await self.session.commit()
        return {"status": f"✅ Gegevens opgeslagen voor {inserted} dagen."}

    async def get_market_data_7d(self) -> List[MarketData7DResponse]:
        records = await self.repository.get_market_data_7d("BTC")
        # Origin returns reverse (oud -> nieuw)
        resp = [MarketData7DResponse.from_orm(r) for r in records]
        resp.reverse()
        return resp

    # =========================================================
    # Forward Returns
    # =========================================================
    async def get_market_forward_returns(self) -> List[MarketForwardReturnResponse]:
        records = await self.repository.get_forward_returns("BTC")
        return [MarketForwardReturnResponse.from_orm(r) for r in records]

    async def get_forward_returns_aggregated(self, period: str) -> List[ForwardReturnChartResponse]:
        records = await self.repository.get_forward_returns_by_period("BTC", period)
        
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
    async def get_interpreted_data(self, user_id: int) -> dict:
        snapshot = await self.repository.get_latest_btc_snapshot()
        if not snapshot:
            raise HTTPException(404, "Geen BTC data gevonden.")

        scores = await asyncio.to_thread(sync_get_scores_for_symbol, int(user_id))

        return {
            "symbol": snapshot.symbol,
            "timestamp": snapshot.timestamp.isoformat(),
            "price": float(snapshot.price or 0.0),
            "change_24h": float(snapshot.change_24h or 0.0),
            "volume": float(snapshot.volume or 0.0),
            "score": scores.get("market_score", 10) or 10,
            "top_contributors": scores.get("market_top_contributors", []),
            "interpretation": scores.get("market_interpretation", "Geen interpretatie"),
            "action": "Market-score is globaal, advies is informatief.",
        }
