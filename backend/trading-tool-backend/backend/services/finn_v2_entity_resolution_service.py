from __future__ import annotations

import re
from typing import Any, Dict, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from backend.infrastructure.repositories.asset_catalog_repository import AssetCatalogRepository
from backend.infrastructure.repositories.bot_repository import BotRepository
from backend.infrastructure.repositories.conversation_state_repository import ConversationStateRepository
from backend.infrastructure.repositories.setup_repository import SetupRepository
from backend.infrastructure.repositories.strategy_repository import StrategyRepository
from backend.infrastructure.repositories.user_repository import UserRepository
from backend.services.asset_catalog_service import AssetCatalogService
from backend.services.finn_v2_active_plan_resolver import FinnV2ActivePlanResolver


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
        self.active_plans = FinnV2ActivePlanResolver()

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

        explicit_setup_id = self._coerce_int(selector.get("setup_id"))
        if explicit_setup_id:
            setup = await self.setups.get_setup_by_id(explicit_setup_id, user_id)
            if setup and self._normalize_symbol(setup.get("symbol")):
                return {"asset": self._normalize_symbol(setup.get("symbol")), "resolution_source": "explicit_setup_link"}

        explicit_strategy_id = self._coerce_int(selector.get("strategy_id"))
        if explicit_strategy_id:
            strategy = await self.strategies.get_raw_strategy_with_setup(explicit_strategy_id, user_id)
            strategy_asset = self._normalize_symbol((strategy or {}).get("setup_symbol"))
            if strategy_asset:
                return {"asset": strategy_asset, "resolution_source": "explicit_strategy_link"}

        explicit_bot_id = self._coerce_int(selector.get("bot_id"))
        if explicit_bot_id:
            bot = await self.bots.get_bot_config(user_id, explicit_bot_id)
            bot_asset = self._normalize_symbol((bot or {}).get("symbol") or (bot or {}).get("setup_symbol"))
            if bot_asset:
                return {"asset": bot_asset, "resolution_source": "explicit_bot_link"}

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

    async def resolve_contract_reference_inputs(
        self,
        *,
        user_id: int,
        selector: Dict[str, Any],
        required_inputs: tuple[str, ...],
        message: str = "",
    ) -> Dict[str, int]:
        """Resolve explicit, owner-scoped object names into registry ID slots.

        Action contracts own which IDs are required.  This boundary only
        resolves an explicitly named object before missing-input calculation;
        it never guesses an active object or introduces a second input schema.
        """
        # The selector may omit an entity name from ordinary prose. Resolve an
        # unambiguous, user-owned name present in that prose before deciding a
        # registry ID slot is missing. We never use a cross-user or active-item
        # fallback here: ambiguity remains a safe clarification.
        selector = await self._selector_with_message_references(
            user_id=user_id,
            selector=selector,
            required_inputs=required_inputs,
            message=message,
        )
        resolved: Dict[str, int] = {}
        if "setup_id" in required_inputs and not self._coerce_int(selector.get("setup_id")):
            if self._normalized_name(selector.get("setup_name")):
                setup = await self.resolve_setup(user_id=user_id, selector=selector, asset=None)
                value = self._coerce_int(setup["setup"].get("id") or setup["setup"].get("setup_id"))
                if value:
                    resolved["setup_id"] = value
        if "strategy_id" in required_inputs and not self._coerce_int(selector.get("strategy_id")):
            if self._normalized_name(selector.get("strategy_name")):
                strategy = await self.resolve_strategy(user_id=user_id, selector=selector, setup=None)
                value = self._coerce_int(strategy["strategy"].get("id") or strategy["strategy"].get("strategy_id"))
                if value:
                    resolved["strategy_id"] = value
        if "bot_id" in required_inputs and not self._coerce_int(selector.get("bot_id")):
            if self._normalized_name(selector.get("bot_name")):
                bot = await self.resolve_bot(user_id=user_id, selector=selector, strategy=None)
                value = self._coerce_int(bot["bot"].get("id") or bot["bot"].get("bot_id"))
                if value:
                    resolved["bot_id"] = value
        return resolved

    async def _selector_with_message_references(
        self,
        *,
        user_id: int,
        selector: Dict[str, Any],
        required_inputs: tuple[str, ...],
        message: str,
    ) -> Dict[str, Any]:
        enriched = dict(selector)
        repositories = {
            "setup": self.setups.get_user_setups,
            "strategy": lambda owner_id: self.strategies.query_strategies(owner_id, {}),
            "bot": self.bots.get_bot_configs,
        }
        for entity, loader in repositories.items():
            id_field, name_field = f"{entity}_id", f"{entity}_name"
            if id_field not in required_inputs or self._coerce_int(enriched.get(id_field)) or self._normalized_name(enriched.get(name_field)):
                continue
            rows = await loader(user_id)
            matches = [dict(row) for row in rows if self._message_mentions_name(message, row.get("name"))]
            if len(matches) == 1:
                enriched[name_field] = matches[0].get("name")
            elif len(matches) > 1:
                raise LookupError(f"{entity}_ambiguous")
        return enriched

    @staticmethod
    def _message_mentions_name(message: str, name: Any) -> bool:
        normalized_name = " ".join(str(name or "").casefold().split())
        normalized_message = " ".join(str(message or "").casefold().split())
        if len(normalized_name) < 2 or not normalized_message:
            return False
        return bool(re.search(rf"(?<!\w){re.escape(normalized_name)}(?!\w)", normalized_message))

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

        explicit_setup_name = self._normalized_name(selector.get("setup_name"))
        if explicit_setup_name:
            matches = [
                dict(row)
                for row in await self.setups.get_user_setups(user_id)
                if self._normalized_name(row.get("name")) == explicit_setup_name
            ]
            if len(matches) == 1:
                return {"setup": matches[0], "resolution_source": "explicit_setup_name"}
            if len(matches) > 1:
                raise LookupError("setup_ambiguous")
            raise LookupError("entity_not_found")

        # A named strategy or bot identifies its parent setup more precisely
        # than an active-workspace fallback. This keeps an explicit object
        # reference owner-scoped while satisfying contracts that need setup
        # context before they can resolve the requested child object.
        strategy_selector = self._has_explicit_identity(selector, "strategy")
        if strategy_selector:
            strategy = (await self.resolve_strategy(user_id=user_id, selector=selector, setup=None))["strategy"]
            parent_setup_id = self._coerce_int(strategy.get("setup_id"))
            if parent_setup_id:
                row = await self.setups.get_setup_by_id(parent_setup_id, user_id)
                if row:
                    return {"setup": dict(row), "resolution_source": "explicit_strategy_link"}
            raise LookupError("setup_not_resolved")

        bot_selector = self._has_explicit_identity(selector, "bot")
        if bot_selector:
            bot = (await self.resolve_bot(user_id=user_id, selector=selector, strategy=None))["bot"]
            parent_strategy_id = self._coerce_int(bot.get("strategy_id"))
            if parent_strategy_id:
                strategy = await self.strategies.get_raw_strategy_with_setup(parent_strategy_id, user_id)
                parent_setup_id = self._coerce_int((strategy or {}).get("setup_id"))
                if parent_setup_id:
                    row = await self.setups.get_setup_by_id(parent_setup_id, user_id)
                    if row:
                        return {"setup": dict(row), "resolution_source": "explicit_bot_link"}
            raise LookupError("setup_not_resolved")

        resolution = self.active_plans.resolve(
            asset=asset,
            active_setup=await self.setups.get_active_setup(user_id),
            candidates=await self.setups.get_user_setups(user_id),
        )
        if resolution.setup is not None:
            return {"setup": resolution.setup, "resolution_source": resolution.source}
        if resolution.source == "setup_ambiguous":
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

        explicit_strategy_name = self._normalized_name(selector.get("strategy_name"))
        if explicit_strategy_name:
            matches = [
                row
                for row in await self.strategies.query_strategies(user_id, {})
                if self._normalized_name(row.get("name")) == explicit_strategy_name
            ]
            if len(matches) == 1:
                return {"strategy": matches[0], "resolution_source": "explicit_strategy_name"}
            if len(matches) > 1:
                raise LookupError("strategy_ambiguous")
            raise LookupError("entity_not_found")

        # A named bot is an explicit reference to its parent strategy; do not
        # let an unrelated active setup win before following that relation.
        if self._has_explicit_identity(selector, "bot"):
            bot = (await self.resolve_bot(user_id=user_id, selector=selector, strategy=None))["bot"]
            parent_strategy_id = self._coerce_int(bot.get("strategy_id"))
            if parent_strategy_id:
                row = await self.strategies.get_raw_strategy_with_setup(parent_strategy_id, user_id)
                if row:
                    return {"strategy": dict(row), "resolution_source": "explicit_bot_link"}
            raise LookupError("strategy_not_resolved")

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
        explicit_bot_name = self._normalized_name(selector.get("bot_name"))
        if explicit_bot_name:
            matches = [row for row in configs if self._normalized_name(row.get("name")) == explicit_bot_name]
            if len(matches) == 1:
                return {"bot": matches[0], "resolution_source": "explicit_bot_name"}
            if len(matches) > 1:
                raise LookupError("bot_ambiguous")
            raise LookupError("entity_not_found")
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

    @staticmethod
    def _normalized_name(value: Any) -> Optional[str]:
        normalized = " ".join(str(value or "").casefold().split())
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

    def _has_explicit_identity(self, selector: Dict[str, Any], entity: str) -> bool:
        return bool(
            self._coerce_int(selector.get(f"{entity}_id"))
            or self._normalized_name(selector.get(f"{entity}_name"))
        )
