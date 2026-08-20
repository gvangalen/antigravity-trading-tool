from __future__ import annotations

import re
from typing import Dict, List, Optional

from backend.schemas.finn_v2_orchestrator_schema import RequestAnalysisResult
from backend.services.finn_v2_capability_registry_service import FinnV2CapabilityRegistryService


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

    def analyze(
        self,
        *,
        message: str,
        workspace_hints: Optional[Dict[str, object]] = None,
        client_context: Optional[Dict[str, object]] = None,
    ) -> RequestAnalysisResult:
        text = str(message or "").strip()
        normalized = self._normalize_text(text)
        matched_signals: List[str] = []
        unresolved_signals: List[str] = []

        scopes = self._subject_scopes(normalized, matched_signals)
        explicit_asset = self._extract_asset(text, normalized)
        explicit_setup_id = self._extract_entity_id(text, "setup")
        explicit_strategy_id = self._extract_entity_id(text, "strateg")
        explicit_bot_id = self._extract_entity_id(text, "bot")
        requested_entities = self._requested_entities(
            explicit_asset=explicit_asset,
            explicit_setup_id=explicit_setup_id,
            explicit_strategy_id=explicit_strategy_id,
            explicit_bot_id=explicit_bot_id,
        )
        interaction_mode = self._interaction_mode(normalized, scopes, matched_signals, explicit_asset=explicit_asset)
        if interaction_mode == "UNAVAILABLE" and "mode:unavailable_financial_context" in matched_signals:
            scopes = []
        primary_subject = self._primary_subject(scopes=scopes, interaction_mode=interaction_mode, normalized=normalized)
        output_contract = self._output_contract(interaction_mode=interaction_mode, primary_subject=primary_subject)
        action_risk_class = self._action_risk_class(normalized=normalized, interaction_mode=interaction_mode)

        requires_gap_analysis = any(
            token in normalized
            for token in ["ontbreekt", "ontbrekende", "ontbrekend", "missing", "mist", "gap", "perspectief ontbreekt"]
        )
        requires_comparison = any(
            token in normalized
            for token in ["vergelijk", "compare", "versus", "vs", "past", "fit", "conflict", "risico", "risk"]
        )
        requests_change = interaction_mode in {"CREATE_PROPOSAL", "ACTION_PROPOSAL", "PROPOSAL", "ACTION", "CONFIRMATION", "EXECUTION"}
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

        return RequestAnalysisResult(
            interaction_mode=interaction_mode,
            subject_scopes=scopes,
            explicit_asset=explicit_asset,
            explicit_setup_id=explicit_setup_id,
            explicit_strategy_id=explicit_strategy_id,
            explicit_bot_id=explicit_bot_id,
            primary_subject=primary_subject,
            requested_entities=requested_entities,
            output_contract=output_contract,
            action_risk_class=action_risk_class,
            missing_essential_inputs=missing_essential_inputs,
            requires_comparison=requires_comparison,
            requires_gap_analysis=requires_gap_analysis,
            requests_change=requests_change,
            requests_execution=requests_execution,
            confidence=confidence,
            matched_signals=matched_signals,
            unresolved_signals=unresolved_signals,
            reasoning_required=interaction_mode in {
                "CAPABILITY",
                "READ",
                "EVALUATE",
                "CREATE_PROPOSAL",
                "ACTION_PROPOSAL",
                "CONFIRMATION",
                "EXECUTION",
                "FACT",
                "EVALUATION",
                "PROPOSAL",
                "ACTION",
            },
        )

    def _subject_scopes(self, normalized: str, matched_signals: List[str]) -> List[str]:
        scope_keywords = {
            "capability": ["wat kun je", "where can you help", "what can you do", "wat doet finn", "how can you help"],
            "profile": ["profiel", "profile", "risicoprofiel", "risk profile", "tradingstijl", "trading style", "stijl"],
            "analysis": ["analyse", "analysis", "markt", "market", "macro", "technical", "technisch", "context"],
            "indicators": ["indicator", "indicatoren", "indicators", "rsi", "macd", "dxy"],
            "watchlist": ["watchlist", "volglijst"],
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
        if self.capabilities.is_capability_question(normalized):
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
            "voeg toe aan watchlist",
            "voeg toe aan mijn watchlist",
            "add to watchlist",
            "add to my watchlist",
            "verwijder uit watchlist",
            "verwijder uit mijn watchlist",
            "remove from watchlist",
            "remove from my watchlist",
        ]
        proposal_tokens = ["voeg", "add", "maak een voorstel", "proposal", "aanpassen", "wijzig", "change", "adjust", "maak een setup", "create setup"]
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
        ]
        read_tokens = ["welke", "what", "which", "staat", "is", "wat", "who", "where", "bekijk", "toon", "show"]

        if self._contains_any_phrase(normalized, execution_tokens):
            matched_signals.append("mode:execution")
            return "EXECUTION"
        if self._contains_any_phrase(normalized, confirmation_tokens):
            matched_signals.append("mode:confirmation")
            return "CONFIRMATION"
        if ("watchlist" in normalized or "volglijst" in normalized) and any(
            self._contains_phrase(normalized, token) for token in ("voeg", "add", "verwijder", "remove", "haal")
        ):
            matched_signals.append("mode:action_proposal")
            return "ACTION_PROPOSAL"
        if self._contains_any_phrase(normalized, action_tokens):
            matched_signals.append("mode:action_proposal")
            return "ACTION_PROPOSAL"
        if "live" in normalized and "bot" in scopes and any(token in normalized for token in ["activeer", "activate", "zet"]):
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

    def _extract_asset(self, original: str, normalized: str) -> Optional[str]:
        for token, asset in self._ASSET_ALIASES.items():
            if re.search(rf"\b{re.escape(token)}\b", normalized):
                return asset
        explicit_candidates = re.findall(r"\b[A-Z]{2,6}\b", original)
        for candidate in explicit_candidates:
            normalized_candidate = candidate.strip().upper()
            if normalized_candidate in self._ASSET_ALIASES.values():
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
        preferred = ["bot", "strategy", "setup", "indicators", "analysis", "profile", "portfolio", "daily_report", "reflection"]
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
