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
        ("evaluate", ("beoordeel", "evaluate", "zwak", "risico", "past", "fit", "ontbreekt", "vertrouwen")),
    )
    _ENTITY_TERMS = {
        "watchlist": ("watchlist", "volglijst"),
        "indicator_configuration": (
            "indicator",
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
        "setup": ("setup", "set-up"),
        "strategy": ("strategie", "strategy"),
        "bot": ("bot", "automation", "automatisering"),
        "plan": (
            "plan",
            "profiel",
            "tradingstijl",
            "risicoprofiel",
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
        entities = tuple(
            entity for entity, terms in self._ENTITY_TERMS.items()
            if self._contains_any(normalized, terms)
        )
        references = tuple(
            marker
            for marker, terms in self._REFERENCE_MARKERS.items()
            if self._contains_any(normalized, terms)
        )
        action = self._action_polarity(normalized)
        discourse = self._discourse_act(normalized, entities, references, action)
        # A bare explicit asset is useful only as a possible guided slot answer.
        # The conversation resolver decides whether it fills an open field.
        slot_answer = asset if asset and len(re.findall(r"[\w-]+", normalized)) <= 8 else None
        return FinnV2PreprocessedRequest(
            normalized_text=normalized,
            language="en" if re.search(r"\b(what|which|add|remove|create|evaluate)\b", normalized) else "nl",
            action_polarity=action,
            explicit_entities=entities,
            explicit_target_asset=asset if action in {"add", "remove"} else None,
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
            "herformuleer",
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
        if "reformulation" in references:
            return "reformulation"
        if "previous_verified_conclusion" in references:
            return "evidence_follow_up"
        if "contextual_entity" in references:
            return "contextual_follow_up"
        if action == "evaluate" or any(
            phrase in text for phrase in ("zwakste", "betrouwbaar", "waar zit", "belangrijkste", "voorwaarde", "waar wringt", "hele plaatje")
        ):
            return "evaluation"
        if action in {"add", "remove", "create", "update", "activate", "confirm", "execute"}:
            return "operation_request"
        if action == "read" and any(
            phrase in text
            for phrase in (
                "wat kan",
                "wat kun je",
                "welke analyses",
                "welke acties",
                "what can",
                "what can you",
                "waarmee",
                "mogelijkheden",
                "help me",
                "hoe helpt",
            )
        ):
            return "capability"
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
