from __future__ import annotations

from typing import Any, Dict, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from backend.infrastructure.repositories.asset_catalog_repository import AssetCatalogRepository
from backend.infrastructure.repositories.bot_repository import BotRepository
from backend.infrastructure.repositories.conversation_state_repository import ConversationStateRepository
from backend.infrastructure.repositories.setup_repository import SetupRepository
from backend.infrastructure.repositories.strategy_repository import StrategyRepository
from backend.infrastructure.repositories.user_repository import UserRepository
from backend.services.asset_catalog_service import AssetCatalogService


class FinnV2EntityResolutionService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.users = UserRepository(session)
        self.states = ConversationStateRepository(session)
        self.setups = SetupRepository(session)
        self.strategies = StrategyRepository(session)
        self.bots = BotRepository(session)
        self.assets = AssetCatalogService(session)
        self.asset_repo = AssetCatalogRepository(session)

    async def resolve_asset(
        self,
        *,
        user_id: int,
        selector: Dict[str, Any],
        workspace_hints: Optional[Dict[str, Any]] = None,
        client_context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        explicit = self._normalize_symbol(selector.get("asset"))
        if explicit:
            return {"asset": explicit, "resolution_source": "explicit_selector"}

        state = await self.states.get_state(user_id)
        conversation_symbol = self._normalize_symbol((state or {}).get("asset"))
        if conversation_symbol:
            return {"asset": conversation_symbol, "resolution_source": "conversation_state"}

        hints = dict(workspace_hints or {})
        context = dict(client_context or {})
        workspace_asset = self._normalize_symbol(
            hints.get("workspace_asset")
            or hints.get("active_workspace_asset")
            or context.get("workspace_asset")
            or context.get("active_workspace_asset")
        )
        if workspace_asset:
            asset = await self.assets.get_asset(workspace_asset)
            if asset and asset.get("symbol") == workspace_asset:
                return {"asset": workspace_asset, "resolution_source": "workspace_state"}

        user = await self.users.get_by_id(user_id)
        preferences = getattr(user, "ai_preferences", {}) or {}
        selected_asset = self._normalize_symbol(preferences.get("selected_asset"))
        if selected_asset:
            return {"asset": selected_asset, "resolution_source": "selected_asset"}
        active_asset = self._normalize_symbol(preferences.get("active_asset"))
        if active_asset:
            return {"asset": active_asset, "resolution_source": "active_asset"}

        hinted = self._normalize_symbol(hints.get("asset") or hints.get("symbol") or context.get("asset") or context.get("symbol"))
        if hinted:
            asset = await self.assets.get_asset(hinted)
            if asset and asset.get("symbol") == hinted:
                return {"asset": hinted, "resolution_source": "workspace_hint"}

        raise LookupError("asset_not_resolved")

    async def resolve_setup(
        self,
        *,
        user_id: int,
        selector: Dict[str, Any],
        asset: Optional[str],
    ) -> Dict[str, Any]:
        explicit_setup_id = self._coerce_int(selector.get("setup_id"))
        if explicit_setup_id:
            row = await self.setups.get_setup_by_id(explicit_setup_id, user_id)
            if row:
                return {"setup": dict(row), "resolution_source": "explicit_setup_id"}
            raise LookupError("entity_not_found")

        active_setup = await self.setups.get_active_setup(user_id)
        if active_setup and self._matches_symbol(active_setup.get("symbol"), asset):
            return {"setup": dict(active_setup), "resolution_source": "active_setup"}

        candidates = [dict(row) for row in await self.setups.get_user_setups(user_id) if self._matches_symbol(row.get("symbol"), asset)]
        if len(candidates) == 1:
            return {"setup": candidates[0], "resolution_source": "single_asset_setup"}
        if len(candidates) > 1:
            raise LookupError("setup_ambiguous")
        raise LookupError("setup_not_resolved")

    async def resolve_strategy(
        self,
        *,
        user_id: int,
        selector: Dict[str, Any],
        setup: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        explicit_strategy_id = self._coerce_int(selector.get("strategy_id"))
        if explicit_strategy_id:
            row = await self.strategies.get_raw_strategy_with_setup(explicit_strategy_id, user_id)
            if row:
                return {"strategy": dict(row), "resolution_source": "explicit_strategy_id"}
            raise LookupError("entity_not_found")

        if setup and setup.get("id"):
            row = await self.strategies.get_strategy_by_setup(int(setup["id"]), user_id)
            if row:
                return {"strategy": dict(row), "resolution_source": "setup_link"}
            raise LookupError("strategy_not_resolved")

        last_strategy = await self.strategies.get_last_strategy(user_id)
        if last_strategy:
            return {"strategy": dict(last_strategy), "resolution_source": "last_strategy"}
        raise LookupError("strategy_not_resolved")

    async def resolve_bot(
        self,
        *,
        user_id: int,
        selector: Dict[str, Any],
        strategy: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        explicit_bot_id = self._coerce_int(selector.get("bot_id"))
        if explicit_bot_id:
            row = await self.bots.get_bot_config(user_id, explicit_bot_id)
            if row:
                return {"bot": dict(row), "resolution_source": "explicit_bot_id"}
            raise LookupError("entity_not_found")

        configs = [dict(item) for item in await self.bots.get_bot_configs(user_id)]
        if strategy and strategy.get("id"):
            linked = [row for row in configs if row.get("strategy_id") == strategy.get("id")]
            if len(linked) == 1:
                return {"bot": linked[0], "resolution_source": "strategy_link"}
            if len(linked) > 1:
                raise LookupError("bot_ambiguous")
            raise LookupError("bot_not_resolved")
        if len(configs) == 1:
            return {"bot": configs[0], "resolution_source": "single_bot"}
        raise LookupError("bot_not_resolved")

    def _normalize_symbol(self, value: Any) -> Optional[str]:
        normalized = str(value or "").strip().upper()
        return normalized or None

    def _matches_symbol(self, candidate: Any, asset: Optional[str]) -> bool:
        if not asset:
            return False
        return self._normalize_symbol(candidate) == self._normalize_symbol(asset)

    def _coerce_int(self, value: Any) -> Optional[int]:
        try:
            coerced = int(value)
        except (TypeError, ValueError):
            return None
        return coerced if coerced > 0 else None
