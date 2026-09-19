"""Typed guided-operation state backed by the canonical conversation JSON."""
from __future__ import annotations

import json
import re
from typing import Mapping, Optional

from backend.domain.finn_v2_operation_registry import OperationContract
from backend.domain.finn_v2_setup_input_catalog import FinnV2SetupInputCatalog
from backend.domain.technical_indicator_catalog import get_active_technical_indicator_definitions
from backend.domain.macro_indicator_catalog import get_active_macro_indicator_definitions
from backend.domain.market_indicator_catalog import get_active_market_indicator_definitions
from backend.schemas.finn_v2_orchestrator_schema import FinnV2OperationState


class FinnV2OperationStateService:
    """Collect only explicit or verified operation inputs, one field at a time."""

    CONTEXT_STATE_VERSION = "finn_v2.conversation-contracts.v1"

    @staticmethod
    def _typed_numeric_value(value: object) -> object:
        """Parse user-facing NL/EN/DE numbers without losing thousands."""
        if not isinstance(value, str):
            return value
        raw_value = value.strip().casefold().rstrip(".,")
        word_numbers = {
            "honderd": 100, "duizend": 1000,
            "hundred": 100, "thousand": 1000,
            "hundert": 100, "tausend": 1000,
            "one hundred": 100, "one thousand": 1000,
            "een honderd": 100, "een duizend": 1000,
            "einhundert": 100, "eintausend": 1000,
        }
        currency_free = re.sub(r"\s*(?:€|eur|euro|euros)\s*$", "", raw_value).strip()
        if currency_free in word_numbers:
            return word_numbers[currency_free]
        normalized = re.sub(r"\s+", "", currency_free)
        if not re.fullmatch(r"\d+(?:[.,]\d+)*", normalized):
            return value
        if "." in normalized and "," in normalized:
            decimal_separator = "." if normalized.rfind(".") > normalized.rfind(",") else ","
            thousands_separator = "," if decimal_separator == "." else "."
            normalized = normalized.replace(thousands_separator, "").replace(decimal_separator, ".")
        elif re.fullmatch(r"\d{1,3}(?:[.,]\d{3})+", normalized):
            normalized = normalized.replace(".", "").replace(",", "")
        else:
            normalized = normalized.replace(",", ".")
        number = float(normalized)
        return int(number) if number.is_integer() else number

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
        requested_slot = (
            existing.next_missing_input
            or next(iter(existing.missing_required_inputs or ()), None)
            if existing is not None
            else None
        )
        # A clarification reply belongs to the requested contract slot. Words
        # inside a setup name (for example "Sol") must not be reinterpreted as
        # a fresh asset and overwrite the persisted target.
        contract_asset = (
            explicit_asset
            if existing is None or requested_slot in {"asset", "symbol"}
            else None
        )
        # Only values proven by request parsing may be promoted to supplied
        # inputs. Typed selector values are passed separately so a later
        # projection cannot silently overwrite a user-supplied slot.
        is_slot_turn = existing is not None and bool(requested_slot)
        is_correction = is_slot_turn and self._is_explicit_correction(message)
        if is_slot_turn and is_correction:
            explicit = self._explicit_correction_inputs(
                contract=contract, message=message, accepted_inputs=set(contract.input_fields)
            )
        elif is_slot_turn:
            slot_value = (
                contract_asset
                if requested_slot in {"asset", "symbol"} and contract_asset
                else self._requested_slot_value(
                    field=str(requested_slot), text=message, contract=contract
                )
            )
            explicit = {str(requested_slot): slot_value} if slot_value is not None else {}
            # A guided reply can explicitly answer more than the requested
            # slot (for example "Trade setup, naam Momentum"). Keep the
            # active contract authoritative and accept only its still-missing
            # fields; already collected values remain immutable here.
            labelled = self.explicit_inputs(
                contract=contract,
                message=message,
                explicit_asset=contract_asset,
            )
            missing_fields = set(existing.missing_required_inputs)
            for key, value in labelled.items():
                if key in missing_fields and not self._is_missing(value):
                    explicit.setdefault(key, value)
        else:
            explicit = self.explicit_inputs(
                contract=contract,
                message=message,
                explicit_asset=contract_asset,
                continuation=existing is not None,
                requested_slot=requested_slot,
            )
        # Keep the literal spelling of a user-provided value. The semantic
        # projection may normalize an equivalent value for matching, but it
        # must not overwrite a typed setup name with that normalized form.
        accepted_inputs = set(contract.input_fields)
        permits_existing_field_changes = self._is_explicit_correction(message)
        for key, value in (supplied_inputs or {}).items():
            if is_slot_turn:
                continue
            if (
                existing is not None
                and requested_slot not in {"asset", "symbol"}
                and key in {"asset", "symbol"}
            ):
                continue
            if (
                existing is not None
                and key in collected
                and key != requested_slot
                and not permits_existing_field_changes
            ):
                # The model output is a candidate extraction. During a typed
                # guided turn it cannot reinterpret a number for the pending
                # slot as a replacement for an already persisted field.
                continue
            if key in accepted_inputs and not self._is_missing(value):
                explicit.setdefault(key, self._canonical_input(key, value))
        if contract.operation_id == "create_bot" and explicit.get("name"):
            explicit["name"] = self._trim_linked_strategy_clause(str(explicit["name"]))
        sources = dict(existing.input_sources) if existing is not None else {}
        provenance = dict(existing.input_provenance) if existing is not None else {}
        collected.update(explicit)
        sources.update({key: "explicit" for key in explicit})
        next_revision = (existing.state_revision + 1) if existing is not None else 1
        provenance.update({
            key: {"source": "explicit", "state_revision": next_revision}
            for key in explicit
        })
        for key, value in (derived_inputs or {}).items():
            if key in accepted_inputs and key not in collected and not self._is_missing(value):
                collected[key] = self._canonical_input(key, value)
                sources[key] = "default"
                provenance[key] = {"source": "default", "state_revision": next_revision}
        context = conversation_context or {}
        verified_context = dict(context.get("last_verified_context") or {})
        resolved_context = dict(verified_context.get("resolved_entities") or {})
        operation_entity_type = next(
            (
                entity
                for entity in ("setup", "strategy", "bot")
                if contract.operation_id.endswith(entity)
            ),
            "",
        )
        recent_action_results = dict(context.get("recent_action_results") or {})
        action_result = dict(
            recent_action_results.get(operation_entity_type)
            or context.get("previous_action_result")
            or {}
        )
        action_entity_type = str(action_result.get("entity_type") or "")
        action_entity_id = action_result.get("entity_id")
        if action_entity_type == "setup" and action_entity_id is not None:
            resolved_context.setdefault("setup_id", action_entity_id)
        elif action_entity_type == "strategy" and action_entity_id is not None:
            resolved_context.setdefault("strategy_id", action_entity_id)
        elif action_entity_type == "bot" and action_entity_id is not None:
            resolved_context.setdefault("bot_id", action_entity_id)
        parent_entity_type = str(action_result.get("parent_entity_type") or "")
        parent_entity_id = action_result.get("parent_entity_id")
        if parent_entity_type == "setup" and parent_entity_id is not None:
            resolved_context.setdefault("setup_id", parent_entity_id)
        elif parent_entity_type == "strategy" and parent_entity_id is not None:
            resolved_context.setdefault("strategy_id", parent_entity_id)
        # Result lineage may only fill a slot exposed by this action contract.
        # This keeps required-input semantics registry-owned while allowing a
        # new natural-language turn to continue the immediately prior action.
        for field in ("setup_id", "strategy_id", "bot_id"):
            if field in accepted_inputs and not self._is_missing(resolved_context.get(field)):
                collected.setdefault(field, resolved_context[field])
                sources.setdefault(field, "context")
        missing = [
            field
            for field in contract.required_inputs_for(collected)
            if self._is_missing(collected.get(field))
        ]
        is_canonical_context = context.get("conversation_state_version") == self.CONTEXT_STATE_VERSION
        resolved_entities = dict(existing.resolved_entities) if existing is not None else {}
        target_entities = dict(existing.target_entities) if existing is not None else {}
        resolved_entities.update(
            {
                key: value
                for key, value in {
                    "asset": contract_asset or resolved_context.get("asset") or (None if is_canonical_context else context.get("resolved_asset")),
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
            state_revision=next_revision,
            collected_inputs=collected,
            input_sources=sources,
            input_provenance=provenance,
            resolved_entities=resolved_entities,
            target_entities=target_entities,
            missing_required_inputs=missing,
            next_missing_input=missing[0] if missing else None,
            status="collecting" if missing else "complete",
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
        operation_id = contract.operation_id if contract is not None else None
        if field == "changed_fields":
            return {
                "update_setup": "Wat wil je aan deze setup wijzigen?",
                "update_strategy": "Wat wil je aan deze strategie wijzigen?",
                "update_bot": "Wat wil je aan deze paper-bot wijzigen?",
            }.get(operation_id, "Wat wil je precies wijzigen?")
        if field == "name":
            if operation_id == "create_bot":
                return "Welke korte naam wil je voor deze paper-bot gebruiken?"
            if operation_id == "create_strategy":
                return "Welke korte naam wil je voor deze strategie gebruiken?"
        questions = {
            "name": (
                f"Welke naam wil je deze {str(collected.get('symbol') or '').upper()}-setup geven?"
                if operation_id == "create_setup" and collected.get("symbol")
                else "Welke korte naam wil je voor deze setup gebruiken?"
            ),
            "symbol": "Voor welke asset wil je deze setup precies voorbereiden?",
            "setup_type": "Wil je een trade- of DCA-setup voorbereiden?",
            "timeframe": "Welk primair timeframe wil je voor deze setup gebruiken?",
            "dca_frequency": "Hoe vaak wil je volgens deze DCA-setup aankopen: dagelijks, wekelijks of maandelijks?",
            "dca_day": "Op welke weekdag wil je volgens deze DCA-setup aankopen?",
            "dca_month_day": "Op welke dag van de maand wil je volgens deze DCA-setup aankopen?",
            "setup_id": "Welke bestaande setup wil je aanpassen?",
            "strategy_id": "Welke bestaande strategie wil je aanpassen?",
            "execution_mode": "Wil je een fixed of custom uitvoeringsmodus gebruiken?",
            "base_amount": "Welk bedrag wil je per uitvoering inzetten?",
            "entry": "Bij welke koers wil je instappen?",
            "stop_loss": "Waar wil je je stop-loss zetten?",
            "targets": "Welke koersdoelen wil je gebruiken?",
            "risk_profile": "Welke risicostijl wil je gebruiken: voorzichtig, gebalanceerd of offensief?",
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
        text = str(message or "").strip().casefold()
        if re.search(r"\bstop[- ]?loss\b", text):
            return False
        return bool(re.fullmatch(
            r"(?:annuleer|annuleren|cancel)(?:\s+(?:dit|deze|het|the|voorstel|proposal))*[.!?]?|"
            r"(?:stop|stoppen)(?:\s+(?:met\s+)?(?:dit|deze|hiermee|strategie|strategy|flow|maar|please|aub))*[.!?]?",
            text,
        ))

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
        # A completed/proposed action is historical context, not an active
        # guided draft. Reusing it made a fresh RSI request inherit an older
        # DXY proposal because both share the indicator operation contract.
        if not state.missing_required_inputs or state.status != "collecting":
            return None
        return state

    @classmethod
    def _guided_state_payload(cls, context: Mapping[str, object]) -> object:
        """Read the legacy field only from planless historical conversations."""
        if context.get("conversation_state_version") == cls.CONTEXT_STATE_VERSION:
            return context.get("active_guided_operation")
        return context.get("active_guided_operation") or context.get("operation_state")

    def explicit_inputs(
        self,
        *,
        contract: OperationContract,
        message: str,
        explicit_asset: Optional[str],
        continuation: bool = False,
        requested_slot: Optional[str] = None,
    ) -> dict[str, object]:
        text = str(message or "").strip()
        lowered = text.casefold()
        values: dict[str, object] = {}
        accepted_inputs = set(contract.input_fields)
        # A short reply belongs to the one persisted requested slot. A setup
        # name has no keyword and must not be reclassified as a fresh request.
        if continuation and requested_slot in accepted_inputs and text:
            slot_value = self._requested_slot_value(
                field=str(requested_slot), text=text, contract=contract
            )
            if slot_value is not None:
                values[str(requested_slot)] = slot_value
                if self._is_short_slot_answer(text, requested_slot=str(requested_slot)):
                    return values
        if explicit_asset:
            for field in {"asset", "symbol"}.intersection(accepted_inputs):
                values[field] = explicit_asset
        # Clarification owns a single free-text slot. Only a reply to an
        # existing clarification flow may fill it; the initial vague request
        # must remain eligible for the focused question.
        if continuation and "requested_change" in accepted_inputs and text:
            values["requested_change"] = text
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
            identifier = re.search(
                rf"\b{label}(?:\s*(?:id|nummer|number)\s*#?|\s*#)\s*((?!0\d)\d+)\b",
                text,
                re.IGNORECASE,
            )
            if identifier is None:
                identifier = re.fullmatch(
                    rf"(?:deactiveer|deactivate|deaktiviere|verwijder|delete|loesche|lösche|wijzig|update|"
                    rf"change|aktualisiere)\s+(?:de|het|the|den|die|das)?\s*{label}\s+((?!0\d)\d+)[.!?]?",
                    text.strip(),
                    re.IGNORECASE,
                )
            if identifier:
                values[field] = int(identifier.group(1))
        if {"indicator", "category"}.intersection(accepted_inputs):
            indicator = self._indicator_input_from_text(text)
            if indicator is not None:
                if "indicator" in accepted_inputs:
                    values.setdefault("indicator", indicator["name"])
                if "category" in accepted_inputs:
                    values.setdefault("category", indicator["category"])
        if "name" in accepted_inputs:
            named = self._name_input_from_text(text)
            if named:
                values.setdefault("name", named)
        if contract.operation_id == "explain_financial_concept" and "concept" in accepted_inputs:
            concepts = {
                "dollar cost averaging": "dollar cost averaging", "dca": "DCA",
                "relative strength index": "RSI", "rsi": "RSI", "macd": "MACD", "atr": "ATR",
            }
            normalized_concepts = lowered.replace("-", " ")
            for term, concept in concepts.items():
                if term in normalized_concepts:
                    values.setdefault("concept", concept)
                    break
        if "changed_fields" in accepted_inputs:
            changes = self._natural_changed_fields(text, contract=contract)
            if contract.operation_id == "update_indicator_configuration" and re.search(
                r"\b(?:deactivate|disable|turn\s+off|deaktiviere|deaktivier|ausschalt)\w*\b",
                lowered,
            ):
                changes = {"enabled": False}
            if changes:
                values.setdefault("changed_fields", changes)
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
            if values.get("name"):
                values["name"] = FinnV2SetupInputCatalog.display_name(
                    self._trim_setup_name_clause(str(values["name"]))
                )
            timeframe = FinnV2SetupInputCatalog.timeframe_from_text(text)
            if timeframe:
                values["timeframe"] = timeframe
            # The registry exposes this conditional slot for create_setup, but
            # cadence words are inputs only after the user selected a DCA
            # setup. A market's daily trend must not become a DCA schedule.
            if values.get("setup_type") == "dca" and "dca_frequency" in accepted_inputs:
                frequency = next(
                    (
                        canonical
                        for token, canonical in (
                            ("daily", "daily"), ("dagelijks", "daily"), ("dagelijkse", "daily"),
                            ("taeglich", "daily"), ("taegliche", "daily"), ("taegliches", "daily"),
                            ("weekly", "weekly"), ("wekelijks", "weekly"), ("wekelijkse", "weekly"),
                            ("monthly", "monthly"), ("maandelijks", "monthly"),
                        )
                        if re.search(rf"\b{token}\b", lowered)
                    ),
                    None,
                )
                if frequency:
                    values["dca_frequency"] = frequency
                weekday_match = re.search(
                    r"\b(monday|maandag|montag|tuesday|dinsdag|dienstag|wednesday|woensdag|mittwoch|"
                    r"thursday|donderdag|donnerstag|friday|vrijdag|freitag|saturday|zaterdag|samstag|"
                    r"sunday|zondag|sonntag)\b",
                    lowered,
                )
                if weekday_match and "dca_day" in accepted_inputs:
                    values["dca_day"] = self._requested_slot_value(
                        field="dca_day", text=weekday_match.group(1), contract=contract
                    )
                month_day_match = re.search(
                    r"\b(?:day|dag|tag)\s+(?:of\s+the\s+month|van\s+de\s+maand|des\s+monats)?\s*(\d{1,2})\b",
                    lowered,
                )
                if month_day_match and "dca_month_day" in accepted_inputs:
                    values["dca_month_day"] = self._requested_slot_value(
                        field="dca_month_day", text=month_day_match.group(1), contract=contract
                    )
            if any(token in lowered for token in ("daily trend", "dagtrend", "uptrend", "downtrend")):
                values["market_condition"] = "trend_defined"
        elif contract.operation_id in {"watchlist_add", "watchlist_remove"} and explicit_asset:
            values["asset"] = explicit_asset
        elif contract.operation_id == "create_strategy":
            mode_match = re.search(
                r"\b(fixed|vast(?:e)?|standaard|manual|handmatig|automatic|automatis\w*|fest(?:e)?|"
                r"custom|aangepast|individuell|benutzerdefiniert)\b",
                lowered,
            )
            if mode_match:
                mode = mode_match.group(1)
                values["execution_mode"] = {
                    "vast": "fixed", "vaste": "fixed", "standaard": "fixed", "manual": "fixed",
                    "handmatig": "fixed", "automatic": "fixed",
                    "fest": "fixed", "feste": "fixed",
                    "aangepast": "custom", "individuell": "custom",
                    "benutzerdefiniert": "custom",
                }.get(mode, mode)
            amount_match = re.search(
                r"(?:\b(?:base\s*amount|basisinleg|basis\s*bedrag|basisbetrag|grundbetrag|bedrag|inleg|amount)\s*(?:is|:|=|van|von|of)?\s*(?:€|eur|euros?|euro|\$)?\s*(\d+(?:[.,]\d+)?))|(?:\b(\d+(?:[.,]\d+)?)\s*(?:€|eur|euros?|euro|\$)\b)",
                lowered,
            )
            if amount_match is None:
                amount_match = re.search(
                    r"\b(?:fixed|vast|standaard|manual|handmatig|fest(?:e)?|custom|aangepast|"
                    r"individuell|benutzerdefiniert)\s*(?:met|with|mit)?\s*(?:€|eur|euros?|euro|\$)?\s*"
                    r"(\d+(?:[.,]\d+)?)\s*(?:€|eur|euros?|euro|\$)?\s*"
                    r"(?:per\s+(?:uitvoering|execution|ausf.hrung)|each|je)?",
                    lowered,
                )
            if amount_match:
                raw_amount = next((group for group in amount_match.groups() if group), None)
                if raw_amount:
                    values["base_amount"] = self._numeric_value(raw_amount)
            if str(values.get("execution_mode") or "").startswith("automatis"):
                values["execution_mode"] = "fixed"
            if "name" not in values:
                natural_name = re.search(
                    r"\b(?:strategie|strategy)\s+[\"']?(.{2,80}?)[\"']?\s+"
                    r"(?:voor|for|f.r)\s+(?:de\s+|the\s+|die\s+)?setup\b",
                    text,
                    re.IGNORECASE,
                )
                if natural_name:
                    values["name"] = natural_name.group(1).strip(" .\"'")
            strategy_values = self._strategy_trade_inputs(text)
            values.update({key: value for key, value in strategy_values.items() if key in accepted_inputs})
        elif contract.operation_id == "create_bot" and "budget_total_eur" in accepted_inputs:
            if "name" not in values:
                natural_name = re.search(
                    r"\b(?:paper[- ]?bot|bot)\s+[\"']?(.{2,80}?)[\"']?\s+"
                    r"(?:voor|for|f.r)\s+(?:de\s+|the\s+|die\s+)?(?:strategie|strategy)\b",
                    text,
                    re.IGNORECASE,
                )
                if natural_name:
                    values["name"] = natural_name.group(1).strip(" .\"'")
            budget = re.search(
                r"\b(?:budget|totaalbudget|total\s+budget|gesamtbudget)\s*"
                r"(?:is|:|=|van|of|von)?\s*(?:€|eur|euros?|euro)?\s*(\d+(?:[.,]\d+)?)",
                text,
                re.IGNORECASE,
            )
            if budget:
                values["budget_total_eur"] = float(budget.group(1).replace(",", "."))
        elif contract.operation_id in {"update_setup", "update_strategy"}:
            entity = "setup" if contract.operation_id == "update_setup" else "strategy"
            identifier = re.search(
                rf"\b{entity}(?:\s*(?:id|nummer|number)\s*#?|\s*#)\s*((?!0\d)\d+)\b",
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
    def _is_short_slot_answer(text: str, *, requested_slot: str) -> bool:
        """Keep a focused clarification answer inside its requested slot.

        Longer turns with explicit field labels remain eligible for multi-slot
        extraction and corrections.
        """
        words = re.findall(r"\w+", str(text or ""), re.UNICODE)
        if len(words) > 8:
            return False
        field_markers = {
            "entry": ("entry", "instap", "einstieg"),
            "stop_loss": ("stop", "invalidatie", "invalidation", "invalidierung"),
            "targets": ("target", "doel", "take profit", "ziel"),
            "risk_profile": ("risk", "risico", "risiko"),
            "base_amount": ("bedrag", "inleg", "amount", "betrag"),
        }
        lowered = str(text or "").casefold()
        mentioned = {
            field
            for field, markers in field_markers.items()
            if any(marker in lowered for marker in markers)
        }
        return not mentioned or mentioned == {requested_slot}

    @staticmethod
    def _is_explicit_correction(text: str) -> bool:
        return bool(re.search(
            r"\b(?:corrigeer|correct|correctie|wijzig|verander|pas\s+aan|update|change|"
            r"ändern|aendere|korrigiere|aktualisiere)\b|\bmaak\b.+\btoch\b",
            str(text or "").casefold(),
        ))

    @classmethod
    def _explicit_correction_inputs(
        cls, *, contract: OperationContract, message: str, accepted_inputs: set[str]
    ) -> dict[str, object]:
        text = str(message or "")
        aliases = (
            ("base_amount", r"(?:basisinleg|basisbedrag|bedrag|inleg|amount|betrag)"),
            ("entry", r"(?:entry|instap|einstieg)"),
            ("stop_loss", r"(?:stop[- ]?loss|invalidatie|invalidation|invalidierung)"),
            ("targets", r"(?:targets?|doelen?|take[- ]?profit|ziele?)"),
            ("risk_profile", r"(?:risico|risk|risiko)"),
        )
        for field, alias in aliases:
            if field not in accepted_inputs or not re.search(rf"\b{alias}\b", text, re.IGNORECASE):
                continue
            if field == "targets":
                numbers = re.findall(r"\d+(?:[.,]\d+)?", text)
                return {field: [float(number.replace(",", ".")) for number in numbers]} if numbers else {}
            if field == "risk_profile":
                tail = re.split(alias, text, maxsplit=1, flags=re.IGNORECASE)[-1].strip(" .,:;-")
                canonical = cls._canonical_risk_profile(tail) if tail else None
                return {field: canonical} if canonical else {}
            number = re.search(r"\d+(?:[.,]\d+)?", text)
            return {field: float(number.group(0).replace(",", "."))} if number else {}
        return {}

    def _requested_slot_value(self, *, field: str, text: str, contract: OperationContract) -> Optional[object]:
        """Canonicalize only the registry slot that the user was asked for."""
        value = str(text or "").strip()
        if not value:
            return None
        if field == "name":
            named = self._name_input_from_text(value) or value
            return FinnV2SetupInputCatalog.display_name(named) if contract.operation_id == "create_setup" else named
        if field == "dca_frequency":
            lowered = value.casefold()
            for token, canonical in (
                ("daily", "daily"), ("dagelijks", "daily"), ("taeglich", "daily"),
                ("weekly", "weekly"), ("wekelijks", "weekly"),
                ("monthly", "monthly"), ("maandelijks", "monthly"),
            ):
                if re.search(rf"\b{token}\b", lowered):
                    return canonical
            return None
        if field == "dca_day":
            lowered = FinnV2SetupInputCatalog._comparison_text(value)
            weekdays = {
                "monday": "monday", "maandag": "monday", "montag": "monday",
                "tuesday": "tuesday", "dinsdag": "tuesday", "dienstag": "tuesday",
                "wednesday": "wednesday", "woensdag": "wednesday", "mittwoch": "wednesday",
                "thursday": "thursday", "donderdag": "thursday", "donnerstag": "thursday",
                "friday": "friday", "vrijdag": "friday", "freitag": "friday",
                "saturday": "saturday", "zaterdag": "saturday", "samstag": "saturday",
                "sunday": "sunday", "zondag": "sunday", "sonntag": "sunday",
            }
            return weekdays.get(lowered)
        if field == "dca_month_day":
            match = re.fullmatch(r"(?:dag\s*)?(\d{1,2})(?:e|ste|de|st|nd|rd|th)?", value.casefold())
            if match and 1 <= int(match.group(1)) <= 28:
                return str(int(match.group(1)))
            return None
        if field == "timeframe":
            return FinnV2SetupInputCatalog.timeframe_from_text(value)
        if field == "setup_type":
            return FinnV2SetupInputCatalog.setup_type_from_text(value)
        if field == "execution_mode":
            lowered = value.casefold()
            if re.search(r"\b(?:fixed|vast|standaard|manual|handmatig|fest(?:e)?)\b", lowered):
                return "fixed"
            if re.search(r"\b(?:custom|aangepast|individuell|benutzerdefiniert)\b", lowered):
                return "custom"
            if re.search(r"\b(?:automatic|automatis\w*)\b", lowered):
                return "automatic"
            return None
        if field == "changed_fields":
            changes = self._natural_changed_fields(value, contract=contract)
            return changes or None
        if field == "requested_change":
            return value
        if contract.operation_id == "create_strategy":
            parsed = self._strategy_trade_inputs(value, requested_field=field)
            if field in parsed:
                return parsed[field]
            if field in {"entry", "stop_loss", "base_amount"}:
                number = re.search(r"-?\d+(?:[.,]\d+)?", value)
                return float(number.group(0).replace(",", ".")) if number else None
            if field == "targets":
                numbers = re.findall(r"\d+(?:[.,]\d+)?", value)
                return [float(number.replace(",", ".")) for number in numbers] or None
            if field == "risk_profile":
                return self._canonical_risk_profile(value)
        return None

    @staticmethod
    def _canonical_risk_profile(value: str) -> Optional[str]:
        normalized = FinnV2SetupInputCatalog._comparison_text(value).strip(" .,:;!?\"'")
        aliases = {
            "conservative": "conservative",
            "cautious": "conservative",
            "voorzichtig": "conservative",
            "defensief": "conservative",
            "defensive": "conservative",
            "defensiv": "conservative",
            "vorsichtig": "conservative",
            "balanced": "balanced",
            "gebalanceerd": "balanced",
            "evenwichtig": "balanced",
            "ausgewogen": "balanced",
            "aggressive": "aggressive",
            "offensief": "aggressive",
            "agressief": "aggressive",
            "offensiv": "aggressive",
        }
        return aliases.get(normalized)

    @staticmethod
    def _numeric_value(value: str) -> float:
        """Parse a human-entered decimal or locale thousands separator."""
        raw = str(value or "").strip().replace(" ", "")
        if "," in raw and "." in raw:
            decimal = "," if raw.rfind(",") > raw.rfind(".") else "."
            grouping = "." if decimal == "," else ","
            raw = raw.replace(grouping, "").replace(decimal, ".")
        elif raw.count(".") > 1:
            raw = raw.replace(".", "")
        elif raw.count(",") > 1:
            raw = raw.replace(",", "")
        elif re.fullmatch(r"\d{1,3}[.,]\d{3}", raw):
            raw = raw.replace(".", "").replace(",", "")
        else:
            raw = raw.replace(",", ".")
        return float(raw)

    @classmethod
    def _strategy_trade_inputs(
        cls,
        text: str,
        *,
        requested_field: Optional[str] = None,
    ) -> dict[str, object]:
        """Extract only explicitly stated strategy contract fields."""
        values: dict[str, object] = {}
        patterns = {
            "entry": r"\b(?:entry|instap(?:prijs)?|einstieg(?:spreis)?)\s*(?:is|:|=|op|at|bei|rond|around|ongeveer|ungefähr|ca\.?)?\s*(?:€|eur|\$)?\s*(\d+(?:[.,]\d+)?)",
            "stop_loss": r"\b(?:stop[- ]?loss|stop|invalidatie|invalidation|invalidierung)\s*(?:is|:|=|op|at|bei)?\s*(?:€|eur|\$)?\s*(\d+(?:[.,]\d+)?)",
            "base_amount": r"\b(?:base\s*amount|basisinleg|basis\s*bedrag|basisbetrag|grundbetrag|bedrag)\s*(?:is|:|=|van|of|von)?\s*(?:€|eur)?\s*(\d+(?:[.,]\d+)?)",
        }
        for field, pattern in patterns.items():
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                values[field] = cls._numeric_value(match.group(1))
        targets = re.search(
            r"\b(?:targets?|koersdoelen?|take[- ]?profits?|ziele?n?)\s*"
            r"(?:zijn|are|sind|:|=|op|at)?\s*"
            r"(.+?)(?=,?\s+(?:(?:and|en|und)\s+)?(?:(?:maximaal|max(?:imum)?|maximum|höchstens)\s+"
            r"\d+(?:[.,]\d+)?\s*(?:procent|percent|%|prozent)\s+)?(?:risk(?:\s*profile|\s*style)?|"
            r"risico(?:profiel|stijl|regel)?|risikoprofil|risikostil)\b|[!?\n]|\.(?:\s|$)|$)",
            text,
            re.IGNORECASE,
        )
        if targets:
            numbers = re.findall(r"\d+(?:[.,]\d+)?", targets.group(1))
            if numbers:
                values["targets"] = [cls._numeric_value(number) for number in numbers]
        risk_prefix = re.search(
            r"\b((?:maximaal|max(?:imum)?|maximum|höchstens)\s+\d+(?:[.,]\d+)?\s*"
            r"(?:procent|percent|%|prozent))\s+(?:risk|risico|risiko)\b",
            text,
            re.IGNORECASE,
        )
        risk = re.search(
            r"\b(?:risk(?:\s*profile|\s*rule|\s*style)?|risico(?:profiel|regel|stijl)?|risikoprofil|risikostil)\s*(?:is|:|=)?\s*"
            r"([^,.!?\n]+?)(?=\s+(?:and|en|und)\s+(?:(?:the|de|dem)\s+)?(?:name|naam|namen)|[,.!?\n]|$)",
            text,
            re.IGNORECASE,
        )
        if risk_prefix:
            values["risk_profile"] = risk_prefix.group(1).strip()
        elif risk:
            values["risk_profile"] = risk.group(1).strip()
        else:
            natural_risk = re.search(
                r"\b(conservative|cautious|voorzichtig|defensief|defensive|defensiv|vorsichtig|"
                r"balanced|gebalanceerd|evenwichtig|ausgewogen|aggressive|offensief|agressief|"
                r"offensiv)\s+(?:risk(?:\s*profile|\s*style)?|risico(?:profiel|stijl)?|risikoprofil|risikostil)\b",
                text,
                re.IGNORECASE,
            )
            if natural_risk:
                values["risk_profile"] = natural_risk.group(1).strip()
        if "risk_profile" in values:
            canonical_risk = cls._canonical_risk_profile(str(values["risk_profile"]))
            if canonical_risk:
                values["risk_profile"] = canonical_risk
            else:
                values.pop("risk_profile", None)
        if requested_field == "name" and text.strip():
            values["name"] = cls._name_input_from_text(text) or text.strip(" .\"'")
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
    def _name_input_from_text(text: str) -> Optional[str]:
        named = re.search(
            r"\b(?:mit\s+dem\s+namen|unter\s+dem\s+namen|dem\s+namen|met\s+de\s+naam|namens|genannt|"
            r"genaamd|named|called|call\s+it|nenne\s+(?:ihn|sie|es)|"
            r"noem\s+(?:hem|haar|het|deze|dit)|ik\s+noem\s+(?:hem|haar|het|deze|dit)|"
            r"hij\s+heet|het\s+heet|naam|name|titel|title)\b"
            r"\s*(?:is|:|=)?\s*[\"']?([\w .-]{2,80}?)"
            r"(?=\s+(?:voor|for|für)\s+[\w-]+\b|\s+(?:op|on|auf)\s+\d|[,;.!?\n]|$)",
            text,
            re.IGNORECASE,
        )
        if not named:
            return None
        return named.group(1).strip(" .\"'") or None

    @classmethod
    def _natural_changed_fields(cls, text: str, *, contract: OperationContract) -> dict[str, object]:
        """Capture one explicit natural-language change for a typed update slot.

        The action contract deliberately exposes ``changed_fields`` as one
        typed object; the downstream adapter remains the authority for which
        fields it accepts.  This parser only serializes an explicitly stated
        ``field -> value`` pair and does not infer a change from prose.
        """
        structured = cls._structured_changed_fields(text)
        if structured:
            return structured
        changes: dict[str, object] = {}
        if contract.operation_id == "update_strategy":
            mode = re.search(
                r"\b(?:naar|to|auf)\s+(manual|handmatig|automatic|automatis\w*|fest(?:e)?|"
                r"fixed|vast|custom|aangepast|individuell|benutzerdefiniert)\b",
                text,
                re.IGNORECASE,
            )
            if mode:
                raw_mode = mode.group(1).casefold()
                canonical_mode = {
                    "handmatig": "fixed", "manual": "fixed", "fixed": "fixed", "vast": "fixed",
                    "fest": "fixed", "feste": "fixed", "automatic": "automatic",
                    "aangepast": "custom", "individuell": "custom", "benutzerdefiniert": "custom",
                }.get(raw_mode, "automatic" if raw_mode.startswith("automatis") else raw_mode)
                changes["execution_mode"] = canonical_mode
            changes.update(cls._strategy_trade_inputs(text))
        # The action contract deliberately has one ``changed_fields`` slot,
        # while the owning domain services keep their field allowlists.  Parse
        # common natural-language update clauses into those canonical domain
        # keys before the generic field/value parser sees possessives such as
        # "its timeframe" or a German object name.
        domain_fields = {
            "update_setup": {"timeframe"},
            "update_strategy": {"base_amount"},
            "update_bot": {"budget_total_eur"},
        }.get(contract.operation_id, set())

        if contract.operation_id == "update_bot":
            budget_transition = re.search(
                r"\b(?:budget|totaalbudget|total\s+budget|gesamtbudget)\b"
                r"[^\n]{0,160}?\b(?:naar|to|auf|op|at|setze\s+auf)\s+"
                r"(?:€|eur|euro)?\s*([0-9][0-9.,]*|honderd|duizend|hundred|thousand|hundert|tausend)"
                r"(?:\s*(?:€|eur|euro|euros))?\b",
                text,
                re.IGNORECASE,
            )
            if budget_transition:
                changes["budget_total_eur"] = cls._typed_numeric_value(
                    budget_transition.group(1)
                )

        # Natural update requests often describe both the old and new value:
        # "Wijzig deze setup van timeframe 4H naar 1D."  The old value is
        # context, not another mutation. Bind only the final value to the
        # registry-owned changed_fields slot.
        if contract.operation_id == "update_setup":
            timeframe_transition = re.search(
                r"\b(?:wijzig|verander|change|update|aktualisiere|ändere)\b"
                r"[^,.!?\n]{0,100}?\b(?:van|from|von)\s+"
                r"(?:timeframe|time\s*frame|tijdframe|zeitrahmen)\s+"
                r"[\w-]+\s+(?:naar|to|auf)\s+([\w-]+)",
                text,
                re.IGNORECASE,
            )
            if timeframe_transition:
                changes["timeframe"] = FinnV2SetupInputCatalog.canonical_input(
                    "timeframe", timeframe_transition.group(1)
                )
        canonical_clauses = (
            ("timeframe", r"(?:its\s+)?(?:timeframe|time\s*frame|tijdframe|zeitrahmen)"),
            ("base_amount", r"(?:the\s+)?(?:base\s*amount|basisinleg|basis\s*bedrag|basisbetrag|grundbetrag)"),
            ("budget_total_eur", r"(?:the\s+)?(?:total\s+budget|budget|totaalbudget|gesamtbudget)"),
        )
        for field, aliases in canonical_clauses:
            if field not in domain_fields:
                continue
            if field in changes:
                continue
            natural = re.search(
                rf"\b(?:zet|set|setze|wijzig|verander|change|aktualisiere)\s+"
                rf"(?:mijn|my|de|het|the|den|die|das)?\s*{aliases}\s+"
                r"(?:naar|to|auf|als|op|on)\s+[\"']?([^,.!?\n]{1,80})",
                text,
                re.IGNORECASE,
            )
            if natural:
                value = natural.group(1).strip(" .\"'")
                if value:
                    value = re.sub(r"\s*(?:eur|euro|€)\s*$", "", value, flags=re.IGNORECASE).strip()
                    value = cls._typed_numeric_value(value)
                    changes[field] = FinnV2SetupInputCatalog.canonical_input(field, value)
            if field in changes:
                continue
            field_then_object = re.search(
                rf"\b(?:zet|set|setze|wijzig|verander|change|aktualisiere)\s+"
                rf"(?:mijn|my|de|het|the|den|die|das)?\s*{aliases}\b"
                r"[^,.!?\n]{0,120}?\s+(?:naar|to|auf|als|op|on)\s+"
                r"(?:€|eur|euro)?\s*[\"']?([^,.!?\n]{1,80})",
                text,
                re.IGNORECASE,
            )
            if field_then_object:
                value = field_then_object.group(1).strip(" .\"'")
                value = re.sub(r"\s*(?:eur|euro|€)\s*$", "", value, flags=re.IGNORECASE).strip()
                value = cls._typed_numeric_value(value)
                changes[field] = FinnV2SetupInputCatalog.canonical_input(field, value)
            if field in changes:
                continue
            # Users often name the object before the requested field, for
            # example: "Wijzig setup My Plan naar timeframe 1D". Keep the
            # owner-scoped object reference separate and bind only the
            # canonical field/value tail to changed_fields.
            object_then_field = re.search(
                rf"\b(?:wijzig|verander|change|update|aktualisiere|pas)\s+"
                rf"(?:mijn|my|deze|dit|this|het|the|den|die|das|dieses|de)?\s*{re.escape(contract.domain)}\b"
                rf"[^,.!?\n]{{0,80}}?(?:\s+aan)?\s+(?:naar|to|auf|als|op|on)\s+{aliases}\s+"
                r"(?:naar|to|auf|als|op|on)?\s*[\"']?([^,.!?\n]{1,80})",
                text,
                re.IGNORECASE,
            )
            if object_then_field:
                value = object_then_field.group(1).strip(" .\"'")
                if value:
                    changes[field] = FinnV2SetupInputCatalog.canonical_input(field, value)
        if changes:
            return changes
        # Prefer the final imperative in a natural update sentence. Object
        # names can themselves contain words such as "Update", which must
        # never become a changed-field name.
        match = re.search(
            r"\b(?:zet|set|setze|ändere)\s+"
            r"(?:mijn|my|deze|dit|this|het|the|den|die|das|dieses|de)?\s*([\w -]{2,48}?)\s+"
            r"(?:naar|to|auf|als|op|on)\s+[\"']?([^,.!?\n]{1,80})",
            text,
            re.IGNORECASE,
        )
        if not match:
            # In a compound request, the initial update verb describes the
            # object ("update that setup") while the later change clause
            # owns the field/value pair. Prefer that explicit clause so it
            # cannot be serialized as a synthetic field name.
            match = re.search(
                r"\b(?:wijzig|verander|change|aktualisiere)\s+"
                r"(?:mijn|my|deze|dit|this|het|the|den|die|das|dieses|de)?\s*([\w -]{2,48}?)\s+"
                r"(?:naar|to|auf|als|op|on)\s+[\"']?([^,.!?\n]{1,80})",
                text,
                re.IGNORECASE,
            )
        if not match:
            match = re.search(
                r"\b(?:wijzig|verander|change|update|aktualisiere)\s+"
            r"(?:mijn|my|deze|dit|this|het|the|den|die|das|dieses|de)?\s*([\w -]{2,48}?)\s+"
            r"(?:naar|to|auf|als|op|on)\s+[\"']?([^,.!?\n]{1,80})",
            text,
            re.IGNORECASE,
            )
        if not match:
            # Natural action requests commonly attach a typed update after the
            # object reference ("werk ... bij met timeframe 1 uur"). This is
            # still an explicit field/value pair, not inferred state.
            match = re.search(
                r"\b(?:met|with|en\s+zet|and\s+set|und\s+setze)\s+"
                r"(?:deze|dit|this|het|the|den|die|das|dieses|de)?\s*([\w -]{2,48}?)\s+"
                r"(?:(?:naar|to|auf|als|op|on)\s+)?[\"']?([^,.!?\n]{1,80})",
                text,
                re.IGNORECASE,
            )
        if not match:
            return {}
        field = re.sub(r"\s+", "_", match.group(1).strip().casefold())
        # Object names are supplied by the selected registry contract; remove
        # only that object prefix, never a domain-specific list of fields.
        domain_prefix = f"{contract.domain}_"
        if field.startswith(domain_prefix):
            field = field[len(domain_prefix):]
        field = re.sub(r"^\d+_", "", field)
        field = {
            "naam": "name",
            "namen": "name",
            "titel": "name",
            "tijdframe": "timeframe",
            "time_frame": "timeframe",
            "periode": "period",
            "basisinleg": "base_amount",
            "basis_bedrag": "base_amount",
            "bedrag": "base_amount",
        }.get(field, field)
        value = match.group(2).strip(" .\"'")
        if not field or not value:
            return {}
        # Currency is presentation around an otherwise explicit numeric action
        # value; preserve the number's type instead of sending a prose value to
        # the action adapter.
        value = re.sub(r"^\s*(?:eur|euro|€)\s*", "", value, flags=re.IGNORECASE)
        value = re.sub(r"\s*(?:eur|euro|€)\s*$", "", value, flags=re.IGNORECASE).strip()
        lowered = value.casefold()
        if lowered in {"true", "waar", "ja", "yes"}:
            typed_value: object = True
        elif lowered in {"false", "onwaar", "nee", "no"}:
            typed_value = False
        elif re.fullmatch(r"\d+(?:[.,]\d+)*", value):
            typed_value = cls._typed_numeric_value(value)
        else:
            typed_value = value
        return {field: FinnV2SetupInputCatalog.canonical_input(field, typed_value)}

    @staticmethod
    def _indicator_input_from_text(text: str) -> Optional[dict[str, str]]:
        """Resolve configured indicators from the canonical indicator catalogs."""
        normalized = re.sub(r"[\s_-]+", " ", text.casefold()).strip()
        definitions = [
            *get_active_technical_indicator_definitions(),
            *get_active_macro_indicator_definitions(),
            *get_active_market_indicator_definitions(),
        ]
        for definition in definitions:
            name = str(definition.get("name") or "").strip()
            category = str(definition.get("category") or "").strip()
            display = str(definition.get("display_name") or "").strip()
            variants = {name, display, name.replace("_", " "), display.replace("_", " ")}
            if any(
                variant and re.search(rf"(?<!\w){re.escape(variant.casefold())}(?!\w)", normalized)
                for variant in variants
            ):
                return {"name": name, "category": category}
        return None

    @staticmethod
    def _trim_setup_name_clause(value: str) -> str:
        """Exclude trailing non-persistence instructions from a display name."""
        return re.split(
            r"\s+(?:(?:en|and|aber|but)\s+)?(?:sla\s+(?:niets|het)?\s*op|"
            r"(?:en|and|und)\s+(?:het\s+|the\s+|dem\s+)?(?:timeframe|tijdframe|time\s*frame)\b.*|"
            r"(?:en\s+koop|and\s+buy|und\s+kauf\w*)\b.*|"
            r"(?:do\s+not|don't)\s+(?:save|write|persist)(?:\s+(?:it|the\s+setup|anything))?(?:\s+yet)?|"
            r"save\s+(?:nothing|it)|without\s+(?:saving|writing|persisting)\s+(?:it|anything)(?:\s+yet)?|"
            r"speicher\s+(?:nichts|es))\b",
            value,
            maxsplit=1,
            flags=re.IGNORECASE,
        )[0].strip(" .")

    @staticmethod
    def _trim_linked_strategy_clause(value: str) -> str:
        """Keep a bot display name separate from its linked strategy reference."""
        return re.split(
            r"\s+(?:(?:voor|for|f.r)\s+(?:de\s+|the\s+|die\s+)?|"
            r"(?:gekoppeld|verbonden)\s+aan\s+(?:de\s+)?|"
            r"(?:linked|connected)\s+to\s+(?:the\s+)?|"
            r"(?:verknuepft|verknüpft|verbunden)\s+mit\s+(?:der\s+|die\s+)?)"
            r"(?:strategie|strategy)\b.*",
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
