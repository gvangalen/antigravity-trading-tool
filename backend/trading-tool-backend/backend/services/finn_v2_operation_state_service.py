"""Typed guided-operation state backed by the canonical conversation JSON."""
from __future__ import annotations

import re
from typing import Mapping, Optional

from backend.domain.finn_v2_operation_registry import OperationContract
from backend.schemas.finn_v2_orchestrator_schema import FinnV2OperationState


class FinnV2OperationStateService:
    """Collect only explicit or verified operation inputs, one field at a time."""

    _TIMEFRAME = re.compile(r"\b(1m|5m|15m|30m|1h|4h|1d|1w|1M)\b", re.IGNORECASE)

    def resolve(
        self,
        *,
        contract: OperationContract,
        message: str,
        explicit_asset: Optional[str],
        conversation_context: Optional[Mapping[str, object]],
    ) -> FinnV2OperationState:
        existing = self._existing_state(contract, conversation_context or {})
        collected = dict(existing.collected_inputs) if existing is not None else {}
        collected.update(self._explicit_inputs(contract=contract, message=message, explicit_asset=explicit_asset))
        missing = [field for field in contract.required_inputs if self._is_missing(collected.get(field))]
        context = conversation_context or {}
        resolved_entities = dict(existing.resolved_entities) if existing is not None else {}
        resolved_entities.update(
            {
                key: value
                for key, value in {
                    "asset": explicit_asset or context.get("resolved_asset"),
                    "setup_id": context.get("resolved_setup_id"),
                    "strategy_id": context.get("resolved_strategy_id"),
                    "bot_id": context.get("resolved_bot_id"),
                }.items()
                if value is not None
            }
        )
        return FinnV2OperationState(
            operation_id=contract.operation_id,
            contract_version=contract.version,
            collected_inputs=collected,
            resolved_entities=resolved_entities,
            missing_required_inputs=missing,
            next_missing_input=missing[0] if missing else None,
            open_proposal_id=context.get("open_proposal_id"),
            previous_verified_conclusion=context.get("last_verified_conclusion"),
            previous_evidence_refs=list(context.get("last_evidence_refs") or []),
        )

    @staticmethod
    def pending_operation_id(context: Mapping[str, object]) -> Optional[str]:
        raw = context.get("operation_state")
        if not isinstance(raw, dict) or context.get("open_proposal_id"):
            return None
        try:
            state = FinnV2OperationState.parse_obj(raw)
        except (TypeError, ValueError):
            return None
        return state.operation_id if state.missing_required_inputs else None

    @staticmethod
    def clarification_question(field: Optional[str]) -> str:
        questions = {
            "name": "Welke korte naam wil je voor deze setup gebruiken?",
            "symbol": "Voor welke asset wil je deze setup precies voorbereiden?",
            "setup_type": "Wil je een trade- of DCA-setup voorbereiden?",
            "setup_id": "Welke bestaande setup wil je aanpassen?",
            "changed_fields": "Welke concrete setupvelden wil je aanpassen?",
            "proposal_id": "Welk voorstel wil je precies bevestigen of uitvoeren?",
            "asset": "Welke asset wil je aan je watchlist toevoegen?",
        }
        return questions.get(field or "", "Welk ontbrekend detail wil je voor dit voorstel vastleggen?")

    def _existing_state(self, contract: OperationContract, context: Mapping[str, object]) -> Optional[FinnV2OperationState]:
        raw = context.get("operation_state")
        if not isinstance(raw, dict):
            return None
        try:
            state = FinnV2OperationState.parse_obj(raw)
        except (TypeError, ValueError):
            return None
        if state.operation_id != contract.operation_id or state.contract_version != contract.version:
            return None
        return state

    def _explicit_inputs(self, *, contract: OperationContract, message: str, explicit_asset: Optional[str]) -> dict[str, object]:
        text = str(message or "").strip()
        lowered = text.casefold()
        values: dict[str, object] = {}
        if explicit_asset and "symbol" in contract.required_inputs:
            values["symbol"] = explicit_asset
        if contract.operation_id == "create_setup":
            if "dca" in lowered:
                values["setup_type"] = "dca"
            elif any(token in lowered for token in ("trade", "swing", "scalp", "setup")):
                values["setup_type"] = "trade"
            named = re.search(
                r"(?:naam|name)\s*(?:is|:)?\s*[\"']?([\w .-]{2,80})",
                text,
                re.IGNORECASE,
            )
            if named is None:
                # A pending guided operation has already asked specifically for
                # a name, so accept the common natural-language follow-up too.
                named = re.search(
                    r"\b(?:noem\s+(?:hem|haar)|ik\s+noem\s+(?:hem|haar)|hij\s+heet|het\s+heet)\s+[\"']?([\w .-]{2,80})",
                    text,
                    re.IGNORECASE,
                )
            if named:
                values["name"] = named.group(1).strip(" .")
            timeframe = self._TIMEFRAME.search(text)
            if timeframe:
                values["timeframe"] = timeframe.group(1).upper()
            if any(token in lowered for token in ("daily trend", "dagtrend", "uptrend", "downtrend")):
                values["market_condition"] = "trend_defined"
        elif contract.operation_id in {"watchlist_add", "watchlist_remove"} and explicit_asset:
            values["asset"] = explicit_asset
        return values

    @staticmethod
    def _is_missing(value: object) -> bool:
        return value is None or (isinstance(value, str) and not value.strip())
