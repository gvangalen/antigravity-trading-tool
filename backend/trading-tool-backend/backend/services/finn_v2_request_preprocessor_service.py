"""Deterministic facts extracted before selecting a FINN V2 operation.

This service deliberately stops at facts that can be established without a
model: explicit assets, entity mentions, polarity and conversational
references.  It does not choose modes, scopes or tools; that remains the
operation registry's responsibility.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Mapping, Optional

from backend.services.asset_catalog_service import resolve_catalog_symbol


@dataclass(frozen=True)
class FinnV2PreprocessedRequest:
    normalized_text: str
    language: str
    action_polarity: str
    explicit_entities: tuple[str, ...]
    primary_entity: Optional[str]
    explicit_target_asset: Optional[str]
    referenced_asset: Optional[str]
    workspace_context_asset: Optional[str]
    conversation_reference_markers: tuple[str, ...]
    discourse_act: str
    possible_slot_answer: Optional[str]


class FinnV2RequestPreprocessorService:
    """Extract user-provided facts without creating a parallel intent router."""

    _ACTION_PATTERNS = (
        ("confirm", ("bevestig", "confirm")),
        ("execute", ("uitvoeren", "execute", "voer uit")),
        ("remove", ("verwijder", "remove", "haal", "halen", "stop met")),
        ("add", ("voeg", "add", "toevoeg", "zet op", "volg")),
        ("activate", ("activeer", "activate", "schakel", "start", "zet live", "go live")),
        ("update", ("wijzig", "update", "pas aan")),
        ("create", ("maak", "maken", "create", "ontwerp", "stel", "bereid")),
        ("evaluate", ("beoordeel", "evaluate", "zwak", "risico", "past", "fit", "ontbrek", "ontbreek", "vertrouwen")),
    )
    _ENTITY_TERMS = {
        "watchlist": ("watchlist", "volglijst", "follow"),
        "indicator_configuration": (
            "indicator",
            "indicatorconfiguratie",
            "technische configuratie",
            "technical configuration",
            "signaal",
            "signalen",
            "trendindicator",
            "rsi",
            "vwap",
            "volume",
            "ma200",
            "ma_200",
            "marktregime",
        ),
        "profile": ("profiel", "risicoprofiel", "tradingstijl", "risk profile", "trading style"),
        "setup": ("setup", "set-up"),
        "strategy": ("strategie", "strategy"),
        "bot": ("bot", "automation", "automatisering"),
        "plan": (
            "plan",
            "plaatje",
            "voorwaarde",
            "zwakste",
            "betrouwbaar",
        ),
        "asset": ("asset", "instrument", "coin", "aandeel", "workspace", "markt"),
    }
    _REFERENCE_MARKERS = {
        "previous_verified_conclusion": ("die conclusie", "dat antwoord", "eerder antwoord", "onderbouw", "waarop baseer", "waar baseer", "welk bewijs", "waarom concludeerde", "leg de eerdere", "evidence achter"),
        "reformulation": (
            "korter",
            "herformuleer",
            "anders formuleren",
            "andere woorden",
            "compacter",
            "conclusie anders",
        ),
        "contextual_entity": ("die setup", "deze strategie", "die bot", "dat plan", "deze asset"),
    }

    def preprocess(
        self,
        *,
        message: str,
        workspace_hints: Optional[Mapping[str, object]] = None,
        client_context: Optional[Mapping[str, object]] = None,
    ) -> FinnV2PreprocessedRequest:
        original = str(message or "").strip()
        normalized = re.sub(r"\s+", " ", original.casefold()).strip()
        asset = self._asset_from_text(original)
        context_asset = self._asset_from_context(workspace_hints, client_context)
        entity_positions = self._entity_positions(normalized)
        if "bot" in entity_positions:
            bot_status_position = self._first_term_position(
                normalized, ("live", "status", "draait", "actief")
            )
            if bot_status_position is not None:
                entity_positions["bot_status"] = bot_status_position
        entities = tuple(entity_positions)
        plan_components = {"indicator_configuration", "setup", "strategy", "bot"}
        relational_components = plan_components.intersection(entities)
        relational_graph = "bot" in relational_components and bool({"setup", "strategy"}.intersection(relational_components))
        explicit_plan = bool(re.search(r"\b(?:mijn\s+)?(?:actieve\s+)?plan\b|\bactive\s+plan\b", normalized))
        # Two linked plan entities are a graph request, not two isolated reads.
        # This remains a fact about the request's explicit nouns; the registry
        # remains responsible for selecting the graph contract and its tools.
        if (relational_graph or explicit_plan) and "plan" not in entities:
            entities = (*entities, "plan")
        # "mijn strategie ... mijn plan" commonly refers to one component
        # inside a plan. Keep ``plan`` as an aggregate entity only when it is
        # the sole entity or the user actually listed several components.
        if "plan" in entities and relational_components and not relational_graph and not explicit_plan:
            entities = tuple(entity for entity in entities if entity != "plan")
        # The aggregate plan is the semantic subject when the user explicitly
        # names several plan components. Otherwise preserve the first entity
        # mentioned in natural language for registry candidate ranking.
        primary_entity = "plan" if "plan" in entities and (relational_graph or explicit_plan) else next(
            (entity for entity in entities if entity != "plan"),
            "plan" if "plan" in entities else None,
        )
        references = tuple(
            marker
            for marker, terms in self._REFERENCE_MARKERS.items()
            if self._contains_any(normalized, terms)
        )
        action = self._action_polarity(normalized)
        if action == "add" and re.search(r"\bvolg(?:en)?\b", normalized) and "watchlist" not in entities:
            entities = (*entities, "watchlist")
        discourse = self._discourse_act(normalized, entities, references, action)
        # A bare explicit asset is useful only as a possible guided slot answer.
        # The conversation resolver decides whether it fills an open field.
        short_turn = len(re.findall(r"[\w-]+", normalized)) <= 10
        is_interrogative = bool(re.match(r"^(?:welke|welk|wat|waar|hoe|who|what|which|where|how)\b", normalized))
        slot_answer = asset if asset and short_turn and not is_interrogative else None
        if (
            action == "read"
            and short_turn
            and (not entities or set(entities).issubset({"asset"}))
            and (
                slot_answer is not None
                or re.search(r"\b(?:naam|name|noem\s+(?:hem|haar)|ik\s+noem|hij\s+heet|het\s+heet)\b", normalized)
            )
        ):
            discourse = "clarification_answer"
        return FinnV2PreprocessedRequest(
            normalized_text=normalized,
            language="en" if re.search(r"\b(what|which|add|remove|create|evaluate)\b", normalized) else "nl",
            action_polarity=action,
            explicit_entities=entities,
            primary_entity=primary_entity,
            explicit_target_asset=asset if action in {"add", "remove", "create"} and "watchlist" in entities else None,
            referenced_asset=asset,
            workspace_context_asset=context_asset,
            conversation_reference_markers=references,
            discourse_act=discourse,
            possible_slot_answer=slot_answer,
        )

    @classmethod
    def _contains_any(cls, text: str, terms: tuple[str, ...]) -> bool:
        words = re.findall(r"[\w-]+", text)
        inflection_stems = {
            "indicator", "signaal", "trendindicator", "setup", "haal", "maak",
            "toevoeg", "verwijder", "activeer", "bevestig", "formuleer",
            "herformuleer", "ontbrek", "ontbreek",
        }
        return any(
            re.search(rf"(?<!\w){re.escape(term)}(?!\w)", text)
            or (
                " " not in term
                and term in inflection_stems
                and any(word.startswith(term) for word in words)
            )
            for term in terms
        )

    @classmethod
    def _entity_positions(cls, text: str) -> dict[str, int]:
        """Return explicit entities in the order they appear in the request."""
        matches: list[tuple[int, str]] = []
        for entity, terms in cls._ENTITY_TERMS.items():
            positions = [
                match.start()
                for term in terms
                for match in re.finditer(rf"(?<!\\w){re.escape(term)}(?!\\w)", text)
            ]
            if positions:
                matches.append((min(positions), entity))
        return {entity: position for position, entity in sorted(matches)}

    @staticmethod
    def _first_term_position(text: str, terms: tuple[str, ...]) -> Optional[int]:
        positions = [
            match.start()
            for term in terms
            for match in re.finditer(rf"(?<!\\w){re.escape(term)}(?!\\w)", text)
        ]
        return min(positions) if positions else None

    def _action_polarity(self, text: str) -> str:
        # Declarative and interrogative verb forms ("volg ik", "bevestigd")
        # describe existing product state; they are not confirmation or add
        # commands. This is grammatical normalization, not prompt matching.
        if re.search(r"\bvolg\s+ik\b|\b(bevestigd|confirmed)\b", text):
            return "read"
        if "live" in text and re.search(r"\b(staat|is|welke|toon)\b", text):
            return "read"
        if "live" in text and re.search(r"\b(activeer|activate|schakel|start|zet|maak)\b", text):
            return "activate"
        # A requested concept/proposal is an operation request even when it is
        # phrased as a question. This recognizes the product act, not a fixed
        # sentence or a specific asset.
        if re.search(r"\b(?:voorstel|proposal)\b", text) and re.search(r"\b(?:volg(?:en)?|follow)\b", text):
            return "add"
        if re.search(r"\bsetupconcept\b", text) or (
            re.search(r"\b(?:voorstel|proposal|concept)\b", text)
            and re.search(r"\b(?:setup|set-up)\b", text)
        ):
            return "create"
        if re.search(r"\bzet\b.+\bop\b", text):
            return "add"
        for polarity, terms in self._ACTION_PATTERNS:
            if self._contains_any(text, terms):
                if polarity == "execute" and self._contains_any(text, ("niet", "niets", "zonder")):
                    continue
                return polarity
        return "read"

    @classmethod
    def _discourse_act(cls, text: str, entities: tuple[str, ...], references: tuple[str, ...], action: str) -> str:
        # A direct capability question is a new request even when it happens
        # to mention plan domains or an earlier conversation. It must not be
        # reinterpreted as a request to explain previous evidence.
        if action == "read" and any(
            phrase in text
            for phrase in (
                "wat kan",
                "wat kun je",
                "welke analyses",
                "welke acties",
                "welke taken",
                "wat ondersteun",
                "wat doet finn",
                "what can",
                "what can you",
                "waarmee",
                "mogelijkheden",
                "help me",
                "hoe helpt",
                "hoe kun je",
            )
        ):
            return "capability"
        if "reformulation" in references:
            return "reformulation"
        if "previous_verified_conclusion" in references:
            return "evidence_follow_up"
        if "contextual_entity" in references:
            return "contextual_follow_up"
        if action == "evaluate" or any(
            phrase in text for phrase in ("zwakste", "betrouwbaar", "waar zit", "voorwaarde", "waar wringt", "hele plaatje", "weegt", "belangrijkst")
        ):
            return "evaluation"
        if action in {"add", "remove", "create", "update", "activate", "confirm", "execute"}:
            return "operation_request"
        return "information_request"

    @staticmethod
    def _asset_from_text(original: str) -> Optional[str]:
        for token in re.findall(r"[A-Za-z0-9]+", original):
            resolved = resolve_catalog_symbol(token)
            if resolved:
                return resolved
        return None

    @staticmethod
    def _asset_from_context(
        workspace_hints: Optional[Mapping[str, object]], client_context: Optional[Mapping[str, object]]
    ) -> Optional[str]:
        for context in (workspace_hints or {}, client_context or {}):
            for key in ("asset", "symbol", "active_asset"):
                resolved = resolve_catalog_symbol(context.get(key))
                if resolved:
                    return resolved
        return None
