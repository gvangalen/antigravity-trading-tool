"""Typed guided-operation state backed by the canonical conversation JSON."""
from __future__ import annotations

import json
import re
from typing import Mapping, Optional

from backend.domain.finn_v2_operation_registry import OperationContract
from backend.domain.finn_v2_setup_input_catalog import FinnV2SetupInputCatalog
from backend.schemas.finn_v2_orchestrator_schema import FinnV2OperationState


class FinnV2OperationStateService:
    """Collect only explicit or verified operation inputs, one field at a time."""

    CONTEXT_STATE_VERSION = "finn_v2.conversation-contracts.v1"

    def resolve(
        self,
        *,
        contract: OperationContract,
        message: str,
        explicit_asset: Optional[str],
        conversation_context: Optional[Mapping[str, object]],
        supplied_inputs: Optional[Mapping[str, object]] = None,
        derived_inputs: Optional[Mapping[str, object]] = None,
    ) -> FinnV2OperationState:
        existing = self._existing_state(contract, conversation_context or {})
        collected = self._canonicalize_inputs(dict(existing.collected_inputs)) if existing is not None else {}
        # Only values proven by request parsing may be promoted to supplied
        # inputs. Typed selector values are passed separately so a later
        # projection cannot silently overwrite a user-supplied slot.
        explicit = self.explicit_inputs(contract=contract, message=message, explicit_asset=explicit_asset)
        # Keep the literal spelling of a user-provided value. The semantic
        # projection may normalize an equivalent value for matching, but it
        # must not overwrite a typed setup name with that normalized form.
        accepted_inputs = set(contract.required_inputs).union(contract.optional_inputs)
        for key, value in (supplied_inputs or {}).items():
            if key in accepted_inputs and not self._is_missing(value):
                explicit.setdefault(key, self._canonical_input(key, value))
        collected.update(explicit)
        for key, value in (derived_inputs or {}).items():
            if key in accepted_inputs and key not in collected and not self._is_missing(value):
                collected[key] = self._canonical_input(key, value)
        missing = [field for field in contract.required_inputs if self._is_missing(collected.get(field))]
        context = conversation_context or {}
        verified_context = dict(context.get("last_verified_context") or {})
        resolved_context = dict(verified_context.get("resolved_entities") or {})
        is_canonical_context = context.get("conversation_state_version") == self.CONTEXT_STATE_VERSION
        resolved_entities = dict(existing.resolved_entities) if existing is not None else {}
        target_entities = dict(existing.target_entities) if existing is not None else {}
        resolved_entities.update(
            {
                key: value
                for key, value in {
                    "asset": explicit_asset or resolved_context.get("asset") or (None if is_canonical_context else context.get("resolved_asset")),
                    "setup_id": resolved_context.get("setup_id") or (None if is_canonical_context else context.get("resolved_setup_id")),
                    "strategy_id": resolved_context.get("strategy_id") or (None if is_canonical_context else context.get("resolved_strategy_id")),
                    "bot_id": resolved_context.get("bot_id") or (None if is_canonical_context else context.get("resolved_bot_id")),
                }.items()
                if value is not None
            }
        )
        if contract.operation_id in {"watchlist_add", "watchlist_remove"}:
            target_asset = collected.get("asset")
            if target_asset:
                target_entities["asset"] = target_asset
        return FinnV2OperationState(
            operation_id=contract.operation_id,
            contract_version=contract.version,
            state_revision=(existing.state_revision + 1) if existing is not None else 1,
            collected_inputs=collected,
            resolved_entities=resolved_entities,
            target_entities=target_entities,
            missing_required_inputs=missing,
            next_missing_input=missing[0] if missing else None,
            open_proposal_id=context.get("open_proposal_id"),
            previous_verified_response_id=(
                verified_context.get("verified_response_id")
                or (None if is_canonical_context else context.get("last_verified_response_id"))
            ),
            previous_verified_conclusion=(
                verified_context.get("conclusion")
                or (None if is_canonical_context else context.get("last_verified_conclusion"))
            ),
            previous_evidence_refs=list(
                verified_context.get("evidence_refs")
                or ([] if is_canonical_context else context.get("last_evidence_refs"))
                or []
            ),
        )

    @staticmethod
    def pending_operation_id(context: Mapping[str, object]) -> Optional[str]:
        # The typed state supersedes the legacy compatibility field for every
        # newly created conversation.  Historical contexts still fall back to
        # ``operation_state`` until they are naturally rewritten.
        raw = FinnV2OperationStateService._guided_state_payload(context)
        if not isinstance(raw, dict) or context.get("open_proposal_id"):
            return None
        try:
            state = FinnV2OperationState.parse_obj(raw)
        except (TypeError, ValueError):
            return None
        return state.operation_id if state.missing_required_inputs else None

    @staticmethod
    def clarification_question(
        field: Optional[str], *, contract: Optional[OperationContract] = None, collected_inputs: Optional[Mapping[str, object]] = None
    ) -> str:
        collected = collected_inputs or {}
        questions = {
            "name": (
                f"Welke naam wil je deze {str(collected.get('symbol') or '').upper()}-setup geven?"
                if contract is not None and contract.operation_id == "create_setup" and collected.get("symbol")
                else "Welke korte naam wil je voor deze setup gebruiken?"
            ),
            "symbol": "Voor welke asset wil je deze setup precies voorbereiden?",
            "setup_type": "Wil je een trade- of DCA-setup voorbereiden?",
            "timeframe": "Welk primair timeframe wil je voor deze setup gebruiken?",
            "setup_id": "Welke bestaande setup wil je aanpassen?",
            "changed_fields": "Welke concrete setupvelden wil je aanpassen?",
            "strategy_id": "Welke bestaande strategie wil je aanpassen?",
            "execution_mode": "Wil je een fixed of custom uitvoeringsmodus gebruiken?",
            "base_amount": "Welke basisinleg wil je voor deze strategie gebruiken?",
            "proposal_id": "Welk voorstel wil je precies bevestigen of uitvoeren?",
            "asset": "Welke asset wil je aan je watchlist toevoegen?",
            "requested_change": "Wat wil je precies aan je manier van handelen verbeteren?",
        }
        return questions.get(field or "", "Welk ontbrekend detail wil je voor dit voorstel vastleggen?")

    def cancel(
        self,
        *,
        operation_id: str,
        conversation_context: Optional[Mapping[str, object]],
    ) -> Optional[FinnV2OperationState]:
        """Return a terminal typed state without executing or deleting data."""
        try:
            contract = self._registry_contract(operation_id)
        except ValueError:
            return None
        existing = self._existing_state(contract, conversation_context or {})
        if existing is None:
            return None
        return existing.copy(
            update={
                "missing_required_inputs": [],
                "next_missing_input": None,
                "open_proposal_id": None,
                "status": "cancelled",
            }
        )

    @staticmethod
    def is_cancel_intent(message: str) -> bool:
        words = set(re.findall(r"\w+", str(message or "").casefold()))
        return bool(words.intersection({"annuleer", "annuleren", "cancel", "stop", "stoppen"}))

    @staticmethod
    def _registry_contract(operation_id: str) -> OperationContract:
        from backend.domain.finn_v2_operation_registry import FinnV2OperationRegistry

        return FinnV2OperationRegistry().require_supported(operation_id)

    def _existing_state(self, contract: OperationContract, context: Mapping[str, object]) -> Optional[FinnV2OperationState]:
        raw = self._guided_state_payload(context)
        if not isinstance(raw, dict):
            return None
        try:
            state = FinnV2OperationState.parse_obj(raw)
        except (TypeError, ValueError):
            return None
        if state.operation_id != contract.operation_id or state.contract_version != contract.version:
            return None
        return state

    @classmethod
    def _guided_state_payload(cls, context: Mapping[str, object]) -> object:
        """Read the legacy field only from planless historical conversations."""
        if context.get("conversation_state_version") == cls.CONTEXT_STATE_VERSION:
            return context.get("active_guided_operation")
        return context.get("active_guided_operation") or context.get("operation_state")

    def explicit_inputs(self, *, contract: OperationContract, message: str, explicit_asset: Optional[str]) -> dict[str, object]:
        text = str(message or "").strip()
        lowered = text.casefold()
        values: dict[str, object] = {}
        accepted_inputs = set(contract.required_inputs).union(contract.optional_inputs)
        if explicit_asset:
            for field in {"asset", "symbol"}.intersection(accepted_inputs):
                values[field] = explicit_asset
        # A structured selector or a caller may provide a compact typed object
        # in a follow-up. Promote only fields already declared by this contract;
        # no operation-specific field list is maintained here.
        structured = self._structured_changed_fields(text)
        for field in accepted_inputs:
            if field in structured and not self._is_missing(structured[field]):
                values[field] = self._canonical_input(field, structured[field])
        for field in contract.required_inputs:
            if not field.endswith("_id") or field in values:
                continue
            label = re.escape(field[:-3]).replace("_", r"\s*")
            identifier = re.search(rf"\b{label}(?:\s*(?:id|nummer|number))?\s*#?\s*(\d+)\b", text, re.IGNORECASE)
            if identifier:
                values[field] = int(identifier.group(1))
        if contract.operation_id == "create_setup":
            if "dca" in lowered:
                values["setup_type"] = "dca"
            else:
                setup_type = FinnV2SetupInputCatalog.setup_type_from_text(text)
                if setup_type:
                    values["setup_type"] = setup_type
            # Keep multi-word locale introducers ahead of their shorter
            # components. Word boundaries prevent ``name`` matching inside
            # German ``namens`` or an unrelated user-supplied word.
            named = re.search(
                r"\b(?:mit\s+dem\s+namen|unter\s+dem\s+namen|met\s+de\s+naam|namens|genannt|"
                r"genaamd|named|called|call\s+it|nenne\s+(?:ihn|sie|es)|"
                r"noem\s+(?:hem|haar|het|deze|dit)|ik\s+noem\s+(?:hem|haar|het|deze|dit)|"
                r"hij\s+heet|het\s+heet|naam|name|titel|title)\b"
                r"\s*(?:is|:|=)?\s*[\"']?([\w .-]{2,80})",
                text,
                re.IGNORECASE,
            )
            if named:
                name = FinnV2SetupInputCatalog.display_name(
                    self._trim_setup_name_clause(named.group(1).strip(" ."))
                )
                if name:
                    values["name"] = name
            timeframe = FinnV2SetupInputCatalog.timeframe_from_text(text)
            if timeframe:
                values["timeframe"] = timeframe
            if any(token in lowered for token in ("daily trend", "dagtrend", "uptrend", "downtrend")):
                values["market_condition"] = "trend_defined"
        elif contract.operation_id in {"watchlist_add", "watchlist_remove"} and explicit_asset:
            values["asset"] = explicit_asset
        elif contract.operation_id == "create_strategy":
            setup_match = re.search(r"\bsetup(?:\s*(?:id|nummer|number))?\s*#?\s*(\d+)\b", text, re.IGNORECASE)
            if setup_match:
                values["setup_id"] = int(setup_match.group(1))
            mode_match = re.search(r"\b(fixed|custom)\b", lowered)
            if mode_match:
                values["execution_mode"] = mode_match.group(1)
            amount_match = re.search(
                r"\b(?:base\s*amount|bedrag|inleg|amount)\s*(?:is|:|=)?\s*(?:€|eur|\$)?\s*(\d+(?:[.,]\d+)?)",
                lowered,
            )
            if amount_match:
                values["base_amount"] = float(amount_match.group(1).replace(",", "."))
            named = re.search(r"\b(?:naam|name|named|called)\s*(?:is|:|=)?\s*[\"']?([\w .-]{2,80})", text, re.IGNORECASE)
            if named:
                values["name"] = named.group(1).strip(" .\"'")
        elif contract.operation_id in {"update_setup", "update_strategy"}:
            entity = "setup" if contract.operation_id == "update_setup" else "strategy"
            identifier = re.search(
                rf"\b{entity}(?:\s*(?:id|nummer|number))?\s*#?\s*(\d+)\b",
                text,
                re.IGNORECASE,
            )
            if identifier:
                values[f"{entity}_id"] = int(identifier.group(1))
            changes = self._structured_changed_fields(text)
            if changes:
                values["changed_fields"] = changes
        return values

    @staticmethod
    def _structured_changed_fields(text: str) -> dict[str, object]:
        """Collect an explicit typed update object without inventing fields.

        The action contract exposes one ``changed_fields`` slot. Its accepted
        field names and value validation stay with SetupService or
        StrategyService; this collector merely accepts a user-provided JSON
        object for that typed slot and never turns ordinary prose into a write
        payload.
        """
        start = text.find("{")
        end = text.rfind("}")
        if start < 0 or end <= start:
            return {}
        try:
            raw = json.loads(text[start : end + 1])
        except (TypeError, ValueError):
            return {}
        if not isinstance(raw, dict) or not raw:
            return {}
        if not all(isinstance(key, str) and key.strip() for key in raw):
            return {}
        return dict(raw)

    @staticmethod
    def _trim_setup_name_clause(value: str) -> str:
        """Exclude trailing non-persistence instructions from a display name."""
        return re.split(
            r"\s+(?:(?:en|and|aber|but)\s+)?(?:sla\s+(?:niets|het)?\s*op|"
            r"(?:en|and|und)\s+(?:het\s+|the\s+|dem\s+)?(?:timeframe|tijdframe|time\s*frame)\b.*|"
            r"(?:do\s+not|don't)\s+(?:save|write|persist)(?:\s+(?:it|the\s+setup|anything))?(?:\s+yet)?|"
            r"save\s+(?:nothing|it)|without\s+(?:saving|writing|persisting)\s+(?:it|anything)(?:\s+yet)?|"
            r"speicher\s+(?:nichts|es))\b",
            value,
            maxsplit=1,
            flags=re.IGNORECASE,
        )[0].strip(" .")

    @staticmethod
    def _is_missing(value: object) -> bool:
        return value is None or (isinstance(value, str) and not value.strip())

    @staticmethod
    def _canonical_input(field: str, value: object) -> object:
        return FinnV2SetupInputCatalog.canonical_input(field, value)

    def _canonicalize_inputs(self, values: Mapping[str, object]) -> dict[str, object]:
        return {key: self._canonical_input(key, value) for key, value in values.items()}
