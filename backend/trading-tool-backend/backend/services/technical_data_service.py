import asyncio
import logging
from typing import Dict, Any, List, Optional

from sqlalchemy.ext.asyncio import AsyncSession
from backend.infrastructure.repositories.technical_data_repository import TechnicalDataRepository
from backend.schemas.market_provider_schema import AssetRecord
from backend.services.asset_catalog_service import AssetCatalogService
from backend.services.technical_indicator_provider_registry import TechnicalIndicatorProviderRegistry
from backend.utils.technical_interpreter import fetch_technical_value
from backend.utils.technical_interpreter import normalize_technical_value
from backend.utils.scoring_engine import score_indicator
from backend.utils.scoring_utils import normalize_indicator_name
from backend.utils.db import get_db_connection
from backend.services.onboarding_service import mark_step_completed
from backend.utils.indicator_score_validation import require_indicator_score

logger = logging.getLogger(__name__)

class TechnicalDataService:
    RECOMMENDED_ASSET_CLASS_PRESETS: dict[str, list[str]] = {
        "crypto": ["rsi", "ma_200"],
        "stock": ["rsi", "ema_20_gap_pct", "macd_hist_pct"],
        "etf": ["rsi", "ema_20_gap_pct", "macd_hist_pct"],
        "index": ["rsi", "ema_20_gap_pct", "macd_hist_pct"],
        "forex": ["rsi"],
        "commodity": ["rsi"],
    }

    def __init__(self, session: AsyncSession):
        self.session = session
        self.repository = TechnicalDataRepository(session)
        self.provider_registry = TechnicalIndicatorProviderRegistry()

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
        normalized_symbol, normalized_asset_class = await self._resolve_asset_scope(
            symbol=symbol,
            asset_class=asset_class,
        )

        if normalized_symbol:
            symbol_rows = await self.repository.list_scope_configs(
                user_id,
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
            class_rows = await self.repository.list_scope_configs(
                user_id,
                asset_class=normalized_asset_class,
            )
            if class_rows:
                return {
                    "scope": "asset_class_override",
                    "symbol": normalized_symbol,
                    "asset_class": normalized_asset_class,
                    "rows": class_rows,
                }

        default_rows = await self.repository.list_scope_configs(user_id)
        return {
            "scope": "default",
            "symbol": normalized_symbol,
            "asset_class": normalized_asset_class,
            "rows": default_rows,
        }

    async def bootstrap_preferences(
        self,
        user_id: int,
        *,
        symbol: Optional[str] = None,
        asset_class: Optional[str] = None,
        scope: str = "asset_class",
        preset: str = "recommended",
    ) -> Dict[str, Any]:
        normalized_symbol, normalized_asset_class = await self._resolve_asset_scope(
            symbol=symbol,
            asset_class=asset_class,
        )
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

        indicator_names = self._recommended_indicator_names(preset_key)
        normalized_items = await self._build_scope_items(indicator_names)
        if not normalized_items:
            raise ValueError(f"Geen bruikbare indicatoren gevonden voor preset '{normalized_preset}'.")

        rows = await self.repository.replace_scope_configs(
            user_id,
            normalized_items,
            symbol=target_symbol,
            asset_class=target_asset_class,
        )
        return {
            "scope": "symbol_override" if target_symbol else ("asset_class_override" if target_asset_class else "default"),
            "symbol": target_symbol,
            "asset_class": target_asset_class,
            "rows": rows,
        }

    def _recommended_indicator_names(self, preset_key: Optional[str]) -> List[str]:
        normalized_key = str(preset_key or "").strip().lower()
        if normalized_key == "default":
            return ["rsi"]
        return list(self.RECOMMENDED_ASSET_CLASS_PRESETS.get(normalized_key, ["rsi"]))

    async def _build_scope_items(self, indicator_names: List[str]) -> List[tuple[str, int]]:
        items: List[tuple[str, int]] = []
        seen: set[str] = set()

        for priority, indicator_name in enumerate(indicator_names, start=1):
            normalized_name = normalize_indicator_name(indicator_name)
            if normalized_name in seen:
                continue

            cfg = await self.repository.get_indicator_config(normalized_name)
            if not cfg:
                logger.warning("⚠️ Indicator '%s' ontbreekt in indicators tabel en wordt overgeslagen.", normalized_name)
                continue

            items.append((normalized_name, priority))
            seen.add(normalized_name)

        return items

    async def add_technical_indicator(self, name_raw: str, user_id: int, symbol: str = "BTC") -> Dict[str, Any]:
        return await self._add_technical_indicator(
            name_raw,
            user_id,
            symbol=symbol,
            persist_preference=True,
        )

    async def sync_effective_indicators(
        self,
        user_id: int,
        symbol: str,
        *,
        persist_preferences: bool = False,
        explicit_indicators: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        resolved_preferences = await self.resolve_effective_preferences(user_id, symbol=symbol)
        asset_class = resolved_preferences["asset_class"]

        if explicit_indicators is not None:
            indicator_names = [normalize_indicator_name(name) for name in explicit_indicators if str(name or "").strip()]
            scope = "explicit"
        else:
            configs = resolved_preferences["rows"]
            indicator_names = [normalize_indicator_name(row.indicator) for row in configs]
            scope = resolved_preferences["scope"]

        results: Dict[str, Any] = {
            "symbol": symbol.upper(),
            "asset_class": asset_class,
            "scope": scope,
            "requested_indicators": indicator_names,
            "synced": [],
            "failed": [],
        }

        for indicator_name in indicator_names:
            try:
                payload = await self._add_technical_indicator(
                    indicator_name,
                    user_id,
                    symbol=symbol,
                    persist_preference=persist_preferences,
                )
                results["synced"].append({"indicator": indicator_name, "payload": payload})
            except Exception as exc:
                results["failed"].append({"indicator": indicator_name, "error": str(exc)})

        return results

    async def _fetch_indicator_value(
        self,
        *,
        name: str,
        source: str | None,
        link: str | None,
        symbol: str,
    ) -> dict[str, Any] | None:
        asset_meta = await AssetCatalogService(self.session).get_asset(symbol)
        asset = AssetRecord(**asset_meta)
        provider = self.provider_registry.resolve_for_asset(asset, name)
        if provider is not None:
            value = await provider.fetch_indicator_value(asset, name)
            return {"value": value}

        if isinstance(source, str) and source.strip().lower() == "twelve_data":
            raise ValueError(
                f"Indicator '{name}' wordt momenteel niet ondersteund voor asset class '{asset.asset_class}' ({symbol})."
            )
        if isinstance(link, str) and link.strip().lower().startswith("twelve_data:"):
            raise ValueError(
                f"Indicator '{name}' wordt momenteel niet ondersteund voor asset class '{asset.asset_class}' ({symbol})."
            )

        return await fetch_technical_value(
            name=name,
            source=source,
            link=link,
            symbol=symbol,
        )

    async def _add_technical_indicator(
        self,
        name_raw: str,
        user_id: int,
        *,
        symbol: str = "BTC",
        persist_preference: bool = True,
    ) -> Dict[str, Any]:
        name = normalize_indicator_name(name_raw)
        asset_scope = await AssetCatalogService(self.session).get_asset(symbol)

        if persist_preference:
            await self.repository.ensure_user_config(
                user_id,
                name,
                symbol=symbol,
                asset_class=asset_scope.get("asset_class"),
            )

        cfg = await self.repository.get_indicator_config(name)
        if not cfg:
            raise ValueError(f"Indicator '{name}' niet gevonden of niet actief.")

        result = await self._fetch_indicator_value(
            name=name,
            source=cfg.source,
            link=cfg.link,
            symbol=symbol,
        )
        if not result:
            raise ValueError(f"Geen waarde ontvangen voor '{name}' ({symbol}).")

        val = float(result["value"] if isinstance(result, dict) else result)

        def _score_fallback() -> Dict[str, Any]:
            conn = get_db_connection()
            if not conn:
                raise RuntimeError("Geen database verbinding voor scoring engine.")
            try:
                normalized = normalize_indicator_name(name)
                normalized_value = normalize_technical_value(normalized, val)
                return score_indicator(
                    conn=conn,
                    category="technical",
                    indicator=normalized,
                    value=normalized_value,
                    user_id=user_id,
                )
            finally:
                conn.close()

        scored = await asyncio.to_thread(_score_fallback)
        score = require_indicator_score(scored, name)
        advies = scored.get("trend") or "neutral"
        uitleg = scored.get("interpretation") or "Geen interpretatie beschikbaar"

        new_ind = await self.repository.add_indicator(
            name=name,
            value=val,
            score=score,
            advies=advies,
            uitleg=uitleg,
            user_id=user_id,
            symbol=symbol,
        )
        await mark_step_completed(user_id, "technical", self.session)

        return {
            "message": f"Indicator '{name}' toegevoegd.",
            "id": new_ind.id,
            "value": float(new_ind.value),
            "score": float(new_ind.score),
            "advies": new_ind.advies,
            "uitleg": new_ind.uitleg,
        }

    async def get_indicators(self, user_id: int, symbol: Optional[str] = None) -> List[Any]:
        return await self.repository.get_latest_for_user(user_id, symbol)

    async def get_day_indicators(self, user_id: int, symbol: Optional[str] = None) -> List[Any]:
        return await self.repository.get_day_data(user_id, symbol)

    async def delete_indicator(self, name_raw: str, user_id: int, symbol: Optional[str] = None) -> int:
        name = normalize_indicator_name(name_raw)
        asset_scope = await AssetCatalogService(self.session).get_asset(symbol or "BTC") if symbol else None
        await self.repository.remove_user_config(
            user_id,
            name,
            symbol=symbol,
            asset_class=(asset_scope or {}).get("asset_class"),
        )
        return await self.repository.delete_indicator(name, user_id, symbol)

    async def get_indicator_rules(self, name_raw: str, user_id: int) -> List[Any]:
        name = normalize_indicator_name(name_raw)
        return await self.repository.get_rules_for_indicator(name, user_id)
