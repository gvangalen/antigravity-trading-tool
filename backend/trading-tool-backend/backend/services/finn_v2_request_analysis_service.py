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
        interaction_mode = self._interaction_mode(normalized, scopes, matched_signals)
        if interaction_mode == "UNAVAILABLE" and "mode:unavailable_financial_context" in matched_signals:
            scopes = []
        explicit_asset = self._extract_asset(text, normalized)
        explicit_setup_id = self._extract_entity_id(text, "setup")
        explicit_strategy_id = self._extract_entity_id(text, "strateg")
        explicit_bot_id = self._extract_entity_id(text, "bot")

        requires_gap_analysis = any(
            token in normalized
            for token in ["ontbreekt", "ontbrekende", "ontbrekend", "missing", "mist", "gap", "perspectief ontbreekt"]
        )
        requires_comparison = any(
            token in normalized
            for token in ["vergelijk", "compare", "versus", "vs", "past", "fit", "conflict", "risico", "risk"]
        )
        requests_change = interaction_mode in {"PROPOSAL", "ACTION"}
        requests_execution = interaction_mode == "ACTION"

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
            requires_comparison=requires_comparison,
            requires_gap_analysis=requires_gap_analysis,
            requests_change=requests_change,
            requests_execution=requests_execution,
            confidence=confidence,
            matched_signals=matched_signals,
            unresolved_signals=unresolved_signals,
            reasoning_required=interaction_mode in {"CAPABILITY", "EVALUATION", "PROPOSAL", "ACTION"},
        )

    def _subject_scopes(self, normalized: str, matched_signals: List[str]) -> List[str]:
        scope_keywords = {
            "capability": ["wat kun je", "where can you help", "what can you do", "wat doet finn", "how can you help"],
            "profile": ["profiel", "profile", "risicoprofiel", "risk profile", "tradingstijl", "trading style", "stijl"],
            "analysis": ["analyse", "analysis", "markt", "market", "macro", "technical", "technisch", "context"],
            "indicators": ["indicator", "indicatoren", "indicators", "rsi", "macd", "dxy"],
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

    def _interaction_mode(self, normalized: str, scopes: List[str], matched_signals: List[str]) -> str:
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
        action_tokens = ["zet", "activeer", "voer", "execute", "activate", "run this", "go live", "zet live"]
        proposal_tokens = ["voeg", "add", "maak een voorstel", "proposal", "aanpassen", "wijzig", "change", "adjust"]
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
        fact_tokens = ["welke", "what", "which", "staat", "is", "wat", "who", "where"]

        if any(token in normalized for token in action_tokens):
            matched_signals.append("mode:action")
            return "ACTION"
        if any(token in normalized for token in proposal_tokens):
            matched_signals.append("mode:proposal")
            return "PROPOSAL"
        if any(token in normalized for token in evaluation_tokens):
            matched_signals.append("mode:evaluation")
            return "EVALUATION"
        if scopes and any(token in normalized for token in fact_tokens):
            matched_signals.append("mode:fact")
            return "FACT"
        if scopes:
            matched_signals.append("mode:fact_inferred")
            return "FACT"
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

    def _confidence(self, *, scopes: List[str], matched_signals: List[str], interaction_mode: str) -> str:
        if interaction_mode == "UNAVAILABLE":
            return "none"
        if len(scopes) >= 2 and len(matched_signals) >= 3:
            return "high"
        if scopes:
            return "medium"
        return "low"
