"""Small semantic front door for FINN V2 operation contracts.

The classifier intentionally returns no scopes, tools or policy.  Those remain
the registry's responsibility after the selected operation has been validated.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Mapping, Optional

from backend.domain.finn_v2_operation_registry import FinnV2OperationRegistry


@dataclass(frozen=True)
class SemanticOperationClassification:
    operation_id: str
    action: str
    domain: str
    discourse: str
    confidence: str


class FinnV2OperationClassificationService:
    """Classify action/domain/polarity without duplicating registry contracts."""

    _ACTION_WORDS = {
        "confirm": ("bevestig", "confirm"),
        "execute": ("uitvoeren", "uitvoer", "voer", "execute"),
        "activate": ("activeer", "activate", "schakel", "start", "live"),
        "remove": ("verwijder", "remove", "haal", "hal", "stop"),
        "add": ("voeg", "add", "toevoeg", "zet", "volg"),
        "create": ("maak", "mak", "create", "stel", "bereid", "voorbereiden", "ontwerp", "setupconcept"),
        "update": ("wijzig", "update"),
        "evaluate": ("beoordeel", "evaluate", "zwak", "risico", "past", "fit", "wringt", "ontbreekt", "ontbrekende", "vertrouwen", "betrouwbaar", "voorwaarde", "entryvoorwaarde", "weegt"),
        "explain": ("onderbouw", "waarom", "bewijs", "baseer", "leg"),
        "reformulate": ("korter", "herformuleer", "anders", "andere", "compacter"),
        "read": ("welke", "wat", "toon", "bekijk", "staat", "heb"),
    }
    _DOMAIN_WORDS = {
        "capability": ("finn", "help", "helpen", "kan", "doen"),
        "watchlist": ("watchlist", "volglijst", "volgen"),
        "indicators": (
            "indicator", "rsi", "vwap", "volume", "ma200", "ma_200",
            "signaal", "signalen", "trendindicator",
        ),
        "setup": ("setup",),
        "strategy": ("strategie", "strategy"),
        "bot": ("bot", "automation", "automatisering"),
        "plan": ("plan", "profiel", "profile"),
        "reports": ("rapport", "report"),
        "reviews": ("reflectie", "reflection", "review"),
        "portfolio": ("portfolio", "portefeuille"),
        "asset": (
            "asset", "instrument", "bitcoin", "btc", "aapl", "coin",
            "aandeel", "workspace", "markt", "market",
        ),
        # These are recognised domains with no executable V2 contract.  They
        # must reach the registry's safe unavailable contract, not a legacy
        # request-analysis fallback.
        "trade": ("trade", "entry", "positie", "position"),
        "non_financial": ("weer", "weather", "amsterdam"),
    }

    def __init__(self, registry: Optional[FinnV2OperationRegistry] = None):
        self.registry = registry or FinnV2OperationRegistry()

    def classify(self, *, message: str, conversation_context: Optional[Mapping[str, object]] = None) -> SemanticOperationClassification:
        # Hyphenated asset-plan phrasing (for example ``BTC-plan``) carries
        # both an asset selector and a plan domain.  Keep those concepts
        # separate instead of letting the asset token erase the user goal.
        normalized_message = re.sub(r"\bset[-\s]+up\b", "setup", str(message or "").casefold())
        words = set(re.findall(r"\w+", normalized_message))
        action = self._action(words)
        domain = self._domain(words)
        if domain == "unknown" and action == "unknown":
            # Contract aliases may enrich semantic recognition but never
            # contribute scopes, tools or policy.  The resolved contract is
            # still validated below before a new run can plan work.
            alias_contract = self.registry.resolve_alias(normalized_message)
            if alias_contract is not None:
                domain = alias_contract.domain
        discourse = self._discourse(words, conversation_context or {})
        operation = self._operation(action=action, domain=domain, discourse=discourse, words=words)
        confidence = "high" if action != "unknown" and domain != "unknown" else "medium" if domain != "unknown" else "low"
        return SemanticOperationClassification(operation, action, domain, discourse, confidence)

    def _action(self, words: set[str]) -> str:
        # State questions ("staat hij live?", "is de bot live?") read a
        # configuration; only an imperative live request is an activation.
        if "live" in words and words.intersection({"staat", "is", "welke", "toon"}):
            return "read"
        for action in ("confirm", "execute", "remove", "activate", "add", "create", "update", "evaluate", "explain", "reformulate", "read"):
            candidates = self._ACTION_WORDS[action]
            # Confirmation is a workflow command, not a description of a
            # condition that should be confirmed before an entry.
            if action == "confirm":
                if words.intersection(candidates):
                    return action
                continue
            # "Voer niets uit" and comparable negated imperatives describe a
            # safety constraint for a proposal, not an execution request.
            if action == "execute" and words.intersection({"niet", "niets", "geen", "zonder"}):
                continue
            if any(
                word == token or (token != "volg" and word.startswith(token))
                for word in words
                for token in candidates
            ):
                return action
        return "unknown"

    def _domain(self, words: set[str]) -> str:
        matches = [
            domain for domain, vocabulary in self._DOMAIN_WORDS.items()
            if any(word == token or word.startswith(token) for word in words for token in vocabulary)
        ]
        # “Help me een BTC-setup ...” is a setup operation, not a generic
        # capability request merely because it contains the word “help”.
        if "capability" in matches and len(matches) > 1:
            matches.remove("capability")
        if "plan" in matches:
            return "plan"
        if {"setup", "strategy", "bot"}.issubset(matches):
            return "plan"
        # A graph request must keep every persisted relationship available.  A
        # bot mention therefore wins over an otherwise narrower strategy/setup
        # mention; the bot contract reads the full setup -> strategy -> bot graph.
        for domain in (
            "bot", "strategy", "setup", "watchlist", "indicators", "portfolio",
            "reports", "reviews",
        ):
            if domain in matches:
                return domain
        return matches[0] if matches else "unknown"

    @staticmethod
    def _discourse(words: set[str], context: Mapping[str, object]) -> str:
        active = context.get("active_guided_operation") or context.get("operation_state")
        if isinstance(active, dict) and active.get("missing_required_inputs"):
            return "clarification_answer"
        verified = context.get("last_verified_context") or context.get("last_verified_conclusion")
        if verified and words.intersection({"onderbouw", "bewijs", "waarom", "baseer", "leg", "evidence", "bron", "bronnen"}):
            return "evidence_follow_up"
        if verified and words.intersection({"korter", "herformuleer", "anders", "andere", "compacter"}):
            return "reformulation"
        if verified and words.intersection({"die", "dat", "eerder"}):
            return "contextual_follow_up"
        return "new_request"

    @staticmethod
    def _operation(*, action: str, domain: str, discourse: str, words: set[str]) -> str:
        if discourse == "evidence_follow_up":
            return "explain_previous_evidence"
        if discourse == "reformulation":
            return "reformulate_previous_response"
        if action == "confirm":
            return "confirm_proposal"
        if action == "execute":
            return "execute_proposal"
        if domain in {"trade", "non_financial"}:
            return "unavailable"
        if domain == "watchlist":
            return "watchlist_remove" if action == "remove" else "watchlist_add" if action in {"add", "create"} else "read_watchlist"
        if domain == "reports":
            return "read_latest_report"
        if domain == "reviews":
            return "evaluate_review_history" if action == "evaluate" else "read_review_history"
        if domain == "portfolio":
            return "evaluate_portfolio" if action == "evaluate" else "read_portfolio"
        if action == "create" and domain in {"setup", "plan"}:
            return "create_setup"
        if action == "add" and domain == "setup":
            return "create_setup"
        if domain == "bot" and action == "activate":
            return "activate_paper_bot" if "paper" in words else "activate_bot"
        if action == "evaluate":
            if domain in {"plan", "unknown"}:
                return "evaluate_plan"
            if domain == "indicators":
                return "evaluate_indicator_configuration"
            return f"evaluate_{domain}"
        if domain == "capability" and action in {"read", "unknown"}:
            return "capability"
        if domain == "asset":
            return "read_active_asset"
        if domain == "indicators":
            return "read_indicator_configuration"
        if domain == "setup":
            return "read_active_setup"
        if domain == "strategy":
            return "read_linked_strategy"
        if domain == "bot":
            return "read_linked_bot"
        if domain == "plan":
            return "read_active_plan"
        return "clarify_request"


class FinnV2OperationClassificationValidator:
    """Reject semantic/action mismatches before a contract enters planning."""

    _ACTIONS_BY_OPERATION = {
        "watchlist_add": {"add", "create"}, "watchlist_remove": {"remove"}, "create_setup": {"create", "add"},
        "activate_bot": {"activate"}, "confirm_proposal": {"confirm"}, "execute_proposal": {"execute"},
        "evaluate_plan": {"evaluate"}, "explain_previous_evidence": {"explain"},
        "reformulate_previous_response": {"reformulate"},
    }

    def validate(self, classification: SemanticOperationClassification) -> bool:
        expected = self._ACTIONS_BY_OPERATION.get(classification.operation_id)
        return expected is None or classification.action in expected | {"unknown"}
