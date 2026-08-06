import asyncio
import logging
from typing import List, Optional, Dict, Any

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from backend.infrastructure.models import MacroData
from backend.infrastructure.repositories.technical_data_repository import TechnicalDataRepository
from backend.infrastructure.repositories.macro_data_repository import MacroDataRepository
from backend.schemas.macro_data_schema import (
    MacroDataResponse, MacroAggregateResponse, MacroAddResponse, MacroIndicatorNamesResponse, MacroIndicatorRuleResponse
)
from backend.utils.indicator_score_validation import require_indicator_score
from backend.utils.scoring_utils import normalize_indicator_name
from backend.services.asset_catalog_service import AssetCatalogService

logger = logging.getLogger(__name__)


def _extract_numeric_result(result: Any) -> float:
    if result is None:
        raise ValueError("Lege macro response ontvangen.")

    if isinstance(result, dict):
        candidates = [
            result.get("value"),
            result.get("result"),
            (result.get("data") or {}).get("value") if isinstance(result.get("data"), dict) else None,
        ]
        for candidate in candidates:
            if candidate in ("", ".", None):
                continue
            return float(candidate)
        raise ValueError(f"Macro response bevat geen bruikbare waarde: {result}")

    return float(result)

class MacroDataService:
    RECOMMENDED_ASSET_CLASS_PRESETS: dict[str, list[str]] = {
        "crypto": ["fear_greed_index", "btc_dominance", "dxy"],
        "stock": ["dxy", "fear_greed_index"],
        "etf": ["dxy", "fear_greed_index"],
        "index": ["dxy", "fear_greed_index"],
        "forex": ["dxy", "fear_greed_index"],
        "commodity": ["dxy", "fear_greed_index", "oil_price"],
    }

    def __init__(self, session: AsyncSession):
        self.session = session
        self.repository = MacroDataRepository(session)
        self.preference_repository = TechnicalDataRepository(session)

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
                category="macro",
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
                category="macro",
                asset_class=normalized_asset_class,
            )
            if class_rows:
                return {
                    "scope": "asset_class_override",
                    "symbol": normalized_symbol,
                    "asset_class": normalized_asset_class,
                    "rows": class_rows,
                }

        default_rows = await self.preference_repository.list_scope_configs(user_id, category="macro")
        return {
            "scope": "default",
            "symbol": normalized_symbol,
            "asset_class": normalized_asset_class,
            "rows": default_rows,
        }

    async def _build_scope_items(self, indicator_names: List[str]) -> List[tuple[str, int]]:
        items: List[tuple[str, int]] = []
        seen: set[str] = set()
        for priority, indicator_name in enumerate(indicator_names, start=1):
            normalized_name = normalize_indicator_name(indicator_name)
            if normalized_name in seen:
                continue
            cfg = await self.preference_repository.get_indicator_config(normalized_name, category="macro")
            if not cfg or cfg.category != "macro":
                logger.warning("⚠️ Macro indicator '%s' ontbreekt of heeft verkeerde category.", normalized_name)
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
            preset_key = normalized_asset_class
        elif normalized_scope == "asset_class":
            if not normalized_asset_class:
                raise ValueError("Een asset_class of herleidbaar symbool is verplicht voor scope 'asset_class'.")
            target_symbol = None
            target_asset_class = normalized_asset_class
            preset_key = normalized_asset_class
        elif normalized_scope == "default":
            target_symbol = None
            target_asset_class = None
            preset_key = "default"
        else:
            raise ValueError("Scope moet 'default', 'asset_class' of 'symbol' zijn.")

        indicator_names = ["dxy", "fear_greed_index"] if preset_key == "default" else list(
            self.RECOMMENDED_ASSET_CLASS_PRESETS.get(str(preset_key or "").lower(), ["dxy", "fear_greed_index"])
        )
        normalized_items = await self._build_scope_items(indicator_names)
        rows = await self.preference_repository.replace_scope_configs(
            user_id,
            normalized_items,
            category="macro",
            symbol=target_symbol,
            asset_class=target_asset_class,
        )
        return {
            "scope": "symbol_override" if target_symbol else ("asset_class_override" if target_asset_class else "default"),
            "symbol": target_symbol,
            "asset_class": target_asset_class,
            "rows": rows,
        }

    async def sync_effective_indicators(self, user_id: int, symbol: str) -> Dict[str, Any]:
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
        for indicator_name in indicator_names:
            try:
                payload = await self.add_macro_indicator(
                    user_id,
                    indicator_name,
                    payload_value=None,
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
    async def add_macro_indicator(
        self,
        user_id: int,
        raw_name: str,
        payload_value: Optional[float],
        symbol: Optional[str] = None,
        *,
        persist_preference: bool = True,
    ) -> MacroAddResponse:
        indicator_name = raw_name.strip()
        if not indicator_name:
            raise HTTPException(400, "❌ Indicator mag niet leeg zijn.")

        normalized_symbol = str(symbol or "").strip().upper() or None
        asset_scope = await AssetCatalogService(self.session).get_asset(normalized_symbol or "BTC")
        if persist_preference:
            await self.preference_repository.ensure_user_config(
                user_id,
                normalize_indicator_name(indicator_name),
                category="macro",
                symbol=normalized_symbol,
                asset_class=asset_scope.get("asset_class"),
            )

        exists = await self.repository.check_indicator_exists(user_id, indicator_name, symbol=normalized_symbol)
        if exists:
            raise HTTPException(409, f"Indicator '{indicator_name}' is al toegevoegd voor deze gebruiker en asset.")

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

                value = _extract_numeric_result(result)
            except HTTPException:
                raise
            except Exception as e:
                logger.error("Error fetching value macro for '%s': %s", indicator_name, e)
                raise HTTPException(500, f"Fout bij ophalen dynamische waarde.")

        # Score the value
        normalized = normalize_indicator_name(indicator_name)

        scored = await asyncio.to_thread(self._sync_score_indicator, "macro", normalized, value, user_id)
        score = require_indicator_score(scored, indicator_name)
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
            symbol=normalized_symbol,
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
            symbol=normalized_symbol
        )

    # =========================================================
    # QUERIES
    # =========================================================
    async def get_macro_indicators(self, user_id: int, symbol: Optional[str] = None) -> List[MacroDataResponse]:
        normalized_symbol = str(symbol or "").strip().upper() or None
        records = await self.repository.get_user_macro_data(user_id, symbol=normalized_symbol)
        return [MacroDataResponse.from_orm(r) for r in records]

    async def get_latest_macro_day_data(self, user_id: int, symbol: Optional[str] = None) -> List[MacroDataResponse]:
        normalized_symbol = str(symbol or "").strip().upper() or None
        records = await self.repository.get_active_day_macro_data(user_id, symbol=normalized_symbol)
        return [MacroDataResponse.from_orm(r) for r in records]

    async def get_macro_week_data(self, user_id: int, symbol: Optional[str] = "BTC") -> List[MacroAggregateResponse]:
        normalized_symbol = str(symbol or "").strip().upper() or None
        records = await self.repository.get_macro_week_data(user_id, normalized_symbol)
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
        normalized_symbol = str(symbol or "").strip().upper() or None
        records = await self.repository.get_macro_month_data(user_id, normalized_symbol)
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
        normalized_symbol = str(symbol or "").strip().upper() or None
        records = await self.repository.get_macro_quarter_data(user_id, normalized_symbol)
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
        normalized_symbol = str(symbol or "").strip().upper() or None
        asset_scope = await AssetCatalogService(self.session).get_asset(normalized_symbol or "BTC")
        await self.preference_repository.remove_user_config(
            user_id,
            normalize_indicator_name(name),
            category="macro",
            symbol=normalized_symbol,
            asset_class=asset_scope.get("asset_class"),
        )
        deleted = await self.repository.delete_user_macro_indicator(name, user_id, symbol=normalized_symbol)
        if not deleted:
            raise HTTPException(404, f"Indicator '{name}' niet gevonden voor deze gebruiker.")
        return {"message": f"Indicator '{name}' verwijderd.", "rows_deleted": 1}
