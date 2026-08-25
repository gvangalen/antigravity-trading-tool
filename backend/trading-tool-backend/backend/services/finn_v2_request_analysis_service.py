from __future__ import annotations

import re
from typing import Dict, List, Optional

from backend.domain.finn_v2_operation_registry import FinnV2OperationRegistry, FinnV2OperationUnavailableError
from backend.schemas.finn_v2_orchestrator_schema import RequestAnalysisResult, RequestPlan
from backend.services.finn_v2_capability_registry_service import FinnV2CapabilityRegistryService
from backend.services.finn_v2_operation_state_service import FinnV2OperationStateService
from backend.services.finn_v2_operation_classification_service import (
    FinnV2OperationClassificationService,
    FinnV2OperationClassificationValidator,
)
from backend.services.asset_catalog_service import DEFAULT_ASSET_CATALOG


class FinnV2RequestAnalysisService:
    _ASSET_ALIASES = {
        "BITCOIN": "BTC",
        "BTC": "BTC",
        "APPLE": "AAPL",
        "AAPL": "AAPL",
        "ETHEREUM": "ETH",
        "ETH": "ETH",
        "SOLANA": "SOL",
        "SOL": "SOL",
    }

    def __init__(self):
        self.capabilities = FinnV2CapabilityRegistryService()
        self.operations = FinnV2OperationRegistry()
        self.operation_state = FinnV2OperationStateService()
        self.classifier = FinnV2OperationClassificationService(self.operations)
        self.classification_validator = FinnV2OperationClassificationValidator()

    def analyze(
        self,
        *,
        message: str,
        workspace_hints: Optional[Dict[str, object]] = None,
        client_context: Optional[Dict[str, object]] = None,
        conversation_context: Optional[Dict[str, object]] = None,
    ) -> RequestAnalysisResult:
        text = str(message or "").strip()
        normalized = self._normalize_text(text)
        semantic = self.classifier.classify(message=text, conversation_context=conversation_context)
        matched_signals: List[str] = []
        unresolved_signals: List[str] = []

        scopes = self._subject_scopes(normalized, matched_signals)
        # An integrated assessment is about the user's plan even when the
        # message uses a natural reference such as "het hele plaatje".
        integrated_plan = self._is_integrated_plan_request(normalized) or len(
            set(scopes).intersection({"profile", "indicators", "setup", "strategy", "bot"})
        ) >= 3
        if integrated_plan:
            for scope in ["profile", "indicators", "setup", "strategy", "bot"]:
                if scope not in scopes:
                    scopes.append(scope)
                    matched_signals.append(f"scope:{scope}:integrated_plan")
        message_asset = self._extract_asset(text, normalized)
        explicit_asset = message_asset or self._asset_from_context(
            workspace_hints=workspace_hints,
            client_context=client_context,
        )
        explicit_setup_id = self._extract_entity_id(text, "setup")
        explicit_strategy_id = self._extract_entity_id(text, "strateg")
        explicit_bot_id = self._extract_entity_id(text, "bot")
        uses_conversation_reference = self._uses_conversation_reference(normalized)
        # "staat die live" is a normal Dutch relative reference to an
        # explicitly requested bot, not a reference to a prior turn.
        if "staat die live" in normalized:
            uses_conversation_reference = False
        if uses_conversation_reference:
            context = conversation_context or {}
            explicit_asset = explicit_asset or self._context_asset(context.get("resolved_asset"))
            explicit_setup_id = explicit_setup_id or self._context_entity_id(context.get("resolved_setup_id"))
            explicit_strategy_id = explicit_strategy_id or self._context_entity_id(context.get("resolved_strategy_id"))
            explicit_bot_id = explicit_bot_id or self._context_entity_id(context.get("resolved_bot_id"))
        requested_entities = self._requested_entities(
            explicit_asset=explicit_asset,
            explicit_setup_id=explicit_setup_id,
            explicit_strategy_id=explicit_strategy_id,
            explicit_bot_id=explicit_bot_id,
        )
        if (
            explicit_asset
            and self._looks_like_asset_question(normalized)
            and "asset" not in scopes
            and not set(scopes).intersection({"profile", "indicators", "setup", "strategy", "bot", "watchlist"})
        ):
            scopes.append("asset")
            matched_signals.append("scope:asset:resolved_context")
        interaction_mode = self._interaction_mode(normalized, scopes, matched_signals, explicit_asset=explicit_asset)
        if uses_conversation_reference:
            interaction_mode, scopes = self._apply_conversation_reference(
                normalized=normalized,
                interaction_mode=interaction_mode,
                scopes=scopes,
                conversation_context=conversation_context or {},
                matched_signals=matched_signals,
                unresolved_signals=unresolved_signals,
            )
        if interaction_mode == "UNAVAILABLE" and "mode:unavailable_financial_context" in matched_signals:
            scopes = []
        primary_subject = self._primary_subject(scopes=scopes, interaction_mode=interaction_mode, normalized=normalized)
        action_risk_class = self._action_risk_class(normalized=normalized, interaction_mode=interaction_mode)

        requires_gap_analysis = any(
            token in normalized
            for token in ["ontbreekt", "ontbrekende", "ontbrekend", "missing", "mist", "gap", "perspectief ontbreekt"]
        )
        requires_comparison = any(
            token in normalized
            for token in ["vergelijk", "compare", "versus", "vs", "past", "fit", "conflict", "risico", "risk"]
        )
        requests_change = interaction_mode in {"CREATE_PROPOSAL", "ACTION_PROPOSAL", "CONFIRMATION", "EXECUTION"}
        requests_execution = interaction_mode == "EXECUTION"
        missing_essential_inputs = self._missing_essential_inputs(
            interaction_mode=interaction_mode,
            primary_subject=primary_subject,
            explicit_asset=explicit_asset,
            normalized=normalized,
        )

        if interaction_mode == "CAPABILITY":
            scopes = ["capability"]
        elif not scopes:
            scopes = ["unknown"]
            unresolved_signals.append("no_financial_scope_detected")
        if interaction_mode == "UNAVAILABLE":
            unresolved_signals.append("financial_domain_unavailable")
        if interaction_mode == "UNAVAILABLE" and "mode:unavailable_financial_context" in matched_signals:
            unresolved_signals.append("insufficient_trade_context")

        confidence = self._confidence(scopes=scopes, matched_signals=matched_signals, interaction_mode=interaction_mode)
        # New V2 runs select their operation exclusively through the semantic
        # front door.  The legacy analyzer remains below only to reconstruct
        # historical planless records, never to choose a new contract.
        operation_id = semantic.operation_id
        pending_operation_id = self.operation_state.pending_operation_id(conversation_context or {})
        if (
            pending_operation_id
            and semantic.discourse == "clarification_answer"
            and semantic.action == "unknown"
        ):
            operation_id = pending_operation_id
        if uses_conversation_reference and "conversation_reference_without_verified_context" in unresolved_signals:
            operation_id = "clarify_request"
        # A pending guided operation owns bare follow-up values such as a setup
        # name, but it must never hijack a later explicit product operation.
        # This keeps one conversation useful without turning a watchlist request
        # into a continuation of an unfinished setup proposal.
        if (
            pending_operation_id
            and operation_id in {"clarify_request", "unavailable"}
            and "mode:unavailable_financial_context" not in matched_signals
        ):
            operation_id = pending_operation_id
        try:
            operation = self.operations.require_supported(operation_id)
        except FinnV2OperationUnavailableError as exc:
            # An unavailable registry capability cannot fall through to a
            # legacy planner or business write path.
            operation_id = "unavailable"
            operation = self.operations.require_supported(operation_id)
            interaction_mode = "UNAVAILABLE"
            unresolved_signals.append(str(exc))
        else:
            # The registry owns the persisted mode for every new request.
            interaction_mode = operation.mode
            if not self.classification_validator.validate(semantic):
                operation_id = "clarify_request"
                operation = self.operations.require_supported(operation_id)
                interaction_mode = operation.mode
                unresolved_signals.append("operation_action_mismatch")
        # A workspace asset may enrich a setup draft, but it is never a
        # substitute for the asset explicitly requested by a write operation.
        operation_asset = (
            message_asset
            if operation_id in {"watchlist_add", "watchlist_remove"}
            else explicit_asset
        )
        guided_state = self.operation_state.resolve(
            contract=operation,
            message=text,
            explicit_asset=operation_asset,
            conversation_context=conversation_context,
        ) if operation.required_inputs else None
        if guided_state is not None:
            missing_essential_inputs = list(guided_state.missing_required_inputs)
        request_plan = self._request_plan(
            interaction_mode=interaction_mode,
            scopes=scopes,
            primary_subject=primary_subject,
            normalized=normalized,
            confidence=confidence,
            conversation_context=conversation_context or {},
            integrated_plan=integrated_plan,
            missing_essential_inputs=missing_essential_inputs,
            uses_conversation_reference=uses_conversation_reference,
            explicit_asset=explicit_asset,
            explicit_setup_id=explicit_setup_id,
            explicit_strategy_id=explicit_strategy_id,
            explicit_bot_id=explicit_bot_id,
            operation_id=operation_id,
            operation=operation,
            operation_state=guided_state.dict() if guided_state is not None else {},
            context_asset=self._asset_from_context(workspace_hints=workspace_hints, client_context=client_context),
            target_asset=message_asset if operation_id in {"watchlist_add", "watchlist_remove"} else None,
            requested_action=semantic.action if semantic.action != "unknown" else None,
            discourse_type=semantic.discourse,
        )

        return RequestAnalysisResult(
            interaction_mode=interaction_mode,
            subject_scopes=scopes,
            explicit_asset=explicit_asset,
            explicit_setup_id=explicit_setup_id,
            explicit_strategy_id=explicit_strategy_id,
            explicit_bot_id=explicit_bot_id,
            primary_subject=primary_subject,
            requested_entities=requested_entities,
            output_contract=operation.response_strategy if operation is not None else "unavailable",
            action_risk_class=action_risk_class,
            missing_essential_inputs=missing_essential_inputs,
            requires_comparison=requires_comparison,
            requires_gap_analysis=requires_gap_analysis,
            requests_change=requests_change,
            requests_execution=requests_execution,
            confidence=confidence,
            matched_signals=matched_signals,
            unresolved_signals=unresolved_signals,
            reasoning_required=bool(operation is not None and operation.model_policy != "never"),
            request_plan=request_plan,
        )

    def _request_plan(
        self,
        *,
        interaction_mode: str,
        scopes: List[str],
        primary_subject: Optional[str],
        normalized: str,
        integrated_plan: bool,
        confidence: str,
        conversation_context: Dict[str, object],
        missing_essential_inputs: List[str],
        uses_conversation_reference: bool,
        explicit_asset: Optional[str],
        explicit_setup_id: Optional[int],
        explicit_strategy_id: Optional[int],
        explicit_bot_id: Optional[int],
        operation_id: str,
        operation,
        operation_state: Dict[str, object],
        context_asset: Optional[str],
        target_asset: Optional[str],
        requested_action: Optional[str],
        discourse_type: str,
    ) -> RequestPlan:
        reference = None
        if uses_conversation_reference:
            reference = str(conversation_context.get("last_user_goal") or "previous_verified_response")
        score = {"high": 0.9, "medium": 0.7, "low": 0.4, "none": 0.0}[confidence]
        return RequestPlan(
            user_goal=self._user_goal(interaction_mode, primary_subject, normalized, integrated_plan),
            operation_id=operation_id,
            operation_contract_version=getattr(operation, "version", None),
            interaction_mode=interaction_mode,
            primary_domains=list(scopes),
            required_information_scopes=list(getattr(operation, "required_scopes", ())),
            optional_information_scopes=list(getattr(operation, "optional_scopes", ())),
            requested_operation=operation_id if interaction_mode in {"CREATE_PROPOSAL", "ACTION_PROPOSAL", "CONFIRMATION", "EXECUTION"} else None,
            conversation_reference=reference,
            referenced_entities={
                key: value
                for key, value in {
                    "asset": explicit_asset,
                    "setup_id": explicit_setup_id,
                    "strategy_id": explicit_strategy_id,
                    "bot_id": explicit_bot_id,
                }.items()
                if value is not None
            },
            missing_information=list(missing_essential_inputs),
            operation_state=operation_state,
            context_asset=context_asset,
            target_asset=target_asset,
            requested_action=requested_action,
            discourse_type=discourse_type,
            clarification_required=bool(missing_essential_inputs) or interaction_mode == "CLARIFICATION",
            confidence_score=score,
        )

    @staticmethod
    def _operation_id(
        *,
        interaction_mode: str,
        primary_subject: Optional[str],
        scopes: List[str],
        normalized: str,
        integrated_plan: bool,
        uses_conversation_reference: bool,
    ) -> str:
        if uses_conversation_reference and any(token in normalized for token in ("korter", "anders", "herformuleer")):
            return "reformulate_previous_response"
        if uses_conversation_reference and any(token in normalized for token in ("onderbouw", "waar baseer")):
            return "explain_previous_evidence"
        if interaction_mode == "CAPABILITY":
            return "capability"
        if interaction_mode == "UNAVAILABLE":
            return "unavailable"
        if interaction_mode == "CLARIFICATION":
            return "clarify_request"
        if interaction_mode == "CONFIRMATION":
            return "confirm_proposal"
        if interaction_mode == "EXECUTION":
            return "execute_proposal"
        if interaction_mode == "CREATE_PROPOSAL":
            return {"setup": "create_setup", "strategy": "create_strategy", "bot": "create_bot"}.get(primary_subject or "", "clarify_request")
        if interaction_mode == "ACTION_PROPOSAL":
            if primary_subject == "watchlist":
                return "watchlist_add" if any(token in normalized for token in ("voeg", "add", "toevoeg")) else "watchlist_remove"
            if primary_subject == "bot" and "live" in normalized:
                return "activate_bot"
            return "clarify_request"
        if interaction_mode == "EVALUATE":
            if "reflection" in scopes or "daily_report" in scopes:
                return "evaluate_review_history"
            if integrated_plan:
                return "evaluate_plan"
            return {
                "indicators": "evaluate_indicator_configuration", "setup": "evaluate_setup",
                "strategy": "evaluate_strategy", "bot": "evaluate_bot", "portfolio": "evaluate_portfolio",
            }.get(primary_subject or "", "evaluate_plan")
        if "bot" in scopes:
            return "read_linked_bot"
        return {
            "asset": "read_active_asset", "watchlist": "read_watchlist", "indicators": "read_indicator_configuration",
            "setup": "read_active_setup", "strategy": "read_linked_strategy", "bot": "read_linked_bot",
            "portfolio": "read_portfolio", "daily_report": "read_latest_report", "reflection": "read_review_history",
        }.get(primary_subject or "", "clarify_request")

    @staticmethod
    def _user_goal(interaction_mode: str, primary_subject: Optional[str], normalized: str, integrated_plan: bool) -> str:
        if interaction_mode == "EVALUATE" and integrated_plan:
            return "evaluate_complete_plan"
        if interaction_mode == "CREATE_PROPOSAL" and primary_subject == "setup":
            return "propose_setup"
        if interaction_mode == "ACTION_PROPOSAL" and primary_subject == "watchlist":
            return "propose_watchlist_change"
        if interaction_mode == "READ":
            return f"read_{primary_subject or 'context'}"
        return interaction_mode.casefold()

    def _subject_scopes(self, normalized: str, matched_signals: List[str]) -> List[str]:
        scope_keywords = {
            "capability": ["wat kun je", "waarmee help", "what can you do", "wat doet finn", "how can you help", "hoe kun je mij helpen"],
            "profile": ["profiel", "profile", "risicoprofiel", "risk profile", "tradingstijl", "trading style", "stijl"],
            "asset": ["actieve asset", "asset heb ik actief", "active asset", "gekozen asset", "huidige instrument", "coin of aandeel", "instrument"],
            "analysis": ["analyse", "analysis", "markt", "market", "macro", "technical", "technisch", "context"],
            "indicators": [
                "indicator", "indicatoren", "indicators", "signaal", "signalen", "rsi", "macd", "dxy",
                "volume", "vwap", "moving average", "ma_", "marktregime", "market regime",
            ],
            "watchlist": ["watchlist", "volglijst", "te volgen", "to follow"],
            "setup": ["setup", "set-up"],
            "strategy": ["strategie", "strategy", "plan"],
            "bot": ["bot", "automation", "automatisering", "live"],
            "daily_report": ["rapport", "report", "dagrapport", "daily report"],
            "reflection": ["reflectie", "reflection", "review", "terugblik"],
            "portfolio": ["portfolio", "portefeuille"],
        }
        scopes: List[str] = []
        for scope, keywords in scope_keywords.items():
            if any(keyword in normalized for keyword in keywords):
                scopes.append(scope)
                matched_signals.append(f"scope:{scope}")
        return scopes

    def _interaction_mode(self, normalized: str, scopes: List[str], matched_signals: List[str], *, explicit_asset: Optional[str]) -> str:
        if "capability" in scopes or self._is_capability_question(normalized):
            matched_signals.append("mode:capability")
            return "CAPABILITY"
        unavailable_financial_tokens = [
            "beste trade",
            "best trade",
            "wat moet ik kopen",
            "what should i buy",
            "wat moet ik traden",
        ]
        if any(token in normalized for token in unavailable_financial_tokens) and not any(
            scope in scopes for scope in {"profile", "indicators", "setup", "strategy", "bot", "portfolio"}
        ):
            matched_signals.append("mode:unavailable_financial_context")
            return "UNAVAILABLE"
        execution_tokens = ["bevestig", "confirm", "voer nu uit", "execute now", "nu uitvoeren"]
        confirmation_tokens = ["kan je dit bevestigen", "kun je dit bevestigen", "bevestiging", "confirmation", "wil je bevestigen"]
        action_tokens = [
            "zet",
            "activeer",
            "voer",
            "execute",
            "activate",
            "run this",
            "go live",
            "zet live",
            "start live trading",
            "voeg toe aan watchlist",
            "voeg toe aan mijn watchlist",
            "add to watchlist",
            "add to my watchlist",
            "verwijder uit watchlist",
            "verwijder uit mijn watchlist",
            "remove from watchlist",
            "remove from my watchlist",
        ]
        proposal_tokens = ["voeg", "add", "maak een voorstel", "stel", "voorstel", "proposal", "concept", "voorbereiden", "bereid", "toevoegen", "aanpassen", "wijzig", "change", "adjust", "maak een setup", "create setup", "setupconcept"]
        evaluation_tokens = [
            "beoordeel",
            "evaluate",
            "past",
            "fit",
            "risico",
            "risk",
            "ontbreekt",
            "missing",
            "belangrijkste",
            "grootste",
            "compare",
            "vergelijk",
            "conflict",
            "hele plaatje",
            "hele plan",
            "waar wringt",
            "zwakste punt",
            "vertrouwen",
            "welke voorwaarde",
            "weegt",
            "wat betekent dat plan",
            "als ik morgen niets wijzig",
        ]
        read_tokens = ["welke", "what", "which", "staat", "is", "wat", "who", "where", "bekijk", "toon", "show"]

        if self._contains_any_phrase(normalized, execution_tokens):
            matched_signals.append("mode:execution")
            return "EXECUTION"
        if self._contains_any_phrase(normalized, confirmation_tokens):
            matched_signals.append("mode:confirmation")
            return "CONFIRMATION"
        if ("watchlist" in scopes or "watchlist" in normalized or "volglijst" in normalized) and any(
            self._contains_phrase(normalized, token) for token in ("voeg", "add", "verwijder", "remove", "haal", "zet", "toevoegen", "volgen")
        ):
            matched_signals.append("mode:action_proposal")
            return "ACTION_PROPOSAL"
        if "setup" in scopes and self._contains_any_phrase(normalized, proposal_tokens):
            matched_signals.append("mode:create_proposal")
            return "CREATE_PROPOSAL"
        no_execution_phrase = any(phrase in normalized for phrase in ["voer niets uit", "niet uitvoeren", "nog niet opslaan"])
        if self._contains_any_phrase(normalized, action_tokens) and not no_execution_phrase:
            matched_signals.append("mode:action_proposal")
            return "ACTION_PROPOSAL"
        if "live" in normalized and "bot" in scopes and any(token in normalized for token in ["activeer", "activate", "zet", "maak", "start"]):
            matched_signals.append("mode:action_proposal")
            return "ACTION_PROPOSAL"
        if self._contains_any_phrase(normalized, proposal_tokens):
            matched_signals.append("mode:create_proposal")
            return "CREATE_PROPOSAL"
        if self._contains_any_phrase(normalized, evaluation_tokens):
            matched_signals.append("mode:evaluate")
            return "EVALUATE"
        if explicit_asset and any(self._contains_phrase(normalized, token) for token in ("voeg", "add", "verwijder", "remove", "haal")):
            matched_signals.append("mode:action_proposal")
            return "ACTION_PROPOSAL"
        if scopes and self._contains_any_phrase(normalized, read_tokens):
            matched_signals.append("mode:read")
            return "READ"
        if scopes:
            matched_signals.append("mode:read_inferred")
            return "READ"
        return "UNAVAILABLE"

    @staticmethod
    def _is_integrated_plan_request(normalized: str) -> bool:
        direct_integrated_reference = any(
            phrase in normalized
            for phrase in [
                "hele plaatje",
                "hele plan",
                "zwakste punt",
                "waar wringt",
                "belangrijkste ontbrekende onderdeel",
                "welke voorwaarde ontbreekt",
            ]
        )
        # Natural references include compounds such as "BTC-plan" and phrases
        # like "mijn volledige plan". Tokenizing punctuation prevents the
        # strategy keyword "plan" from narrowing these requests to one domain.
        plan_tokens = set(re.findall(r"[a-z0-9]+", normalized))
        plan_reference = "plan" in plan_tokens or any(phrase in normalized for phrase in ["mijn plan", "dat plan"])
        evaluation_language = any(
            phrase in normalized
            for phrase in ["beoordeel", "bekijk", "ontbreekt", "risico", "vertrouwen", "verbeter", "betekent"]
        )
        return direct_integrated_reference or (plan_reference and evaluation_language)

    def _extract_asset(self, original: str, normalized: str) -> Optional[str]:
        for token, asset in self._ASSET_ALIASES.items():
            if re.search(rf"\b{re.escape(token)}\b", normalized):
                return asset
        explicit_candidates = re.findall(r"\b[A-Z]{2,6}\b", original)
        for candidate in explicit_candidates:
            normalized_candidate = candidate.strip().upper()
            # The catalog is the product authority for supported symbols. This
            # avoids maintaining a smaller FINN-only alias list that can reject
            # a valid, confirmable watchlist target such as XRP.
            if normalized_candidate in DEFAULT_ASSET_CATALOG:
                return normalized_candidate
        return None

    def _extract_entity_id(self, original: str, keyword_root: str) -> Optional[int]:
        match = re.search(rf"\b{keyword_root}[a-z]*\s+#?(\d+)\b", original, re.IGNORECASE)
        if not match:
            return None
        try:
            value = int(match.group(1))
        except ValueError:
            return None
        return value if value > 0 else None

    def _normalize_text(self, text: str) -> str:
        return re.sub(r"\s+", " ", text.casefold()).strip()

    @staticmethod
    def _uses_conversation_reference(normalized: str) -> bool:
        return any(
            re.search(rf"(?<!\w){re.escape(token)}(?!\w)", normalized)
            for token in [
                "die", "dat", "eerder", "onderbouw", "waar baseer",
                "korter", "anders", "herformuleer", "dezelfde conclusie",
            ]
        )

    def _is_capability_question(self, normalized: str) -> bool:
        if self.capabilities.is_capability_question(normalized):
            return True
        words = set(re.findall(r"[\w-]+", normalized))
        asks_how = bool(words.intersection({"hoe", "how", "wat", "what"}))
        asks_help = bool(words.intersection({"help", "helpen", "kan", "can", "doen", "do"}))
        return asks_how and asks_help and bool(words.intersection({"finn", "tradingcoach", "assistant", "coach"}))

    @staticmethod
    def _asset_from_context(
        *,
        workspace_hints: Optional[Dict[str, object]],
        client_context: Optional[Dict[str, object]],
    ) -> Optional[str]:
        for context in (workspace_hints or {}, client_context or {}):
            for key in ("asset", "symbol", "active_asset"):
                value = str(context.get(key) or "").strip().upper()
                if value:
                    return value
        return None

    @staticmethod
    def _looks_like_asset_question(normalized: str) -> bool:
        return any(token in normalized for token in [
            "asset", "instrument", "symbool", "symbol", "workspace", "markt", "market", "geselecteerd", "selected", "actief", "active", "huidig", "current",
        ])

    def _apply_conversation_reference(
        self,
        *,
        normalized: str,
        interaction_mode: str,
        scopes: List[str],
        conversation_context: Dict[str, object],
        matched_signals: List[str],
        unresolved_signals: List[str],
    ) -> tuple[str, List[str]]:
        if not conversation_context.get("last_verified_conclusion"):
            unresolved_signals.append("conversation_reference_without_verified_context")
            return "CLARIFICATION", scopes
        inherited_scopes = list(conversation_context.get("last_primary_domains") or [])
        if inherited_scopes:
            scopes = inherited_scopes
        prior_mode = str(conversation_context.get("last_mode") or "READ")
        if any(token in normalized for token in ["korter", "anders", "herformuleer", "dezelfde conclusie"]):
            matched_signals.append("conversation:rephrase_verified_conclusion")
            return prior_mode if prior_mode in {"READ", "EVALUATE"} else "READ", scopes
        if any(token in normalized for token in ["onderbouw", "waar baseer"]):
            matched_signals.append("conversation:explain_verified_conclusion")
            return prior_mode if prior_mode in {"READ", "EVALUATE"} else "READ", scopes
        return interaction_mode, scopes

    @staticmethod
    def _context_asset(value: object) -> Optional[str]:
        normalized = str(value or "").strip().upper()
        return normalized or None

    @staticmethod
    def _context_entity_id(value: object) -> Optional[int]:
        try:
            entity_id = int(value)
        except (TypeError, ValueError):
            return None
        return entity_id if entity_id > 0 else None

    def _contains_any_phrase(self, normalized: str, phrases: List[str]) -> bool:
        return any(self._contains_phrase(normalized, phrase) for phrase in phrases)

    def _contains_phrase(self, normalized: str, phrase: str) -> bool:
        return bool(re.search(rf"(?<!\w){re.escape(phrase.casefold())}(?!\w)", normalized))

    def _confidence(self, *, scopes: List[str], matched_signals: List[str], interaction_mode: str) -> str:
        if interaction_mode == "UNAVAILABLE":
            return "none"
        if len(scopes) >= 2 and len(matched_signals) >= 3:
            return "high"
        if scopes:
            return "medium"
        return "low"

    def _requested_entities(
        self,
        *,
        explicit_asset: Optional[str],
        explicit_setup_id: Optional[int],
        explicit_strategy_id: Optional[int],
        explicit_bot_id: Optional[int],
    ) -> List[str]:
        entities: List[str] = []
        if explicit_asset:
            entities.append("asset")
        if explicit_setup_id:
            entities.append("setup")
        if explicit_strategy_id:
            entities.append("strategy")
        if explicit_bot_id:
            entities.append("bot")
        return entities

    def _primary_subject(self, *, scopes: List[str], interaction_mode: str, normalized: str) -> Optional[str]:
        if interaction_mode == "CAPABILITY":
            return "assistant"
        if interaction_mode == "ACTION_PROPOSAL" and ("watchlist" in normalized or "volglijst" in normalized):
            return "watchlist"
        if interaction_mode == "CREATE_PROPOSAL" and "setup" in normalized:
            return "setup"
        preferred = ["bot", "strategy", "setup", "indicators", "asset", "analysis", "profile", "portfolio", "daily_report", "reflection"]
        for scope in preferred:
            if scope in scopes:
                return scope
        return scopes[0] if scopes else None

    def _output_contract(self, *, interaction_mode: str, primary_subject: Optional[str]) -> Optional[str]:
        if interaction_mode == "READ":
            return f"read_{primary_subject or 'context'}"
        if interaction_mode == "EVALUATE":
            return f"evaluate_{primary_subject or 'context'}"
        if interaction_mode == "CREATE_PROPOSAL":
            return "proposal_setup_change"
        if interaction_mode == "ACTION_PROPOSAL":
            return "proposal_action_change"
        if interaction_mode == "CLARIFICATION":
            return "clarification"
        if interaction_mode == "CONFIRMATION":
            return "confirmation"
        if interaction_mode == "EXECUTION":
            return "execution_result"
        if interaction_mode == "CAPABILITY":
            return "capability_overview"
        if interaction_mode == "UNAVAILABLE":
            return "safe_unavailable"
        return None

    def _action_risk_class(self, *, normalized: str, interaction_mode: str) -> Optional[str]:
        if interaction_mode not in {"ACTION_PROPOSAL", "CONFIRMATION", "EXECUTION"}:
            return None
        if "watchlist" in normalized or "volglijst" in normalized:
            return "watchlist_change"
        if "live" in normalized:
            return "live_action"
        return "paper_action"

    def _missing_essential_inputs(
        self,
        *,
        interaction_mode: str,
        primary_subject: Optional[str],
        explicit_asset: Optional[str],
        normalized: str,
    ) -> List[str]:
        missing: List[str] = []
        if interaction_mode in {"CREATE_PROPOSAL", "ACTION_PROPOSAL"} and primary_subject in {"setup", "strategy", "bot", "watchlist"}:
            if explicit_asset is None and "deze asset" not in normalized and "mijn actieve" not in normalized and "mijn " not in normalized:
                missing.append("asset")
        return missing
