import asyncio
import logging
from typing import Dict, Any, List, Optional
from types import SimpleNamespace

from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import HTTPException
from backend.infrastructure.database import async_session_factory
from backend.domain.technical_indicator_catalog import (
    get_active_technical_indicator_definitions,
    get_technical_indicator_definition,
)
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
    def __init__(self, session: AsyncSession):
        self.session = session
        self.repository = TechnicalDataRepository(session)
        self.provider_registry = TechnicalIndicatorProviderRegistry()

    def _resolve_indicator_config(self, indicator_name: str, db_config: Optional[Any]) -> Optional[Any]:
        catalog_def = get_technical_indicator_definition(indicator_name)
        if catalog_def and catalog_def.get("active"):
            return SimpleNamespace(**catalog_def)
        return db_config

    async def _get_asset_scope(self, symbol: str) -> dict[str, Any]:
        normalized_symbol = str(symbol or "BTC").strip().upper() or "BTC"

        async with async_session_factory() as isolated_session:
            try:
                asset = await AssetCatalogService(isolated_session).get_asset(normalized_symbol)
                await isolated_session.rollback()
                return asset
            except Exception:
                await isolated_session.rollback()
                logger.error(
                    "❌ Technical asset scope lookup failed for %s",
                    normalized_symbol,
                    exc_info=True,
                )
                return AssetCatalogService(self.session)._fallback_asset(normalized_symbol)

    def _score_indicator_with_fallback(self, *, name: str, value: float, user_id: int) -> Dict[str, Any]:
        conn = get_db_connection()
        if not conn:
            raise RuntimeError("Geen database verbinding voor scoring engine.")
        try:
            normalized = normalize_indicator_name(name)
            normalized_value = normalize_technical_value(normalized, value)
            scored = score_indicator(
                conn=conn,
                category="technical",
                indicator=normalized,
                value=normalized_value,
                user_id=user_id,
            )
        finally:
            conn.close()

        try:
            score = require_indicator_score(scored, name)
        except HTTPException as exc:
            if exc.status_code != 422:
                raise
            score = max(0.0, min(100.0, float(normalized_value)))
            if score >= 75:
                trend = "sterk"
                interpretation = "Indicator noteert in de sterke zone op basis van de genormaliseerde Twelve Data-waarde."
                action = "Actie: trend en momentum krijgen extra bevestiging."
            elif score >= 55:
                trend = "constructief"
                interpretation = "Indicator ondersteunt het huidige technische beeld, maar zonder extreme uitslag."
                action = "Actie: bruikbaar als bevestiging naast structuur en context."
            elif score <= 25:
                trend = "zwak"
                interpretation = "Indicator noteert in een zwakke zone op basis van de genormaliseerde Twelve Data-waarde."
                action = "Actie: defensief blijven tot meer bevestiging terugkomt."
            else:
                trend = "neutraal"
                interpretation = "Indicator zit in een gemengde zone en geeft nog geen duidelijke edge."
                action = "Actie: wacht op extra bevestiging uit trend, momentum of prijsstructuur."
            return {
                "score": score,
                "trend": trend,
                "interpretation": interpretation,
                "action": action,
            }

        return {
            "score": score,
            "trend": scored.get("trend") or "neutral",
            "interpretation": scored.get("interpretation") or "Geen interpretatie beschikbaar",
            "action": scored.get("action") or "Geen actie",
        }

    async def _resolve_asset_scope(
        self,
        symbol: Optional[str] = None,
        asset_class: Optional[str] = None,
    ) -> tuple[Optional[str], Optional[str]]:
        normalized_symbol = str(symbol or "").strip().upper() or None
        normalized_asset_class = str(asset_class or "").strip().lower() or None

        if normalized_symbol and not normalized_asset_class:
            asset = await self._get_asset_scope(normalized_symbol)
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

        return {
            "scope": "empty",
            "symbol": normalized_symbol,
            "asset_class": normalized_asset_class,
            "rows": [],
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

        rows = await self.repository.replace_scope_configs(
            user_id,
            [],
            symbol=target_symbol,
            asset_class=target_asset_class,
        )
        return {
            "scope": "symbol_override" if target_symbol else ("asset_class_override" if target_asset_class else "default"),
            "symbol": target_symbol,
            "asset_class": target_asset_class,
            "rows": rows,
        }

    async def _build_scope_items(self, indicator_names: List[str]) -> List[tuple[str, int]]:
        items: List[tuple[str, int]] = []
        seen: set[str] = set()

        for priority, indicator_name in enumerate(indicator_names, start=1):
            normalized_name = normalize_indicator_name(indicator_name)
            if normalized_name in seen:
                continue

            cfg = self._resolve_indicator_config(
                normalized_name,
                await self.repository.get_indicator_config(normalized_name),
            )
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

    async def _reset_symbol_indicator_rows(self, user_id: int, symbol: str) -> None:
        normalized_symbol = str(symbol or "BTC").strip().upper()
        existing_rows = await self.repository.get_day_data(user_id, normalized_symbol)
        seen: set[str] = set()
        for row in existing_rows:
            indicator_name = normalize_indicator_name(getattr(row, "indicator", "") or "")
            if not indicator_name or indicator_name in seen:
                continue
            seen.add(indicator_name)
            await self.repository.delete_indicator(indicator_name, user_id, normalized_symbol)

    async def sync_effective_indicators(
        self,
        user_id: int,
        symbol: str,
        *,
        persist_preferences: bool = False,
        explicit_indicators: Optional[List[str]] = None,
        reset_existing: bool = False,
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
        if reset_existing:
            await self._reset_symbol_indicator_rows(user_id, symbol)

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
        asset_scope = await self._get_asset_scope(symbol)

        if persist_preference:
            await self.repository.ensure_user_config(
                user_id,
                name,
                symbol=symbol,
                asset_class=asset_scope.get("asset_class"),
            )

        cfg = self._resolve_indicator_config(
            name,
            await self.repository.get_indicator_config(name),
        )
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

        scored = await asyncio.to_thread(
            self._score_indicator_with_fallback,
            name=name,
            value=val,
            user_id=user_id,
        )
        score = float(scored["score"])
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

    async def get_all_indicators(self) -> List[dict[str, str]]:
        rows = await self.repository.get_all_indicators()
        merged: dict[str, dict[str, str]] = {}

        for definition in get_active_technical_indicator_definitions():
            merged[str(definition["name"])] = {
                "name": str(definition["name"]),
                "display_name": str(definition["display_name"]),
            }

        for row in rows:
            if row["name"] in merged:
                continue
            merged[row["name"]] = row

        return sorted(merged.values(), key=lambda row: row["display_name"].lower())
