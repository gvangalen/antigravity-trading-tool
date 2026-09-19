from __future__ import annotations

import re
from typing import Any, Dict, Literal, Optional

from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.infrastructure.repositories.asset_catalog_repository import AssetCatalogRepository
from backend.infrastructure.repositories.bot_repository import BotRepository
from backend.infrastructure.repositories.conversation_state_repository import ConversationStateRepository
from backend.infrastructure.repositories.setup_repository import SetupRepository
from backend.infrastructure.repositories.strategy_repository import StrategyRepository
from backend.infrastructure.repositories.user_repository import UserRepository
from backend.services.asset_catalog_service import AssetCatalogService
from backend.services.finn_v2_active_plan_resolver import FinnV2ActivePlanResolver


EntityType = Literal["setup", "strategy", "bot"]
ResolutionStatus = Literal["resolved", "ambiguous", "not_found", "forbidden", "invalid_type"]


class CanonicalEntityTarget(BaseModel):
    """One typed resolution result consumed by every existing-object operation."""

    entity_type: EntityType
    entity_id: Optional[int] = None
    display_name: Optional[str] = None
    owner_id: int
    relation: Dict[str, Any] = Field(default_factory=dict)
    source: Optional[str] = None
    resolution_status: ResolutionStatus
    candidate_names: list[str] = Field(default_factory=list)

    @property
    def relational_context(self) -> Dict[str, Any]:
        return self.relation

    @property
    def resolution_source(self) -> Optional[str]:
        return self.source


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

    async def resolve_canonical_target(
        self,
        *,
        user_id: int,
        entity_type: EntityType,
        selector: Optional[Dict[str, Any]] = None,
        message: str = "",
        conversation_context: Optional[Dict[str, Any]] = None,
        workspace_hints: Optional[Dict[str, Any]] = None,
        client_context: Optional[Dict[str, Any]] = None,
    ) -> CanonicalEntityTarget:
        """Resolve one existing object using the shared lifecycle precedence.

        IDs are accepted only from trusted persisted/context sources and are
        always re-read through owner-scoped repositories. A visible name in
        the current message outranks every contextual reference.
        """
        selector = dict(selector or {})
        conversation_context = dict(conversation_context or {})
        workspace_hints = dict(workspace_hints or {})
        client_context = dict(client_context or {})
        candidates = await self._entity_candidates(user_id=user_id, entity_type=entity_type)

        declared_type = selector.get("entity_type")
        if declared_type and declared_type != entity_type:
            return self._resolution_failure(user_id, entity_type, "invalid_type", source="explicit_selector")

        message_matches = self._explicit_message_matches(message, candidates)
        if len(message_matches) == 1:
            return self._canonical_target(user_id, entity_type, message_matches[0], "explicit_name")
        if len(message_matches) > 1:
            return self._resolution_failure(
                user_id,
                entity_type,
                "ambiguous",
                source="explicit_name",
                candidate_names=self._candidate_names(message_matches),
            )

        explicit_name = self._normalized_name(selector.get(f"{entity_type}_name"))
        if explicit_name:
            named = [row for row in candidates if self._normalized_name(row.get("name")) == explicit_name]
            if len(named) == 1:
                return self._canonical_target(user_id, entity_type, named[0], "explicit_name")
            if len(named) > 1:
                return self._resolution_failure(
                    user_id,
                    entity_type,
                    "ambiguous",
                    source="explicit_name",
                    candidate_names=self._candidate_names(named),
                )
            return self._resolution_failure(user_id, entity_type, "not_found", source="explicit_name")

        # An asset named in the current turn outranks stale conversation and
        # workspace context.  It narrows the owner's candidates, but never
        # guesses when more than one object exists for that asset.
        explicit_asset = self._normalize_symbol(selector.get("asset"))
        if explicit_asset:
            asset_candidates = [
                row for row in candidates
                if self._candidate_asset(row) == explicit_asset
            ]
            if len(asset_candidates) == 1:
                return self._canonical_target(
                    user_id, entity_type, asset_candidates[0], "explicit_asset"
                )
            if len(asset_candidates) > 1:
                return self._resolution_failure(
                    user_id,
                    entity_type,
                    "ambiguous",
                    source="explicit_asset",
                    candidate_names=self._candidate_names(asset_candidates),
                )
            return self._resolution_failure(
                user_id, entity_type, "not_found", source="explicit_asset"
            )

        action_result = dict(conversation_context.get("previous_action_result") or {})
        if action_result.get("entity_type") == entity_type and action_result.get("result_status") == "succeeded":
            entity_id = self._coerce_int(action_result.get("entity_id"))
            if entity_id:
                return await self._canonical_target_by_id(
                    user_id=user_id,
                    entity_type=entity_type,
                    entity_id=entity_id,
                    source="previous_action_result",
                )

        active_target = dict(conversation_context.get("canonical_entity_target") or {})
        if active_target.get("entity_type") == entity_type:
            entity_id = self._coerce_int(active_target.get("entity_id"))
            if entity_id:
                return await self._canonical_target_by_id(
                    user_id=user_id,
                    entity_type=entity_type,
                    entity_id=entity_id,
                    source="active_runtime_context",
                )

        related = await self._resolve_workspace_relation(
            user_id=user_id,
            entity_type=entity_type,
            workspace_hints=workspace_hints,
            client_context=client_context,
        )
        if related is not None:
            return related

        for context in (workspace_hints, client_context):
            entity_id = self._coerce_int(context.get(f"{entity_type}_id"))
            if entity_id:
                return await self._canonical_target_by_id(
                    user_id=user_id,
                    entity_type=entity_type,
                    entity_id=entity_id,
                    source="workspace_context",
                )

        # A selector ID is model/legacy output, not visible user intent. Keep
        # it only as a final owner-checked compatibility input after every
        # authoritative context source has had precedence.
        selector_id = self._coerce_int(selector.get(f"{entity_type}_id"))
        if selector_id:
            return await self._canonical_target_by_id(
                user_id=user_id,
                entity_type=entity_type,
                entity_id=selector_id,
                source="selector_compatibility",
            )

        if len(candidates) == 1:
            return self._canonical_target(user_id, entity_type, candidates[0], "single_owner_candidate")
        if len(candidates) > 1:
            return self._resolution_failure(
                user_id,
                entity_type,
                "ambiguous",
                source="owner_candidates",
                candidate_names=self._candidate_names(candidates),
            )
        return self._resolution_failure(user_id, entity_type, "not_found", source="owner_candidates")

    async def _resolve_workspace_relation(
        self,
        *,
        user_id: int,
        entity_type: EntityType,
        workspace_hints: Dict[str, Any],
        client_context: Dict[str, Any],
    ) -> Optional[CanonicalEntityTarget]:
        """Follow an owner-scoped page relation without narrowing search.

        Product surfaces supply hints, never authority. Direct entity IDs are
        handled by the caller after this relation step. For a bot reference on
        a Setup or Strategy page, resolve the validated parent relation and
        return a bot only when that relation identifies exactly one candidate.
        """
        if entity_type != "bot":
            return None
        contexts = (workspace_hints, client_context)
        strategy_id = next(
            (self._coerce_int(context.get("strategy_id")) for context in contexts if self._coerce_int(context.get("strategy_id"))),
            None,
        )
        setup_id = next(
            (self._coerce_int(context.get("setup_id")) for context in contexts if self._coerce_int(context.get("setup_id"))),
            None,
        )
        bot_candidates = [dict(row) for row in await self.bots.get_bot_configs(user_id)]
        if strategy_id:
            strategy = await self.strategies.get_raw_strategy_with_setup(strategy_id, user_id)
            if strategy:
                linked = [row for row in bot_candidates if self._coerce_int(row.get("strategy_id")) == strategy_id]
                if len(linked) == 1:
                    return self._canonical_target(user_id, "bot", linked[0], "workspace_strategy_link")
                if len(linked) > 1:
                    return self._resolution_failure(
                        user_id,
                        "bot",
                        "ambiguous",
                        source="workspace_strategy_link",
                        candidate_names=self._candidate_names(linked),
                    )
        if setup_id:
            setup = await self.setups.get_setup_by_id(setup_id, user_id)
            if setup:
                strategies = [
                    dict(row)
                    for row in await self.strategies.query_strategies(user_id, {})
                    if self._coerce_int(row.get("setup_id")) == setup_id
                ]
                strategy_ids = {
                    self._coerce_int(row.get("id") or row.get("strategy_id"))
                    for row in strategies
                }
                linked = [
                    row for row in bot_candidates
                    if self._coerce_int(row.get("strategy_id")) in strategy_ids
                ]
                if len(linked) == 1:
                    return self._canonical_target(user_id, "bot", linked[0], "workspace_setup_link")
                if len(linked) > 1:
                    return self._resolution_failure(
                        user_id,
                        "bot",
                        "ambiguous",
                        source="workspace_setup_link",
                        candidate_names=self._candidate_names(linked),
                    )
        return None

    async def _entity_candidates(self, *, user_id: int, entity_type: EntityType) -> list[Dict[str, Any]]:
        if entity_type == "setup":
            rows = await self.setups.get_user_setups(user_id)
        elif entity_type == "strategy":
            rows = await self.strategies.query_strategies(user_id, {})
        else:
            rows = await self.bots.get_bot_configs(user_id)
        return [dict(row) for row in rows]

    async def _canonical_target_by_id(
        self,
        *,
        user_id: int,
        entity_type: EntityType,
        entity_id: int,
        source: str,
    ) -> CanonicalEntityTarget:
        if entity_type == "setup":
            row = await self.setups.get_setup_by_id(entity_id, user_id)
        elif entity_type == "strategy":
            row = await self.strategies.get_raw_strategy_with_setup(entity_id, user_id)
        else:
            row = await self.bots.get_bot_config(user_id, entity_id)
        if not row:
            status: ResolutionStatus = (
                "forbidden"
                if await self._entity_exists_for_another_owner(entity_type=entity_type, entity_id=entity_id, user_id=user_id)
                else "not_found"
            )
            return self._resolution_failure(user_id, entity_type, status, source=source)
        return self._canonical_target(user_id, entity_type, dict(row), source)

    async def _entity_exists_for_another_owner(
        self,
        *,
        entity_type: EntityType,
        entity_id: int,
        user_id: int,
    ) -> bool:
        if not callable(getattr(self.session, "execute", None)):
            return False
        tables = {"setup": "setups", "strategy": "strategies", "bot": "bot_configs"}
        result = await self.session.execute(
            text(f"SELECT 1 FROM {tables[entity_type]} WHERE id = :entity_id AND user_id <> :user_id LIMIT 1"),
            {"entity_id": entity_id, "user_id": user_id},
        )
        return result.first() is not None

    def _canonical_target(
        self,
        user_id: int,
        entity_type: EntityType,
        row: Dict[str, Any],
        source: str,
    ) -> CanonicalEntityTarget:
        entity_id = self._coerce_int(row.get("id") or row.get(f"{entity_type}_id"))
        if not entity_id:
            return self._resolution_failure(user_id, entity_type, "not_found", source=source)
        relation = {
            key: row.get(key)
            for key in (
                "setup_id",
                "setup_name",
                "strategy_id",
                "strategy_name",
                "symbol",
                "timeframe",
            )
            if row.get(key) is not None and key != f"{entity_type}_id"
        }
        return CanonicalEntityTarget(
            entity_type=entity_type,
            entity_id=entity_id,
            display_name=str(row.get("name") or f"{entity_type.title()} {entity_id}"),
            owner_id=user_id,
            relation=relation,
            source=source,
            resolution_status="resolved",
        )

    @staticmethod
    def _resolution_failure(
        user_id: int,
        entity_type: EntityType,
        status: ResolutionStatus,
        *,
        source: Optional[str],
        candidate_names: Optional[list[str]] = None,
    ) -> CanonicalEntityTarget:
        return CanonicalEntityTarget(
            entity_type=entity_type,
            owner_id=user_id,
            source=source,
            resolution_status=status,
            candidate_names=list(candidate_names or []),
        )

    @staticmethod
    def _candidate_names(rows: list[Dict[str, Any]]) -> list[str]:
        return sorted({str(row.get("name") or "").strip() for row in rows if str(row.get("name") or "").strip()})

    def _candidate_asset(self, row: Dict[str, Any]) -> Optional[str]:
        return self._normalize_symbol(
            row.get("symbol")
            or row.get("setup_symbol")
            or row.get("strategy_symbol")
            or row.get("asset")
        )

    def _explicit_message_matches(
        self,
        message: str,
        rows: list[Dict[str, Any]],
    ) -> list[Dict[str, Any]]:
        matches = [row for row in rows if self._message_mentions_name(message, row.get("name"))]
        if len(matches) <= 1:
            return matches
        # If one visible name fully contains another ("Alpha" / "Alpha Bot"),
        # the most specific name is the user's explicit target. Equal-length
        # matches remain genuinely ambiguous.
        lengths = [len(self._normalized_name(row.get("name")) or "") for row in matches]
        longest = max(lengths, default=0)
        return [row for row, length in zip(matches, lengths) if length == longest]

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
            strategy_asset = self._normalize_symbol((strategy or {}).get("symbol") or (strategy or {}).get("setup_symbol"))
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
        operation_id: str = "",
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
        if operation_id == "create_strategy" and "setup_id" in required_inputs and not self._coerce_int(selector.get("setup_id")):
            setups = [dict(row) for row in await self.setups.get_user_setups(user_id)]
            if len(setups) == 1:
                resolved["setup_id"] = self._coerce_int(setups[0].get("id") or setups[0].get("setup_id"))
            elif len(setups) > 1 and not self._normalized_name(selector.get("setup_name")):
                raise LookupError("setup_ambiguous")
        if operation_id == "create_bot" and "strategy_id" in required_inputs and not self._coerce_int(selector.get("strategy_id")):
            strategies = [dict(row) for row in await self.strategies.query_strategies(user_id, {})]
            if len(strategies) == 1:
                resolved["strategy_id"] = self._coerce_int(strategies[0].get("id") or strategies[0].get("strategy_id"))
            elif len(strategies) > 1 and not self._normalized_name(selector.get("strategy_name")):
                raise LookupError("strategy_ambiguous")
        if "setup_id" in required_inputs and not self._coerce_int(selector.get("setup_id")):
            if resolved.get("setup_id"):
                pass
            elif self._normalized_name(selector.get("setup_name")):
                setup = await self.resolve_setup(user_id=user_id, selector=selector, asset=None)
                value = self._coerce_int(setup["setup"].get("id") or setup["setup"].get("setup_id"))
                if value:
                    resolved["setup_id"] = value
        if "strategy_id" in required_inputs and not self._coerce_int(selector.get("strategy_id")):
            if resolved.get("strategy_id"):
                pass
            elif self._normalized_name(selector.get("strategy_name")):
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

    async def enrich_tool_selector_from_message(
        self,
        *,
        user_id: int,
        selector: Dict[str, Any],
        message: str,
    ) -> Dict[str, Any]:
        """Resolve exact owner-scoped names for read-tool context.

        These identifiers are tool selectors, not action-contract inputs. They
        guide evidence hydration without changing the registry-owned schema.
        """
        enriched = dict(selector)
        if self.is_setup_collection_request(message):
            enriched["setup_collection_requested"] = True
        repositories = {
            "setup": self.setups.get_user_setups,
            "strategy": lambda owner_id: self.strategies.query_strategies(owner_id, {}),
            "bot": self.bots.get_bot_configs,
        }
        for entity, loader in repositories.items():
            id_field = f"{entity}_id"
            if self._coerce_int(enriched.get(id_field)):
                continue
            matches = [
                dict(row)
                for row in await loader(user_id)
                if self._message_mentions_name(message, row.get("name"))
            ]
            if len(matches) == 1:
                value = self._coerce_int(matches[0].get("id") or matches[0].get(id_field))
                if value:
                    enriched[id_field] = value
            elif len(matches) > 1:
                raise LookupError(f"{entity}_ambiguous")
        return enriched

    @staticmethod
    def is_setup_collection_request(message: str) -> bool:
        normalized = " ".join(str(message or "").casefold().split())
        return bool(re.search(
            r"\b(?:welke|toon|noem|overzicht|which|show|list|welche|zeige|liste)\b"
            r".*\b(?:setups?|plannen?|set-ups?)\b",
            normalized,
        ))

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

        if selector.get("setup_collection_requested"):
            candidates = [dict(row) for row in await self.setups.get_user_setups(user_id)]
            normalized_asset = self._normalize_symbol(asset or selector.get("asset"))
            if normalized_asset:
                candidates = [row for row in candidates if self._candidate_asset(row) == normalized_asset]
            if candidates:
                return {
                    "setup": candidates[0],
                    "setups": candidates,
                    "resolution_source": "owner_setup_collection",
                }
            raise LookupError("setup_not_resolved")

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
