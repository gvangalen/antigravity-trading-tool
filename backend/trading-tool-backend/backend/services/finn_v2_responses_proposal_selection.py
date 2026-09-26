"""Translate a model proposal candidate into the existing registry-backed run plan."""

from __future__ import annotations

import re
from typing import Any, Mapping, Sequence

from backend.services.asset_catalog_service import mentioned_catalog_symbols, resolve_catalog_symbol
from backend.domain.finn_v2_operation_registry import FinnV2OperationRegistry
from backend.schemas.finn_v2_orchestrator_schema import RequestAnalysisResult, RequestPlan
from backend.services.finn_v2_operation_state_service import FinnV2OperationStateService
from backend.services.finn_v2_responses_tool_catalog import FinnResponsesToolCall


class FinnResponsesProposalSelection:
    def __init__(self, registry: FinnV2OperationRegistry | None = None) -> None:
        self.registry = registry or FinnV2OperationRegistry()
        self.states = FinnV2OperationStateService()

    def from_call(
        self,
        *,
        call: FinnResponsesToolCall,
        message: str,
        conversation_context: Mapping[str, object],
        verified_asset: str | None,
        read_context: Sequence[Mapping[str, Any]] = (),
    ) -> RequestAnalysisResult:
        if call.operation_id is None:
            raise ValueError("proposal_operation_required")
        contract = self.registry.require_supported(call.operation_id)
        if contract.mode not in {"CREATE_PROPOSAL", "ACTION_PROPOSAL"}:
            raise ValueError("proposal_operation_not_write_contract")
        inputs = dict(call.inputs)
        explicitly_named = self.states._name_input_from_text(message)
        if contract.operation_id.startswith("create_") and explicitly_named and "name" in contract.required_inputs:
            # Explicit user input outranks a model candidate that shortened the name.
            inputs["name"] = explicitly_named
        if contract.operation_id == "create_setup":
            explicit_day = self.states.explicit_inputs(
                contract=contract, message=message, explicit_asset=None,
            ).get("dca_day")
            if explicit_day is not None:
                inputs["dca_day"] = explicit_day
            else:
                # The model may propose a valid weekday that the owner never chose.
                # Persisted guided state is merged by the existing state service.
                inputs.pop("dca_day", None)
            # Contribution cadence is not a chart timeframe. The model's
            # candidate may fill this required slot only when the user's
            # current text actually states a canonical setup timeframe.
            chart_timeframe_named = bool(re.search(
                r"\b(?:\d+\s*(?:m|min|h|d|w|mo|uur|hour|dag|day|week)|"
                r"timeframe|tijdframe|time\s*frame|chart|grafiek|zeitrahmen)\b",
                message.casefold(),
            ))
            explicit_timeframe = self.states.explicit_inputs(
                contract=contract, message=message, explicit_asset=None,
            ).get("timeframe") if chart_timeframe_named else None
            revision = dict(conversation_context.get("proposal_revision") or {})
            prior_inputs = dict(dict(revision.get("guided_state") or {}).get("collected_inputs") or {})
            revising_draft = (
                call.draft_intent == "revise"
                and revision.get("operation_id") == contract.operation_id
                and bool(revision.get("proposal_id"))
            )
            if revising_draft and prior_inputs.get("timeframe") and explicit_timeframe is None:
                inputs["timeframe"] = prior_inputs["timeframe"]
            elif explicit_timeframe is not None:
                inputs["timeframe"] = explicit_timeframe
            elif not dict(conversation_context.get("active_guided_operation") or {}):
                inputs.pop("timeframe", None)
        mentioned_assets = mentioned_catalog_symbols(message)
        if len(mentioned_assets) > 1:
            raise ValueError("proposal_asset_ambiguous")
        raw_asset = inputs.get("asset") or inputs.get("symbol")
        supplied_asset = resolve_catalog_symbol(raw_asset) or ""
        if raw_asset and (not supplied_asset or (supplied_asset not in mentioned_assets and supplied_asset != verified_asset)):
            inputs.pop("asset", None)
            inputs.pop("symbol", None)
            supplied_asset = ""
        if supplied_asset and verified_asset and supplied_asset != verified_asset.upper():
            raise ValueError("proposal_asset_conflicts_with_verified_context")
        if supplied_asset:
            for field in ("asset", "symbol"):
                if field in inputs:
                    inputs[field] = supplied_asset
        context = dict(conversation_context)
        revision = dict(context.get("proposal_revision") or {})
        revising_current_draft = (
            revision.get("operation_id") == contract.operation_id
            and bool(revision.get("proposal_id"))
            and (
                call.draft_intent == "revise"
                or (call.draft_intent is None and not self.states._name_input_from_text(message))
            )
        )
        if call.draft_intent == "revise" or revising_current_draft:
            if revision.get("operation_id") != contract.operation_id or not revision.get("proposal_id"):
                if not contract.operation_id.startswith(("update_", "delete_", "deactivate_")):
                    raise ValueError("revisable_proposal_not_found_in_conversation")
                context.pop("proposal_revision", None)
            else:
                context["active_guided_operation"] = dict(revision.get("guided_state") or {})
                context["open_proposal_id"] = revision["proposal_id"]
        else:
            context.pop("proposal_revision", None)
        guided = dict(context.get("active_guided_operation") or {})
        prior_name = dict(guided.get("collected_inputs") or {}).get("name")
        read_object_names = {
            str(data["name"]).casefold()
            for read in read_context
            for result in (read.get("results") or [])
            if isinstance(result, Mapping)
            for data in [result.get("data")]
            if isinstance(data, Mapping) and data.get("name")
        }
        requires_parent = any(field in contract.required_inputs for field in ("setup_id", "strategy_id"))
        if (
            contract.operation_id.startswith("create_")
            and requires_parent
            and inputs.get("name")
            and not explicitly_named
            and not prior_name
        ):
            inputs.pop("name")
        if (
            contract.operation_id.startswith("create_")
            and inputs.get("name")
            and str(inputs["name"]).casefold() in read_object_names
            and str(explicitly_named or "").casefold() != str(inputs["name"]).casefold()
        ):
            inputs.pop("name")
        if (
            contract.operation_id.startswith("create_")
            and inputs.get("name")
            and not prior_name
            and str(inputs["name"]).casefold() not in message.casefold()
        ):
            # A generated label is not an explicitly supplied user name.
            inputs.pop("name")
        state = self.states.resolve(
            contract=contract,
            message=message,
            explicit_asset=supplied_asset or verified_asset,
            conversation_context=context,
            supplied_inputs=inputs,
            model_tool_inputs=True,
        )
        inputs = dict(state.collected_inputs)
        asset = str(inputs.get("asset") or inputs.get("symbol") or verified_asset or "").upper() or None
        plan = RequestPlan(
            user_goal=contract.semantic_description or contract.operation_id,
            initial_operation_id=contract.operation_id,
            operation_id=contract.operation_id,
            operation_contract_version=contract.version,
            interaction_mode=contract.mode,
            primary_domains=[contract.domain],
            required_information_scopes=list(contract.required_scopes),
            optional_information_scopes=list(contract.optional_scopes),
            requested_operation=contract.operation_id,
            referenced_entities=inputs,
            target_asset=asset,
            target_asset_source="model_explicit" if supplied_asset else "verified_context",
            referenced_asset=supplied_asset or None,
            selector_source="responses_tool_call",
            selector_confidence="high",
            candidate_operation_ids=[contract.operation_id],
            selection_domain=contract.domain,
            selection_supported=True,
            operation_state=state.dict(),
            missing_information=list(state.missing_required_inputs),
            clarification_required=bool(state.missing_required_inputs),
            confidence_score=1.0,
        )
        return RequestAnalysisResult(
            interaction_mode=contract.mode,
            explicit_asset=asset,
            output_contract=contract.operation_id,
            requests_change=True,
            confidence="high",
            reasoning_required=True,
            request_plan=plan,
        )
