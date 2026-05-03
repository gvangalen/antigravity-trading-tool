import asyncio
import logging
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from backend.infrastructure.models import MacroData
from backend.infrastructure.repositories.macro_data_repository import MacroDataRepository
from backend.schemas.macro_data_schema import (
    MacroDataResponse, MacroAggregateResponse, MacroAddResponse, MacroIndicatorNamesResponse, MacroIndicatorRuleResponse
)

logger = logging.getLogger(__name__)

class MacroDataService:
    # 🕒 Global cache for heavy aggregations
    _cache = {}
    _CACHE_TTL = 60

    def __init__(self, session: AsyncSession):
        self.session = session
        self.repository = MacroDataRepository(session)

    # =========================================================
    # Fallback sync wrappers
    # =========================================================
    def _sync_fetch_macro_value(self, name: str, source: str, link: str):
        from backend.utils.macro_interpreter import fetch_macro_value
        return fetch_macro_value(name, source=source, link=link)

    def _sync_score_indicator(self, category: str, indicator: str, value: float, user_id: int):
        from backend.utils.db import get_db_connection
        from backend.utils.scoring_engine import score_indicator
        
        conn = get_db_connection()
        if not conn:
            return {}
        try:
            return score_indicator(conn=conn, category=category, indicator=indicator, value=value, user_id=user_id)
        finally:
            conn.close()

    async def _mark_onboarding(self, user_id: int, step: str):
        from backend.services.onboarding_service import mark_step_completed
        await mark_step_completed(user_id, step, self.session)

    # =========================================================
    # USER INDICATORS: CRUD
    # =========================================================
    async def add_macro_indicator(self, user_id: int, raw_name: str, payload_value: Optional[float], symbol: Optional[str] = None) -> MacroAddResponse:
        indicator_name = raw_name.strip()
        if not indicator_name:
            raise HTTPException(400, "❌ Indicator mag niet leeg zijn.")

        # Check of indicator al bestaat voor deze user (Macro is Global Pool)
        exists = await self.repository.check_indicator_exists(user_id, indicator_name)
        if exists:
            raise HTTPException(409, f"Indicator '{indicator_name}' is al toegevoegd voor deze gebruiker.")

        # Get config
        info = await self.repository.get_indicator_info(indicator_name)
        if not info:
            raise HTTPException(404, f"Indicator '{indicator_name}' bestaat niet of is inactief.")

        # Get value
        value = payload_value
        if value is None:
            # Dynamically fetch
            try:
                result = await asyncio.to_thread(self._sync_fetch_macro_value, indicator_name, info.source, info.link)
                if not result:
                    raise HTTPException(500, f"Geen waarde ontvangen voor '{indicator_name}'")
                
                if isinstance(result, dict):
                    if "value" in result:
                        value = float(result["value"])
                    elif "data" in result and "value" in result["data"]:
                        value = float(result["data"]["value"])
                    elif "result" in result:
                        value = float(result["result"])
                    else:
                        raise HTTPException(500, f"Kan waarde niet parsen: {result}")
                else:
                    value = float(result)
            except HTTPException:
                raise
            except Exception as e:
                logger.error(f"Error fetching value macro: {e}")
                raise HTTPException(500, f"Fout bij ophalen dynamische waarde.")

        # Score the value
        from backend.utils.scoring_utils import normalize_indicator_name
        normalized = normalize_indicator_name(indicator_name)

        scored = await asyncio.to_thread(self._sync_score_indicator, "macro", normalized, value, user_id)
        score = scored.get("score", 10.0)
        trend = scored.get("trend") or "neutral"
        interpretation = scored.get("interpretation") or "Geen interpretatie beschikbaar"
        action = scored.get("action") or "Geen actie"

        record = MacroData(
            name=indicator_name,
            value=value,
            trend=trend,
            interpretation=interpretation,
            action=action,
            score=score,
            symbol=symbol,
            user_id=user_id
        )
        saved_record = await self.repository.add_macro_data(record)

        # Mark onboarding
        await self._mark_onboarding(user_id, "macro")

        return MacroAddResponse(
            message=f"Indicator '{indicator_name}' opgeslagen.",
            value=value,
            score=score,
            trend=trend,
            interpretation=interpretation,
            action=action,
            symbol=symbol
        )

    # =========================================================
    # QUERIES
    # =========================================================
    async def get_macro_indicators(self, user_id: int, symbol: Optional[str] = None) -> List[MacroDataResponse]:
        records = await self.repository.get_user_macro_data(user_id)
        return [MacroDataResponse.from_orm(r) for r in records]

    async def get_latest_macro_day_data(self, user_id: int, symbol: Optional[str] = None) -> List[MacroDataResponse]:
        records = await self.repository.get_active_day_macro_data(user_id)
        return [MacroDataResponse.from_orm(r) for r in records]

    async def get_macro_week_data(self, user_id: int, symbol: Optional[str] = "BTC") -> List[MacroAggregateResponse]:
        records = await self.repository.get_macro_week_data(user_id, symbol)
        return [
            MacroAggregateResponse(
                indicator=r.name,
                waarde=r.value,
                trend=r.trend,
                interpretation=r.interpretation,
                action=r.action,
                score=r.score,
                timestamp=r.timestamp
            ) for r in records
        ]

    async def get_macro_month_data(self, user_id: int, symbol: Optional[str] = "BTC") -> List[MacroAggregateResponse]:
        records = await self.repository.get_macro_month_data(user_id, symbol)
        return [
            MacroAggregateResponse(
                indicator=r.name,
                waarde=r.value,
                trend=r.trend,
                interpretation=r.interpretation,
                action=r.action,
                score=r.score,
                timestamp=r.timestamp
            ) for r in records
        ]

    async def get_macro_quarter_data(self, user_id: int, symbol: Optional[str] = "BTC") -> List[MacroAggregateResponse]:
        records = await self.repository.get_macro_quarter_data(user_id, symbol)
        return [
            MacroAggregateResponse(
                indicator=r.name,
                waarde=r.value,
                trend=r.trend,
                interpretation=r.interpretation,
                action=r.action,
                score=r.score,
                timestamp=r.timestamp
            ) for r in records
        ]

    # =========================================================
    # RULES & CONFIG
    # =========================================================
    async def get_all_macro_indicators(self) -> List[MacroIndicatorNamesResponse]:
        records = await self.repository.get_global_indicators()
        return [MacroIndicatorNamesResponse(name=r.name, display_name=r.display_name) for r in records]

    async def get_rules_for_macro_indicator(self, name: str, user_id: int) -> List[MacroIndicatorRuleResponse]:
        records = await self.repository.get_indicator_rules(name, user_id)
        return [MacroIndicatorRuleResponse.from_orm(r) for r in records]

    async def delete_macro_indicator(self, name: str, user_id: int, symbol: Optional[str] = None) -> dict:
        deleted = await self.repository.delete_user_macro_indicator(name, user_id)
        if not deleted:
            raise HTTPException(404, f"Indicator '{name}' niet gevonden voor deze gebruiker.")
        return {"message": f"Indicator '{name}' verwijderd.", "rows_deleted": 1}
