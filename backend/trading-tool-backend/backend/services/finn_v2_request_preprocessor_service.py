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

from backend.services.asset_catalog_service import resolve_catalog_symbol, resolve_catalog_symbol_in_text
from backend.domain.finn_v2_setup_input_catalog import FinnV2SetupInputCatalog


@dataclass(frozen=True)
class FinnV2PreprocessedRequest:
    original_text: str
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
    domain_hint: str = "unknown"
    financial_concept: Optional[str] = None
    financial_execution_intent: bool = False
    ambiguous_reference: bool = False
    explicit_plan_subject: bool = False
    linked_graph_relationship: bool = False
    guidance_requested: bool = False


class FinnV2RequestPreprocessorService:
    """Extract user-provided facts without creating a parallel intent router."""

    _ACTION_PATTERNS = (
        ("confirm", ("bevestig", "confirm")),
        # Dutch separable verbs may put the object between "voer" and
        # "uit" ("voer dit voorstel uit"). The imperative stem is still
        # an unambiguous execution act once the registry resolves its domain.
        ("execute", ("uitvoeren", "execute", "voer", "verplaats", "transfer", "stort")),
        ("remove", ("verwijder", "remove", "haal", "halen", "stop met")),
        ("add", ("voeg", "add", "toevoeg", "zet op", "volg")),
        ("activate", ("activeer", "activate", "schakel", "inschakel", "start", "zet live", "go live")),
        ("update", ("wijzig", "update", "pas aan", "verbeter", "improve", "optimise", "optimize")),
        ("create", (
            "maak", "maken", "create", "prepare", "preparing", "ontwerp", "stel", "bereid",
            "voorbereid", "erstell", "anleg",
        )),
        ("evaluate", ("beoordeel", "evaluate", "zwak", "risico", "past", "fit", "ontbrek", "ontbreek", "vertrouwen")),
    )
    # These are assessment predicates, not operation routes.  Combined with
    # an explicitly detected plan subject they constrain the model's semantic
    # frame: a request to diagnose a plan is not a request to clarify a change.
    _PLAN_ASSESSMENT_TERMS = (
        "kwetsbaar", "fragiel", "robuust", "weerbaar", "sterk", "zwak", "risico", "onderbouw",
        "wring", "probleem", "kwaliteit", "verbeter",
        "vulnerable", "fragile", "robust", "resilient", "strong", "weak", "risk", "evidence",
        "vulnerability", "quality", "improve",
        "verletzlich", "fragil", "robust", "widerstandsfähig", "stark", "schwach", "risiko", "beleg",
        "schwachstelle", "qualität", "verbesser",
    )
    _ENTITY_TERMS = {
        "watchlist": ("watchlist", "volglijst", "follow", "gevolgde", "marktenlijst"),
        "indicator_configuration": (
            "indicator",
            "indikator",
            "indikatoren",
            "indikatoreinstellung",
            "indikatoreinstellungen",
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
        "setup": ("setup", "set-up", "opzet", "positie-opzet"),
        "strategy": ("strategie", "strategy"),
        "bot": ("bot", "robot", "automation", "automatisering"),
        "plan": (
            "plan",
            "plaatje",
            "voorwaarde",
            "zwakste",
            "betrouwbaar",
            "handelsaanpak",
            "aanpak",
            "handelswijze",
            "tradingaanpak",
            "trading approach",
            "handelsplan",
            "trading plan",
        ),
        # Portfolio is a financial object even where FINN deliberately has no
        # executable portfolio-management contract. Preserve that fact so the
        # resolver can return the safe unsupported contract rather than
        # treating a financial request as off-topic.
        "portfolio": ("portfolio", "portefeuille"),
        "asset": (
            "asset", "instrument", "symbool", "symbol", "coin", "aandeel", "effect",
            "security", "share", "equity", "wertpapier", "aktie", "workspace", "werkruimte",
            "markt", "belegging", "investment",
        ),
    }
    _REFERENCE_MARKERS = {
        "previous_verified_conclusion": (
            "die conclusie", "dat antwoord", "eerder antwoord", "onderbouw",
            "waarop baseer", "waar baseer", "welk bewijs", "waarom concludeerde",
            "leg de eerdere", "evidence achter", "vastgelegde feiten",
            "feiten achter", "gegeven oordeel", "zojuist gegeven oordeel",
            "vorige oordeel", "eerdere oordeel", "vorige beoordeling", "previous judgment", "previous verdict",
        ),
        "contextual_implication": ("wat betekent dat", "wat houdt dat in", "welk gevolg heeft dat"),
        "reformulation": (
            "korter", "eenvoudiger", "simpler", "more simply",
            "herformuleer",
            "herschrijf",
            "anders formuleren",
            "andere woorden",
            "compacter",
            "conclusie anders", "hetzelfde oordeel opnieuw", "zelfde oordeel opnieuw",
            "zeg hetzelfde eenvoudiger", "say the same judgment again", "same verdict again",
            "restate your previous assessment", "explain that conclusion more simply",
            "gleiches urteil noch einmal", "gleiches urteil erneut", "formuliere diese einschätzung einfacher",
        ),
        "contextual_entity": (
            "die setup", "die strategie", "die bot", "die gekoppelde bot",
            "that setup", "that strategy", "that bot",
            "dat plan", "deze asset",
        ),
    }
    _TIMEFRAME_VALUE = re.compile(r"\b(?:[1-9]\d*(?:m|h|d|w))\b", re.IGNORECASE)
    _COMPOUND_ENTITY_PATTERNS = {
        # Dutch and English compound nouns can join an explicit asset name to
        # an indicator subject without whitespace. These are request facts,
        # not an operation decision; the structured selector still owns the
        # contract selection.
        "indicator_configuration": re.compile(
            r"(?:indicator(?:en)?(?:configuratie|instellingen|settings)?|"
            r"signal(?:settings|configuration)?|technical(?:settings|configuration)?)",
            re.IGNORECASE,
        ),
        # Dutch trading setup compounds are valid financial nouns, while
        # unrelated words such as ``kamerplant`` must never inherit ``plan``.
        "setup": re.compile(
            r"\b(?:swing|trade|position|dca|handels|positie)[-_]?(?:setup|opzet)\b"
            r"|\b(?:setup|opzet)concept\b",
            re.IGNORECASE,
        ),
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
        # A graph overview and a relationship question need different read
        # contracts. This is a typed grammatical fact; it does not select an
        # operation or inspect a particular asset, setup, or bot.
        linked_graph_relationship = relational_graph and bool(re.search(
            r"\b(?:gekoppel\w*|verbond\w*|verbund\w*|linked|connect\w*|associated|zugeordnet)\b",
            normalized,
        ))
        explicit_plan = bool(re.search(r"\b(?:mijn\s+)?(?:actieve\s+)?plan\b|\bactive\s+plan\b", normalized))
        # Two linked plan entities are a graph request, not two isolated reads.
        # This remains a fact about the request's explicit nouns; the registry
        # remains responsible for selecting the graph contract and its tools.
        # A catalog-backed asset followed by a plan noun is an aggregate plan
        # subject even when the language writes the compound as one word.
        # This is grammar plus catalog evidence, not an asset-specific route.
        compound_plan_subject = bool(
            asset
            and re.search(r"(?:plan|strategie|strategy)\b", normalized)
        )
        # A concrete, stored approach for an explicitly named instrument is
        # a setup-shaped object. Broad diagnosis of an approach remains a
        # plan subject, so the concrete/configured modifier is required.
        concrete_setup_subject = bool(
            asset
            and re.search(r"\b(?:concrete|specifieke|configured|ready|klaarstaande|prepared)\b", normalized)
            and re.search(r"(?:handelsaanpak|trading approach)\b", normalized)
        )
        if concrete_setup_subject:
            entities = tuple("setup" if entity == "plan" else entity for entity in entities)
        if (relational_graph or explicit_plan or compound_plan_subject) and "plan" not in entities:
            entities = (*entities, "plan")
        # "mijn strategie ... mijn plan" commonly refers to one component
        # inside a plan. Keep ``plan`` as an aggregate entity only when it is
        # the sole entity or the user actually listed several components.
        if "plan" in entities and relational_components and not relational_graph and not explicit_plan:
            entities = tuple(entity for entity in entities if entity != "plan")
        # The aggregate plan is the semantic subject when the user explicitly
        # names several plan components. Otherwise preserve the first entity
        # mentioned in natural language for registry candidate ranking.
        primary_entity = "plan" if "plan" in entities and (relational_graph or explicit_plan or compound_plan_subject) else next(
            (entity for entity in entities if entity != "plan"),
            "plan" if "plan" in entities else None,
        )
        references = tuple(
            marker
            for marker, terms in self._REFERENCE_MARKERS.items()
            if self._contains_any(normalized, terms)
        )
        # A bare causal question is only a follow-up when the resolver later
        # finds persisted lineage.  Without that authority it becomes a
        # targeted clarification rather than an unrelated request.
        if re.fullmatch(r"(?:waarom|why|wieso|weshalb|warum)[?!\.\s]*", normalized):
            references = (*references, "previous_verified_conclusion")
        action = self._action_polarity(normalized)
        financial_execution_intent = self._is_explicit_financial_execution_intent(normalized) or bool(
            asset and re.search(r"\b(?:koop\w*|verkoop\w*|buy\w*|sell\w*|place\w*|plaats\w*|submit\w*)\b", normalized)
        )
        ambiguous_reference = self._has_unbound_deictic_reference(normalized, entities)
        if financial_execution_intent:
            action = "execute"
        if action == "add" and re.search(r"\bvolg(?:en)?\b", normalized) and "watchlist" not in entities:
            entities = (*entities, "watchlist")
        discourse = self._discourse_act(normalized, entities, references, action)
        # Asking FINN to help prepare an object establishes a guided
        # interaction boundary. It does not choose an operation; it only lets
        # the selected contract expose its missing inputs as a clarification.
        guidance_requested = self._requests_guidance(normalized)
        # A bare explicit asset is useful only as a possible guided slot answer.
        # The conversation resolver decides whether it fills an open field.
        short_turn = len(re.findall(r"[\w-]+", normalized)) <= 10
        is_interrogative = bool(re.match(r"^(?:welke|welk|wat|waar|hoe|who|what|which|where|how)\b", normalized))
        slot_answer = asset if asset and short_turn and not is_interrogative else None
        if slot_answer is None and short_turn and not is_interrogative:
            timeframe = FinnV2SetupInputCatalog.timeframe_from_text(original)
            if timeframe:
                slot_answer = timeframe
        if slot_answer is None and short_turn and not is_interrogative:
            setup_type = FinnV2SetupInputCatalog.setup_type_from_text(original)
            if setup_type:
                slot_answer = setup_type
        if (
            action == "read"
            and short_turn
            and (not entities or set(entities).issubset({"asset"}))
            and (
                slot_answer is not None
                or re.search(r"\b(?:naam|name|noem\s+(?:hem|haar|het|deze|dit)|ik\s+noem|hij\s+heet|het\s+heet)\b", normalized)
            )
        ):
            discourse = "clarification_answer"
        concept = self._financial_concept(normalized)
        # Conversation acts and product verbs are meaningful FINN requests
        # even where no financial noun appears in this short turn.
        domain_hint = "financial" if (
            entities or asset or concept or references or slot_answer
            or action != "read" or discourse in {"capability", "clarification_answer"}
            or any(term in normalized for term in ("trade", "beleggen", "investment", "rendement", "risk", "risico"))
        ) else "off_topic"
        return FinnV2PreprocessedRequest(
            original_text=original,
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
            domain_hint=domain_hint,
            financial_concept=concept,
            financial_execution_intent=financial_execution_intent,
            ambiguous_reference=ambiguous_reference,
            explicit_plan_subject=explicit_plan,
            linked_graph_relationship=linked_graph_relationship,
            guidance_requested=guidance_requested,
        )

    @staticmethod
    def _financial_concept(text: str) -> Optional[str]:
        concepts = {
            "atr": "ATR",
            "average true range": "ATR",
            "macd": "MACD",
            "rsi": "RSI",
            "relative strength index": "RSI",
            "relatieve sterkte index": "RSI",
            "relatieve-sterkte-index": "RSI",
            "vwap": "VWAP",
            "volume": "volume",
            "moving average": "moving average",
            "voortschrijdend gemiddelde": "moving average",
            "ma200": "MA200",
            "ma_200": "MA200",
            "stop loss": "stop loss",
            "risk reward": "risk reward",
            "dca": "DCA",
            "dollar cost averaging": "dollar cost averaging",
        }
        return next((label for concept, label in concepts.items() if concept in text), None)

    @classmethod
    def _contains_any(cls, text: str, terms: tuple[str, ...]) -> bool:
        words = re.findall(r"[\w-]+", text)
        inflection_stems = {
            "indicator", "signaal", "trendindicator", "setup", "haal", "maak", "voorbereid",
            "toevoeg", "verwijder", "activeer", "bevestig", "formuleer",
            "herformuleer", "herschrijf", "ontbrek", "ontbreek", "inschakel", "erstell", "anleg",
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
                for match in re.finditer(rf"(?<!\w){re.escape(term)}(?!\w)", text)
            ]
            if positions:
                matches.append((min(positions), entity))
        for entity, pattern in cls._COMPOUND_ENTITY_PATTERNS.items():
            if entity in {item for _, item in matches}:
                continue
            compound_match = pattern.search(text)
            if compound_match and any(character.isalpha() for character in text[:compound_match.start()]):
                matches.append((compound_match.start(), entity))
        return {entity: position for position, entity in sorted(matches)}

    @staticmethod
    def _first_term_position(text: str, terms: tuple[str, ...]) -> Optional[int]:
        positions = [
            match.start()
            for term in terms
            for match in re.finditer(rf"(?<!\w){re.escape(term)}(?!\w)", text)
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
        if "live" in text and re.search(r"\b(?:activeer\w*|activate\w*|schakel\w*|inschakel\w*|start\w*|zet|maak\w*)\b", text):
            return "activate"
        if re.search(r"\b(?:echte|reële|live)\s+orders?\b", text) and re.search(
            r"\b(?:plaats\w*|uitvoer\w*|verstuur\w*|verstur\w*)\b", text
        ):
            return "activate"
        if re.search(r"\bpas\b.*\baan\b", text):
            return "update"
        # Delegating autonomous buy/sell decisions is a financial execution
        # safety fact.  This remains independent from the eventual contract
        # selection and prevents an unrecognised provider frame from treating
        # a consequential request as unrelated conversation.
        if self._is_explicit_financial_execution_intent(text):
            return "execute"
        # Evaluate before ordinary request verbs. In a question such as
        # "welke risico's maken ...", the verb describes the diagnosis rather
        # than a request to create anything.
        if self._is_plan_assessment(text):
            return "evaluate"
        # Confirmation qualifies a proposal lifecycle; it never changes the
        # mutation the user is asking FINN to prepare.
        if any(term in text for term in ("watchlist", "volglijst", "marktenlijst")) and self._contains_any(
            text, ("verwijder", "remove", "haal", "verdwijn", "delete", "drop")
        ):
            return "remove"
        if re.search(r"\bwerk\b.*\buit\b", text):
            return "create"
        if "niet langer" in text and any(term in text for term in ("watchlist", "volglijst", "gevolgde", "marktenlijst")):
            return "remove"
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
        if re.search(r"\bneem\b.+\bop\b", text):
            return "add"
        for polarity, terms in self._ACTION_PATTERNS:
            if self._contains_any(text, terms):
                if polarity == "execute" and self._contains_any(text, ("niet", "niets", "zonder")):
                    continue
                return polarity
        return "read"

    @classmethod
    def _is_plan_assessment(cls, text: str) -> bool:
        if not cls._contains_any(text, cls._ENTITY_TERMS["plan"]):
            return False
        return any(
            re.search(rf"(?<!\w){re.escape(term)}\w*(?!\w)", text)
            for term in cls._PLAN_ASSESSMENT_TERMS
        )

    @staticmethod
    def _is_explicit_financial_execution_intent(text: str) -> bool:
        """Recognise a consequential financial delegation, not an operation."""
        finance_object = (
            r"\b(?:portfolio|portefeuille|beleggingsrekening|beleggingsaccount|investment\s+account|"
            r"anlagekonto|broker(?:rekening|account)?|trading\s+account|wallet|orders?|transacties?|"
            r"transactions?|trades?|savings?|spaargeld|vermogen|funds?|kapitaal|coin(?:s)?)\b"
        )
        market_action = (
            r"\b(?:koop\w*|verkoop\w*|buy\w*|sell\w*|trade\w*|handel\w*|"
            r"orders?|move|transfer|verplaats\w*|stort\w*)\b"
        )
        autonomy = r"\b(?:autonoom\w*|autonom\w*|zelfstandig)\b"
        decision = (
            r"\b(?:\w*besluit\w*|beslissing\w*|decision\w*|entscheidung\w*|"
            r"beheer\w*|manage\w*|verwalte\w*|whichever|welke\s+dan\s+ook)\b"
        )
        return bool(
            # Autonomous market delegation is consequential even when the
            # user omits a specific account or portfolio noun.
            (re.search(autonomy, text) and re.search(market_action, text))
            # Delegating the decision authority for a financial account is
            # equally consequential even before the user names a particular
            # buy or sell action. It must remain inside FINN's typed safe
            # financial boundary rather than being treated as unrelated chat.
            or (re.search(finance_object, text) and re.search(autonomy, text) and re.search(decision, text))
            # A financial object plus an action and delegated selection is
            # likewise a financial execution request, not off-topic.
            or (re.search(finance_object, text) and re.search(market_action, text) and re.search(decision, text))
        )

    @staticmethod
    def _requests_guidance(text: str) -> bool:
        """Recognize a collaboration act without assigning a FINN operation."""
        return bool(re.search(
            r"\b(?:help(?:\s+me)?|could\s+you\s+help(?:\s+me)?|"
            r"can\s+you\s+help(?:\s+me)?|kun\s+je\s+(?:mij|me)\s+helpen|"
            r"help\s+(?:mij|me)|ik\s+heb\s+hulp\s+nodig|"
            r"hilf\s+mir|kannst\s+du\s+mir\s+helfen|unterst[üu]tz(?:e)?\s+mich)\b",
            text,
        ))

    @staticmethod
    def _has_unbound_deictic_reference(text: str, entities: tuple[str, ...]) -> bool:
        if entities or len(re.findall(r"[\w-]+", text)) > 8:
            return False
        return bool(re.search(r"\b(?:hetzelfde|dezelfde|dit|dat|ermee|daarmee|it|that|same)\b", text))

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
                "ondersteuning biedt",
                "welke ondersteuning",
                "what support",
            )
        ) or (
            # This captures a broad support question independently of the
            # product name or a particular example wording.
            bool(re.search(r"\b(?:hulp|ondersteuning)\b", text))
            and bool(re.search(r"\b(?:kan|kunnen|bied\w*|helpt?)\b", text))
        ):
            return "capability"
        if "reformulation" in references:
            return "reformulation"
        # A question about the consequence that follows from a prior result
        # remains contextual even when it introduces a concrete FINN object.
        # The selector decides which lineage contract applies; this only keeps
        # the grammatical reference available to that model boundary.
        if re.search(
            r"\b(?:welk(?:e)?|wat)\b(?:\s+\w+){0,4}\s+"
            r"(?:volgt|vloeit\s+voort|komt\s+voort)\s+(?:daaruit|daar\s+uit)\b",
            text,
        ) or re.search(
            r"\b(?:which|what)\b(?:\s+\w+){0,4}\s+"
            r"(?:follows|flows)\s+(?:from\s+that|therefrom)\b",
            text,
        ):
            return "contextual_follow_up"
        if "contextual_implication" in references:
            return "contextual_follow_up"
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
        matches = [
            (match.start(), resolved)
            for match in re.finditer(r"[A-Za-z0-9]+", original)
            if (resolved := resolve_catalog_symbol_in_text(match.group(0)))
        ]
        if not matches:
            return None
        if len(matches) == 1:
            return matches[0][1]

        # A contrast clause distinguishes a mentioned context from the target
        # the user is actually asking FINN to handle. The rule is deliberately
        # syntax-level and catalog-backed; it does not depend on any symbol or
        # individual prompt wording. Without contrast we retain first mention
        # so comparison requests are not silently rewritten into a target.
        normalized = original.casefold()
        contrast = re.search(
            r"\b(?:maar|but|instead|rather|hoewel|although|despite|doch|sondern)\b",
            normalized,
        )
        if contrast:
            after_contrast = [asset for position, asset in matches if position > contrast.start()]
            if after_contrast:
                return after_contrast[-1]
        return matches[0][1]

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
